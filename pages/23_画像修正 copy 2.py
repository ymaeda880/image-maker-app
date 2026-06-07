# -*- coding: utf-8 -*-
# image_maker_app/pages/23_画像修正.py
# ============================================================
# 🧪 テンプレ寄せ：画像アップロード（or Inbox選択）→ 何度でも修正
#
# 方針（テンプレ準拠）
# - st.form 不使用 / use_container_width 不使用
# - ログイン：common_lib.sessions.page_entry.page_session_heartbeat（正本）
# - AI 呼び出し：common_lib.ai.routing（正本）経由
# - 画像修正モデルはサイドバーで選択
#   - OpenAI / gpt-image-1
#   - Gemini / gemini-2.5-flash-image
# - provider:model 形式の model_key を common_lib.ai.models の正本から取得
# - 画像：ImageResult（bytes / url）→ PNG bytes に統一して表示・連続修正
#   - url の場合は urllib で取得（timeout あり）
# - busy：common_lib.busy.busy_run（with）で ai_runs.db を必ず記録
# - ログ（任意）：JsonlLogger（app/page 自動付与、JST、monthly rotate）
# - Inbox：
#   - 読み込み：inbox_items.db を直接参照（last_viewed は更新しない）
#   - 保存：common_lib.inbox.*（ingest_to_inbox）正本を使用
#
# テンプレ（22_画像生成.py）への寄せポイント（重要）
# - モデル選択：sidebar の render_image_model_picker を使用
# - サイズ選択：sidebar のボタン式 + rerun（ボタンは「1組」）
#   -> ここで選択されたサイズが「次の修正（edit）」に使用される
# - 実行時間：render_run_summary_image_compact（正本UI）を使用
#   - 見出し（divider/subheader）は意図的に出さない（必要時に静かに表示）
# - サムネは使わない（UI重複を避ける／保存にも関与しない）
# ============================================================

from __future__ import annotations

# ============================================================
# sys.path（common_lib を import できるように）
# ============================================================
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
APP_DIR = _THIS.parents[1]         # toolkit_app
PROJ_DIR = _THIS.parents[2]        # toolkit_project
MONO_ROOT = _THIS.parents[3]       # projects root

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PROJECTS_ROOT = MONO_ROOT
APP_NAME = APP_DIR.name
PAGE_NAME = _THIS.stem


# ============================================================
# 標準ライブラリ
# ============================================================
from io import BytesIO
from typing import Any
import datetime as dt
import sqlite3


# ============================================================
# 依存ライブラリ
# ============================================================
import streamlit as st
from PIL import Image


# ============================================================
# 正本：sessions（ログイン＋heartbeat）
# ============================================================
from common_lib.sessions.page_entry import page_session_heartbeat
from common_lib.ui.ui_basics import subtitle


# ============================================================
# 正本：AI routing（画像）
# ============================================================
from common_lib.ai.routing import edit_image  # type: ignore


# ============================================================
# 正本：AI model catalog / picker
# ============================================================
from common_lib.ai.models import IMAGE_MODEL_CATALOG, DEFAULT_IMAGE_MODEL_KEY
from common_lib.ui.model_picker import render_image_model_picker


# ============================================================
# 正本：busy（ai_runs.db）
# ============================================================
from common_lib.busy import busy_run


# ============================================================
# 正本：run summary（UI）
# ============================================================
from common_lib.ui.run_summary import render_run_summary_image_compact


# ============================================================
# ログ（JSONL）
# ============================================================
from common_lib.logs.jsonl_logger import JsonlLogger, sha256_short


# ============================================================
# Inbox へ保存（正本：common_lib.inbox.*）
# ============================================================
from common_lib.inbox.inbox_ops.ingest import ingest_to_inbox
from common_lib.inbox.inbox_common.types import (
    IngestRequest,
    InboxNotAvailable,
    QuotaExceeded,
    IngestFailed,
)


# ============================================================
# UI：バナー（任意）
# ============================================================
from common_lib.ui.banner_lines import render_banner_line_by_key


# ============================================================
# 定数
# ============================================================
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


