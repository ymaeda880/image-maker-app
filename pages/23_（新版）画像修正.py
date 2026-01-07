# pages/23_（新版）画像修正.py
# ============================================================
# 🧪 画像アップロード → 何度でも修正（gpt-image-1）
# + ログイン表示（common_lib/auth/auth_helpers.py）
# + ログ（upload/reset/edit を JSONL に保存, JST, app_name/page_name 自動付与）
# + ログファイルは logs/{app_name}.log.jsonl（共通ロガー）
# ============================================================

from __future__ import annotations

# ==== ここから追加（22ページと同じパス設定）====
import sys
from pathlib import Path
import sqlite3


_THIS = Path(__file__).resolve()
APP_DIR = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
MONO_ROOT = _THIS.parents[3]

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PAGE_NAME = _THIS.stem
PROJECTS_ROOT = MONO_ROOT  # ★ Storages 解決に使う projects ルート（22ページと同じ意味）

# ==== ここまで追加 ====



from io import BytesIO
import base64, tempfile
from typing import Dict, Any
import streamlit as st
from PIL import Image
from openai import OpenAI

from lib.openai_client import get_client
from lib.image_utils import pil_to_png_bytes, url_to_png_bytes

from pathlib import Path
import datetime as dt

# ★ ログイン関連（共通ヘルパー）
from common_lib.auth.auth_helpers import get_current_user_from_session_or_cookie
from common_lib.auth.auth_helpers import require_login
# ★ 共通JSONLロガー
from common_lib.logs.jsonl_logger import JsonlLogger, sha256_short

# --------------------- ページ設定 ---------------------
st.set_page_config(page_title="画像アップロード→修正", page_icon="🧪", layout="wide")


sub = require_login(st)
if not sub:
    st.stop()
left, right = st.columns([2, 1])
with left:
    st.title("✏️🖼️ 画像修正")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

user = sub

# --------------------- ロガー初期化（Storages/logs/<app_name>/<log_name>_YYYY-MM.jsonl） ---------------------

logger = JsonlLogger(
    projects_root=PROJECTS_ROOT,
    app_name=APP_DIR.name,
    page_name=PAGE_NAME,
    log_name=APP_DIR.name,   # 例：image_maker_app_YYYY-MM.jsonl
    rotate="monthly",
)

INCLUDE_FULL_PROMPT_IN_LOG = True
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")

# ★ ページ専用のセッションキー（他ページと衝突しないようにする）
SESSION_KEY_LAST = f"{PAGE_NAME}_simple_last_png"      # 現在の修正対象PNG（常に最新）
SESSION_KEY_UPLOADED = f"{PAGE_NAME}_uploaded_png"     # アップロード直後のPNG（初期元画像）

# --------------------- クライアント & セッション ---------------------
client: OpenAI = get_client()
st.session_state.setdefault(SESSION_KEY_LAST, b"")
st.session_state.setdefault(SESSION_KEY_UPLOADED, b"")

# ============================================================
# Inbox 画像選択（last_viewed は更新しない）
# - 自分のboxのみ（sub固定）
# - kind=image のみ
# - added_at 降順
# - 10件/ページ
# - ページ移動で選択クリア
# ============================================================

INBOX_PAGE_SIZE = 10
INBOX_ROOT = (PROJECTS_ROOT / "InBoxStorages")  # 既存運用に合わせる（projects直下想定）

K_INBOX_PAGE = f"{PAGE_NAME}_inbox_page"
K_INBOX_SELECTED_ITEM = f"{PAGE_NAME}_inbox_selected_item"  # item_id を入れる

st.session_state.setdefault(K_INBOX_PAGE, 0)
# 「未選択」を明確にするため、selected は setdefault しない（ある場合のみ使う）


def _inbox_user_root(user_sub: str) -> Path:
    return INBOX_ROOT / str(user_sub)


def _items_db_path(user_sub: str) -> Path:
    # 既存の inbox 正本DB：_meta/inbox_items.db を前提
    return _inbox_user_root(user_sub) / "_meta" / "inbox_items.db"