# ============================================================
# 定数（モデル既定値）
# ============================================================
DEFAULT_MODEL_KEY = DEFAULT_IMAGE_MODEL_KEY


# ============================================================
# セッションキー（ページ専用）
# ============================================================
K_LAST_PNG = f"{PAGE_NAME}__last_png"
K_UPLOADED_PNG = f"{PAGE_NAME}__uploaded_png"

K_EDIT_PROMPT = f"{PAGE_NAME}__edit_prompt"

K_SIZE = f"{PAGE_NAME}__size"
K_MODEL_KEY = f"{PAGE_NAME}__image_model_key"
K_DL_NAME = f"{PAGE_NAME}__dl_name"
K_INBOX_FILENAME = f"{PAGE_NAME}__inbox_filename"

K_LAST_RUN_ID = f"{PAGE_NAME}__last_run_id"
K_HAS_TRIED = f"{PAGE_NAME}__has_tried"


# ============================================================
# session_state 初期化
# ============================================================
st.session_state.setdefault(K_LAST_PNG, b"")
st.session_state.setdefault(K_UPLOADED_PNG, b"")

st.session_state.setdefault(K_EDIT_PROMPT, "背景を夕焼けに、全体をシネマティックに")
st.session_state.setdefault(K_SIZE, "1024x1024")
st.session_state.setdefault(K_MODEL_KEY, DEFAULT_MODEL_KEY)

st.session_state.setdefault(K_DL_NAME, "")
st.session_state.setdefault(K_INBOX_FILENAME, "")

st.session_state.setdefault(K_LAST_RUN_ID, "")
st.session_state.setdefault(K_HAS_TRIED, False)


# ============================================================
# helper：model_key -> (provider, model)
# ============================================================
def _parse_model_key(model_key: str) -> tuple[str, str]:
    if ":" not in model_key:
        return ("openai", model_key.strip())

    p, m = model_key.split(":", 1)
    return (p.strip(), m.strip())


# ============================================================
# helper：Gemini availability
# ============================================================
def _gemini_available() -> bool:
    try:
        from google import genai  # type: ignore
        _ = genai
        return True
    except Exception:
        return False


# ============================================================
# ImageResult -> PNG bytes（URL取得に timeout）
# ============================================================
def _image_result_to_png_bytes(res, *, url_timeout_sec: float = 30.0) -> bytes:
    b = getattr(res, "image_bytes", None)
    if b:
        return bytes(b)

    url = getattr(res, "image_url", None)
    if url:
        import urllib.request
        import urllib.error

        try:
            with urllib.request.urlopen(str(url), timeout=float(url_timeout_sec)) as r:
                return r.read()
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"画像URLの取得に失敗しました（timeout={url_timeout_sec}秒）。URL={url} / error={e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"画像URLの取得中に予期しないエラーが発生しました（timeout={url_timeout_sec}秒）。URL={url} / error={e}"
            ) from e

    raise RuntimeError("画像が返ってきませんでした（image_bytes / image_url の両方なし）")


# ============================================================
# 画像ユーティリティ：bytes 正規化
# ============================================================
def _normalize_to_png_bytes(src_bytes: bytes) -> bytes:
    """
    入力 bytes（png/jpg 等）を RGBA PNG bytes に正規化して返す。
    """
    img = Image.open(BytesIO(src_bytes)).convert("RGBA")
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# ============================================================
# ロガー（JSONL）
# ============================================================
logger = JsonlLogger(
    projects_root=PROJECTS_ROOT,
    app_name=APP_NAME,
    page_name=PAGE_NAME,
    log_name=APP_NAME,
    rotate="monthly",
)

INCLUDE_FULL_PROMPT_IN_LOG = True


# ============================================================
# Inbox 画像選択（直接DB参照：last_viewed は更新しない）
# ============================================================
INBOX_PAGE_SIZE = 10
INBOX_ROOT = PROJECTS_ROOT / "InBoxStorages"

K_INBOX_PAGE = f"{PAGE_NAME}__inbox_page"
K_INBOX_SELECTED_ITEM = f"{PAGE_NAME}__inbox_selected_item"

st.session_state.setdefault(K_INBOX_PAGE, 0)


# ============================================================
# Inbox helper：user root
# ============================================================
def _inbox_user_root(user_sub: str) -> Path:
    return INBOX_ROOT / str(user_sub)


# ============================================================
# Inbox helper：items db path
# ============================================================
def _items_db_path(user_sub: str) -> Path:
    return _inbox_user_root(user_sub) / "_meta" / "inbox_items.db"


# ============================================================
# Inbox helper：画像一覧取得
# ============================================================
def _query_inbox_images_page(
    user_sub: str,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    db_path = _items_db_path(user_sub)

    if not db_path.exists():
        return [], 0

    con = sqlite3.connect(str(db_path))

    try:
        cur = con.cursor()

        cur.execute(
            "SELECT COUNT(1) FROM inbox_items WHERE kind = ?",
            ("image",),
        )

        total = int(cur.fetchone()[0] or 0)

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


# ============================================================
# Inbox helper：画像bytes読み込み
# ============================================================
def _load_inbox_image_as_png_bytes(
    user_sub: str,
    stored_rel: str,
) -> bytes:
    user_root = _inbox_user_root(user_sub)
    p = (user_root / stored_rel).resolve()

    if user_root.resolve() not in p.parents and p != user_root.resolve():
        raise ValueError("Invalid stored_rel (path traversal detected).")

    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    img = Image.open(p).convert("RGBA")
    out = BytesIO()
    img.save(out, format="PNG")

    return out.getvalue()


# ============================================================
# Inbox helper：選択クリア
# ============================================================
def _clear_inbox_selection() -> None:
    if K_INBOX_SELECTED_ITEM in st.session_state:
        st.session_state.pop(K_INBOX_SELECTED_ITEM, None)


# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="Image Maker / 画像修正",
    page_icon="🧪",
    layout="wide",
)

render_banner_line_by_key("pink_soft")


# ============================================================
# ログイン（heartbeat）
# ============================================================
sub = page_session_heartbeat(
    st,
    PROJECTS_ROOT,
    app_name=APP_NAME,
    page_name=PAGE_NAME,
)


# ============================================================
# タイトル + ログイン表示
# ============================================================
left, right = st.columns([2, 1])

with left:
    st.title("✏️🖼️ 画像修正")

with right:
    st.success(f"✅ ログイン中: **{sub}**")

subtitle("画像修正モデルをサイドバーで選択可能")


# ============================================================
# Sidebar：モデル選択＋サイズ選択（ボタン1組）
# ============================================================
with st.sidebar:
    # ------------------------------------------------------------
    # モデル選択
    # ------------------------------------------------------------
    model_key = render_image_model_picker(
        title="🧠 画像修正モデル",
        catalog=IMAGE_MODEL_CATALOG,
        session_key=K_MODEL_KEY,
        default_key=DEFAULT_MODEL_KEY,
        page_name=PAGE_NAME,
        gemini_available=_gemini_available(),
    )

    provider_image, model_image = _parse_model_key(model_key)

    st.divider()

    # ------------------------------------------------------------
    # サイズ（出力）
    # ------------------------------------------------------------
    st.header("サイズ（出力）")

    cur_size = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")

    r1c1, r1c2 = st.columns(2)

    with r1c1:
        if st.button("1024x1024", disabled=(cur_size == "1024x1024")):
            st.session_state[K_SIZE] = "1024x1024"
            st.rerun()

        if st.button("1536x1024", disabled=(cur_size == "1536x1024")):
            st.session_state[K_SIZE] = "1536x1024"
            st.rerun()

    with r1c2:
        if st.button("1024x1536", disabled=(cur_size == "1024x1536")):
            st.session_state[K_SIZE] = "1024x1536"
            st.rerun()

        if st.button("auto", disabled=(cur_size == "auto")):
            st.session_state[K_SIZE] = "auto"
            st.rerun()

    st.caption(f"現在: **{st.session_state.get(K_SIZE, '1024x1024')}**")