def _query_inbox_images_page(user_sub: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    """
    inbox_items から image のみをページ取得（added_at desc）
    戻り値: (rows, total)
    rows は item_id, original_name, stored_rel, added_at
    """
    db_path = _items_db_path(user_sub)
    if not db_path.exists():
        return [], 0

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        # total
        cur.execute(
            "SELECT COUNT(1) FROM inbox_items WHERE kind = ?",
            ("image",),
        )
        total = int(cur.fetchone()[0] or 0)

        # page
        cur.execute(
            """
            SELECT item_id, original_name, stored_rel, added_at
            FROM inbox_items
            WHERE kind = ?
            ORDER BY added_at DESC
            LIMIT ? OFFSET ?
            """,
            ("image", int(limit), int(offset)),
        )
        out: list[dict[str, Any]] = []
        for item_id, original_name, stored_rel, added_at in cur.fetchall():
            out.append(
                {
                    "item_id": str(item_id),
                    "original_name": str(original_name or ""),
                    "stored_rel": str(stored_rel or ""),
                    "added_at": str(added_at or ""),
                }
            )
        return out, total
    finally:
        con.close()


def _load_inbox_image_as_png_bytes(user_sub: str, stored_rel: str) -> bytes:
    """
    stored_rel を user_root から解決して読み込み、RGBA PNG bytes に正規化して返す
    """
    user_root = _inbox_user_root(user_sub)
    p = (user_root / stored_rel).resolve()

    # 念のため：user_root の外に出ない（パストラバーサル対策）
    if user_root.resolve() not in p.parents and p != user_root.resolve():
        raise ValueError("Invalid stored_rel (path traversal detected).")

    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    img = Image.open(p).convert("RGBA")
    return pil_to_png_bytes(img)


def _clear_inbox_selection() -> None:
    # ページ移動時の事故防止：必ずクリア
    if K_INBOX_SELECTED_ITEM in st.session_state:
        st.session_state.pop(K_INBOX_SELECTED_ITEM, None)


# ============================================================
# 1) 画像アップロード
# ============================================================
st.subheader("1) 画像をアップロード")
uploaded = st.file_uploader(
    "PNG/JPG(JPEG) 画像を選択してください",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=False
)

col_up1, col_up2 = st.columns([1, 1])
with col_up1:
    reset_clicked = st.button("🔁 リセット（画像クリア）", width="stretch")
with col_up2:
    use_uploaded_clicked = st.button("⬆️ アップロード画像を読み込む", width="stretch")

if reset_clicked:
    st.session_state[SESSION_KEY_UPLOADED] = b""
    st.session_state[SESSION_KEY_LAST] = b""
    st.success("状態をリセットしました。")
    # ログ：リセット
    logger.append({
        "user": user or "(anonymous)",
        "action": "reset",
    })

# アップロード画像をPNG化して保持（押下時に反映）
if use_uploaded_clicked:
    if uploaded is None:
        st.warning("先に画像ファイルを選択してください。")
    else:
        try:
            img = Image.open(uploaded).convert("RGBA")
            png_bytes = pil_to_png_bytes(img)
            st.session_state[SESSION_KEY_UPLOADED] = png_bytes
            st.session_state[SESSION_KEY_LAST] = png_bytes  # 初期の修正対象に昇格
            st.success("アップロード画像を読み込みました。")
            # ログ：アップロード読み込み
            logger.append({
                "user": user or "(anonymous)",
                "action": "upload_loaded",
                "filename": getattr(uploaded, "name", None),
                "size_bytes": len(png_bytes),
            })
        except Exception as e:
            st.error(f"画像の読み込みに失敗しました: {e}")


# ============================================================
# 1-b) Inbox から読み込む（アップロードと同じ操作感）
# ============================================================
# トグル：Inboxから読み込む
use_inbox = st.toggle("📥 Inboxから読み込む（画像のみ）", value=False)
if use_inbox:

    # Inboxルートが無い場合は黙って案内（ページ自体は使える）
    if not INBOX_ROOT.exists():
        st.info(f"InBoxStorages が見つかりません: {INBOX_ROOT}")
    else:
        # ページング
        page_index = int(st.session_state.get(K_INBOX_PAGE, 0))
        offset = page_index * INBOX_PAGE_SIZE

        rows, total = _query_inbox_images_page(user_sub=sub, limit=INBOX_PAGE_SIZE, offset=offset)

        if total <= 0 or not rows:
            st.caption("Inboxに画像がありません（kind=image）。")
        else:
            last_page = max(0, (total - 1) // INBOX_PAGE_SIZE)
            if page_index > last_page:
                page_index = last_page
                st.session_state[K_INBOX_PAGE] = last_page
                offset = page_index * INBOX_PAGE_SIZE
                rows, total = _query_inbox_images_page(user_sub=sub, limit=INBOX_PAGE_SIZE, offset=offset)

            nav1, nav2, nav3, nav4 = st.columns([1, 1, 3.2, 4.8])
            with nav1:
                if st.button("⬅ 前へ", disabled=(page_index <= 0), key=f"{PAGE_NAME}_inbox_prev"):
                    st.session_state[K_INBOX_PAGE] = max(page_index - 1, 0)
                    _clear_inbox_selection()
                    st.rerun()
            with nav2:
                if st.button("次へ ➡", disabled=(page_index >= last_page), key=f"{PAGE_NAME}_inbox_next"):
                    st.session_state[K_INBOX_PAGE] = min(page_index + 1, last_page)
                    _clear_inbox_selection()
                    st.rerun()
            with nav3:
                start = offset + 1
                end = min(offset + INBOX_PAGE_SIZE, total)
                st.caption(f"件数: {total}　／　ページ: {page_index + 1} / {last_page + 1}　（表示レンジ：{start}–{end}）")
            with nav4:
                st.caption("※ ページ移動時は選択がクリアされます（事故防止）")

            # radio（original_name のみ表示）
            options = [r["item_id"] for r in rows]
            label_map = {r["item_id"]: (r["original_name"] or r["item_id"]) for r in rows}

            def _fmt_item_id(x: str) -> str:
                return label_map.get(str(x), str(x))

            selected_item_id = st.radio(
                "画像を選択（original_name）",
                options=options,
                index=None,  # 未選択を許可（ボタンで確定）
                format_func=_fmt_item_id,
                key=K_INBOX_SELECTED_ITEM,
            )

            # 確定ボタン（安全）
            cbtn1, cbtn2 = st.columns([2, 8])
            with cbtn1:
                load_inbox_clicked = st.button("📥 Inbox画像を読み込む", key=f"{PAGE_NAME}_load_from_inbox")
            with cbtn2:
                st.caption("※ 押すと「アップロード画像を読み込む」と同じ挙動で、修正元にセットされます。")

            if load_inbox_clicked:
                if not selected_item_id:
                    st.warning("先にInboxの画像を選択してください。")
                else:
                    # 選択行を引く（stored_relが必要）
                    picked = None
                    for r in rows:
                        if str(r.get("item_id")) == str(selected_item_id):
                            picked = r
                            break

                    if not picked:
                        st.error("選択された画像の情報が見つかりません（ページ更新の可能性）。もう一度選択してください。")
                    else:
                        try:
                            png_bytes = _load_inbox_image_as_png_bytes(
                                user_sub=sub,
                                stored_rel=str(picked.get("stored_rel") or ""),
                            )
                            # ✅ アップロードと同じ：UPLOADED と LAST を両方更新
                            st.session_state[SESSION_KEY_UPLOADED] = png_bytes
                            st.session_state[SESSION_KEY_LAST] = png_bytes
                            st.success("Inbox画像を読み込みました。")

                            # ログ
                            logger.append({
                                "user": user or "(anonymous)",
                                "action": "inbox_loaded",
                                "item_id": str(picked.get("item_id") or ""),
                                "original_name": str(picked.get("original_name") or ""),
                                "size_bytes": len(png_bytes),
                            })

                            st.rerun()

                        except Exception as e:
                            st.error(f"Inbox画像の読み込みに失敗しました: {e}")



# 現在の元画像（修正対象）を表示
current_png = st.session_state.get(SESSION_KEY_LAST, b"")
if current_png:
    st.subheader("現在の処理対象画像（修正元）")
    st.image(current_png, caption="現在の元画像", width="stretch")
else:
    st.info("画像が未設定です。上で画像をアップロードして読み込んでください。")
    st.stop()

# ============================================================
# 2) 修正ループ（images.edit）
# ============================================================
st.divider()
st.subheader("2) 修正（何度でも繰り返し可能）")

edit_prompt = st.text_area(
    "修正内容プロンプト",
    value="背景を夕焼けに、全体をシネマティックに",
    height=100,
    help="例）『被写界深度を浅く』『フィルム調』『雨の夜に』『暖色トーン』など"
)
edit_size = st.selectbox(
    "出力サイズ",
    ["1024x1024", "1024x1536", "1536x1024"],
    index=0
)

if st.button("🪄 修正版を生成する", width="stretch"):
    if not edit_prompt.strip():
        st.warning("修正内容を入力してください。")
        st.stop()
    if not st.session_state.get(SESSION_KEY_LAST):
        st.warning("修正する元画像がありません。アップロード→読み込みを行ってください。")
        st.stop()

    with st.spinner("修正版を生成中..."):
        # 一時ファイルにPNGを書き出して images.edit へ
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(st.session_state[SESSION_KEY_LAST])
            tmp.seek(0)
            res2 = client.images.edit(
                model="gpt-image-1",
                image=("image.png", tmp),
                prompt=edit_prompt.strip(),
                size=edit_size,
            )

        datum = res2.data[0]
        if getattr(datum, "b64_json", None):
            img2 = Image.open(BytesIO(base64.b64decode(datum.b64_json))).convert("RGBA")
            out_bytes = pil_to_png_bytes(img2)
        elif getattr(datum, "url", None):
            out_bytes = url_to_png_bytes(datum.url)
        else:
            st.error("修正結果が取得できませんでした。")
            st.stop()

        # 🔁 修正版を再び元画像に昇格（連続修正OK）
        st.session_state[SESSION_KEY_LAST] = out_bytes

        # ログ：編集
        logger.append({
            "user": user or "(anonymous)",
            "action": "edit",
            "source": "inline",
            "model": "gpt-image-1",
            "size": edit_size,
            "prompt_hash": sha256_short(edit_prompt.strip()),
            **({"prompt": edit_prompt.strip()} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
        })

        st.success("修正版を生成しました。さらに修正を続けられます。")
        st.subheader("今回の修正結果")
        st.image(out_bytes, caption="修正版（次の元画像になります）", width="stretch")

# ============================================================
# 3) 保存セクション（ページ下部）
# ============================================================
st.divider()
st.subheader("3) 生成画像の保存")

png_bytes = st.session_state.get(SESSION_KEY_LAST, b"")
if png_bytes:
    # サムネイル表示（小さめ）
    try:
        thumb = Image.open(BytesIO(png_bytes)).copy()
        thumb.thumbnail((256, 256))  # サムネイル最大サイズ
        st.image(thumb, caption="現在の画像（サムネイル）")
    except Exception as e:
        st.warning(f"サムネイル生成に失敗しました: {e}")

    default_name = f"edited_{dt.datetime.now(JST):%Y%m%d_%H%M%S}.png"  # ダウンロード名もJST基準
    dl_name = st.text_input("ファイル名（ダウンロード用）", value=default_name)
    st.download_button(
        "⬇️ 修正画像の保存（.png）",
        data=png_bytes,
        file_name=dl_name,
        mime="image/png",
        width="stretch",
    )




    # ============================================================
    # 4) Inbox へ保存（pages/22 と同じ方式）
    # ============================================================
    st.markdown("---")
    st.subheader("📥 Inbox へ保存")

    inbox_filename = st.text_input(
        "Inboxに保存するファイル名",
        value=dl_name,
        key=f"{PAGE_NAME}_inbox_filename",
        help="Inboxに保存されるファイル名です（.png 推奨）",
    )

    # Inboxへ保存（正本：common_lib.inbox.*）
    from common_lib.inbox.inbox_ops.ingest import ingest_to_inbox
    from common_lib.inbox.inbox_common.types import (
        IngestRequest,
        InboxNotAvailable,
        QuotaExceeded,
        IngestFailed,
    )

    if st.button("📥 この画像を Inbox に保存", type="primary", width="stretch"):
        try:
            _png = st.session_state.get(SESSION_KEY_LAST, b"")
            if not _png:
                st.warning("保存する画像がありません。先に修正を行ってください。")
                st.stop()

            ingest_to_inbox(
                projects_root=PROJECTS_ROOT,
                req=IngestRequest(
                    user_sub=sub,
                    filename=inbox_filename,
                    data=_png,
                    tags_json='["image_maker/edited"]',
                    origin={
                        "app": APP_DIR.name,
                        "page": PAGE_NAME,
                        "action": "image_edit",
                    },
                ),
            )
            st.success("Inbox に保存しました。")

        except InboxNotAvailable:
            st.error("❌ Inbox が存在しません。ストレージ接続を確認してください。")

        except QuotaExceeded as e:
            st.error(
                f"❌ 容量オーバーです。"
                f" 現在={e.current} / 追加={e.incoming} / 上限={e.quota}"
            )

        except IngestFailed as e:
            st.error(f"❌ Inbox への保存に失敗しました: {e}")



else:
    st.info("保存できる画像がありません。上で修正を実行してください。")