# ============================================================
# 1) 画像アップロード
# ============================================================
st.subheader("画像の読み込み")

uploaded = st.file_uploader(
    "PNG/JPG(JPEG) 画像を選択してください",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=False,
)

c1, c2 = st.columns([1, 1])

with c1:
    reset_clicked = st.button("🔁 リセット（画像クリア）")

with c2:
    use_uploaded_clicked = st.button("⬆️ アップロード画像を読み込む")

if reset_clicked:
    st.session_state[K_UPLOADED_PNG] = b""
    st.session_state[K_LAST_PNG] = b""
    st.session_state[K_HAS_TRIED] = False

    st.success("状態をリセットしました。")

    logger.append(
        {
            "user": str(sub),
            "action": "reset",
        }
    )

if use_uploaded_clicked:
    st.session_state[K_HAS_TRIED] = True

    if uploaded is None:
        st.warning("先に画像ファイルを選択してください。")
    else:
        try:
            raw = uploaded.getvalue()
            png_bytes = _normalize_to_png_bytes(raw)

            st.session_state[K_UPLOADED_PNG] = png_bytes
            st.session_state[K_LAST_PNG] = png_bytes

            st.success("アップロード画像を読み込みました。")

            logger.append(
                {
                    "user": str(sub),
                    "action": "upload_loaded",
                    "filename": getattr(uploaded, "name", None),
                    "size_bytes": len(png_bytes),
                }
            )

        except Exception as e:
            st.error(f"画像の読み込みに失敗しました: {e}")


# ============================================================
# 1-b) Inbox から読み込む（任意）
# ============================================================
use_inbox = st.toggle(
    "📥 Inbox から読み込む（画像のみ）",
    value=False,
)

if use_inbox:
    if not INBOX_ROOT.exists():
        st.info(f"InBoxStorages が見つかりません: {INBOX_ROOT}")

    else:
        page_index = int(st.session_state.get(K_INBOX_PAGE, 0))
        offset = page_index * INBOX_PAGE_SIZE

        rows, total = _query_inbox_images_page(
            user_sub=str(sub),
            limit=INBOX_PAGE_SIZE,
            offset=offset,
        )

        if total <= 0 or not rows:
            st.caption("Inbox に画像がありません（kind=image）。")

        else:
            last_page = max(0, (total - 1) // INBOX_PAGE_SIZE)

            if page_index > last_page:
                page_index = last_page
                st.session_state[K_INBOX_PAGE] = last_page
                offset = page_index * INBOX_PAGE_SIZE

                rows, total = _query_inbox_images_page(
                    user_sub=str(sub),
                    limit=INBOX_PAGE_SIZE,
                    offset=offset,
                )

            nav1, nav2, nav3, nav4 = st.columns([1, 1, 3.2, 4.8])

            with nav1:
                if st.button(
                    "⬅ 前へ",
                    disabled=(page_index <= 0),
                    key=f"{PAGE_NAME}__inbox_prev",
                ):
                    st.session_state[K_INBOX_PAGE] = max(page_index - 1, 0)
                    _clear_inbox_selection()
                    st.rerun()

            with nav2:
                if st.button(
                    "次へ ➡",
                    disabled=(page_index >= last_page),
                    key=f"{PAGE_NAME}__inbox_next",
                ):
                    st.session_state[K_INBOX_PAGE] = min(page_index + 1, last_page)
                    _clear_inbox_selection()
                    st.rerun()

            with nav3:
                start = offset + 1
                end = min(offset + INBOX_PAGE_SIZE, total)
                st.caption(
                    f"件数: {total}　／　ページ: {page_index + 1} / {last_page + 1}"
                    f"　（表示レンジ：{start}–{end}）"
                )

            with nav4:
                st.caption("※ ページ移動時は選択がクリアされます（事故防止）")

            options = [r["item_id"] for r in rows]
            label_map = {
                r["item_id"]: (r["original_name"] or r["item_id"])
                for r in rows
            }

            def _fmt_item_id(x: str) -> str:
                return label_map.get(str(x), str(x))

            selected_item_id = st.radio(
                "画像を選択（original_name）",
                options=options,
                index=None,
                format_func=_fmt_item_id,
                key=K_INBOX_SELECTED_ITEM,
            )

            cbtn1, cbtn2 = st.columns([2, 8])

            with cbtn1:
                load_inbox_clicked = st.button(
                    "📥 Inbox 画像を読み込む",
                    key=f"{PAGE_NAME}__load_from_inbox",
                )

            with cbtn2:
                st.caption("※ 押すとアップロード読み込みと同じ挙動で、修正元にセットされます。")

            if load_inbox_clicked:
                st.session_state[K_HAS_TRIED] = True

                if not selected_item_id:
                    st.warning("先に Inbox の画像を選択してください。")

                else:
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
                                user_sub=str(sub),
                                stored_rel=str(picked.get("stored_rel") or ""),
                            )

                            st.session_state[K_UPLOADED_PNG] = png_bytes
                            st.session_state[K_LAST_PNG] = png_bytes

                            st.success("Inbox 画像を読み込みました。")

                            logger.append(
                                {
                                    "user": str(sub),
                                    "action": "inbox_loaded",
                                    "item_id": str(picked.get("item_id") or ""),
                                    "original_name": str(picked.get("original_name") or ""),
                                    "size_bytes": len(png_bytes),
                                }
                            )

                            st.rerun()

                        except Exception as e:
                            st.error(f"Inbox 画像の読み込みに失敗しました: {e}")


# ============================================================
# 現在の元画像（修正対象）
# ============================================================
current_png = st.session_state.get(K_LAST_PNG, b"")
has_tried = bool(st.session_state.get(K_HAS_TRIED, False))

if not current_png:
    if has_tried:
        st.info("画像が未設定です。上で画像をアップロード（またはInboxから読み込み）してください。")

    st.stop()

st.subheader("現在の処理対象画像（修正元）")
st.image(current_png, caption="現在の元画像")


# ============================================================
# 2) 修正（連続）
# ============================================================
st.divider()
st.subheader("画像の修正（何度でも繰り返し可能）")

edit_prompt = st.text_area(
    "修正内容（プロンプト）",
    value=st.session_state.get(K_EDIT_PROMPT, ""),
    height=120,
    help="例：被写界深度を浅く、フィルム調、雨の夜、暖色トーン…など",
)

st.session_state[K_EDIT_PROMPT] = edit_prompt

size_now = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")
st.caption(f"サイズ（次の修正に適用）: **{size_now}**")

if st.button("🪄 修正版を生成する", type="primary"):
    st.session_state[K_HAS_TRIED] = True

    ep = (edit_prompt or "").strip()

    if not ep:
        st.warning("修正内容を入力してください。")
        st.stop()

    base_png = st.session_state.get(K_LAST_PNG, b"")

    if not base_png:
        st.warning("修正する元画像がありません。上で画像を読み込んでください。")
        st.stop()

    size_now = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")

    # ------------------------------------------------------------
    # 選択中の画像モデルを取得
    # ------------------------------------------------------------
    model_key = str(st.session_state.get(K_MODEL_KEY) or DEFAULT_MODEL_KEY)
    provider_image, model_image = _parse_model_key(model_key)

    if not provider_image or not model_image:
        st.error(f"画像モデル指定が不正です: {model_key}")
        st.stop()

    # ------------------------------------------------------------
    # busy（ai_runs.db）：修正
    # ------------------------------------------------------------
    try:
        with busy_run(
            projects_root=PROJECTS_ROOT,
            user_sub=str(sub),
            app_name=str(APP_NAME),
            page_name=str(PAGE_NAME),
            task_type="image",
            provider=str(provider_image),
            model=str(model_image),
            meta={
                "feature": "image_edit_upload_template",
                "action": "edit",
                "size": str(size_now),
                "prompt_chars": len(ep),
                "has_base_image": True,
                "base_image_bytes": int(len(base_png)),
            },
            usd_jpy=None,
        ) as br:
            with st.spinner("修正版を生成中…"):
                res2 = edit_image(
                    provider=str(provider_image),
                    model=str(model_image),
                    prompt=str(ep),
                    image_bytes=bytes(base_png),
                    size=str(size_now),
                    extra=None,
                )

            out_bytes = _image_result_to_png_bytes(res2)

            br.add_finish_meta(note="ok_edit")

            st.session_state[K_LAST_RUN_ID] = br.run_id

    except Exception as e:
        st.error(f"画像修正に失敗: {e}")
        st.stop()

    # ------------------------------------------------------------
    # 連続修正：修正版を次の元画像へ
    # ------------------------------------------------------------
    st.session_state[K_LAST_PNG] = out_bytes

    # ------------------------------------------------------------
    # JSONL ログ
    # ------------------------------------------------------------
    logger.append(
        {
            "user": str(sub),
            "action": "edit",
            "provider": str(provider_image),
            "model": str(model_image),
            "size": str(size_now),
            "prompt_hash": sha256_short(ep),
            **({"prompt": ep} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
        }
    )

    st.success("修正版を生成しました（これが次の修正元になります）。")
    st.image(out_bytes, caption="修正版（次の元画像）")


# ============================================================
# 3) 保存（ダウンロード）
# ============================================================
st.divider()
st.subheader("画像の保存（ダウンロード）")

png_bytes = st.session_state.get(K_LAST_PNG, b"")

default_name = f"edited_{dt.datetime.now(JST):%Y%m%d_%H%M%S}.png"

if not st.session_state.get(K_DL_NAME):
    st.session_state[K_DL_NAME] = default_name

dl_name = st.text_input(
    "ファイル名（ダウンロード用）",
    key=K_DL_NAME,
)

st.download_button(
    "⬇️ 修正画像を保存（.png）",
    data=png_bytes,
    file_name=dl_name,
    mime="image/png",
)


# ============================================================
# 4) Inbox へ保存（正本）
# ============================================================
st.divider()
st.subheader("📥 Inbox へ保存")

if not st.session_state.get(K_INBOX_FILENAME):
    st.session_state[K_INBOX_FILENAME] = dl_name

inbox_filename = st.text_input(
    "Inbox に保存するファイル名",
    key=K_INBOX_FILENAME,
    help="Inbox に保存されるファイル名です（.png 推奨）",
)

if st.button("📥 この画像を Inbox に保存", type="primary"):
    try:
        _png = bytes(st.session_state.get(K_LAST_PNG, b""))

        if not _png:
            st.warning("保存する画像がありません。先に修正を行ってください。")
            st.stop()

        _ = ingest_to_inbox(
            projects_root=PROJECTS_ROOT,
            req=IngestRequest(
                user_sub=str(sub),
                filename=str(inbox_filename),
                data=_png,
                tags_json='["toolkit/image_edit"]',
                origin={
                    "app": str(APP_NAME),
                    "page": str(PAGE_NAME),
                    "action": "image_edit",
                },
            ),
        )

        st.success("Inbox に保存しました。")

    except InboxNotAvailable:
        st.error("❌ Inbox が存在しません。ストレージ接続を確認してください。")

    except QuotaExceeded as e:
        st.error(f"❌ 容量オーバーです。現在={e.current} / 追加={e.incoming} / 上限={e.quota}")

    except IngestFailed as e:
        st.error(f"❌ Inbox への保存に失敗しました: {e}")


# ============================================================
# busy（ai_runs.db）：直近 run の開始/終了/経過時間（表示）
# ------------------------------------------------------------
# 意図的に「見出し」は出さない。必要なときだけ静かに表示。
# ============================================================
last_run_id = str(st.session_state.get(K_LAST_RUN_ID, "") or "").strip()

if not last_run_id:
    st.info("まだ実行がありません（修正を実行すると表示されます）。")

else:
    current_model_key = str(
        st.session_state.get(K_MODEL_KEY) or DEFAULT_MODEL_KEY
    )

    _, current_model = _parse_model_key(current_model_key)

    render_run_summary_image_compact(
        projects_root=PROJECTS_ROOT,
        run_id=last_run_id,
        model=str(current_model),
        cost=None,
        note="",
        show_divider=False,
    )