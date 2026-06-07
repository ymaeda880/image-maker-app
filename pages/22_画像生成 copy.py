# -*- coding: utf-8 -*-
# toolkit_app/pages/22_画像生成.py
# ============================================================
# 🧪 テンプレ寄せ：画像生成＋何度でも修正（gpt-image-1）
#
# 方針（テンプレ準拠）
# - st.form 不使用 / use_container_width 不使用
# - ログイン：common_lib.sessions.page_entry.page_session_heartbeat（正本）
# - AI 呼び出し：common_lib.ai.routing（正本）経由（provider=openai 固定）
# - 画像：ImageResult（bytes / url）→ PNG bytes に統一して表示・連続修正
#   - url の場合は urllib で取得（timeout あり）
# - busy：common_lib.busy.busy_run（with）で ai_runs.db を必ず記録
# - ログ（任意）：JsonlLogger（app/page 自動付与、JST、monthly rotate）
# - 保存：DL + Inbox へ保存（common_lib.inbox.* 正本）
#
# テンプレ（104_画像生成.py）への寄せポイント（重要）
# - サイズ選択：sidebar のボタン式 + rerun（ボタンは「1組」）
#   -> ここで選択されたサイズが「次の生成（generate）と次の修正（edit）」の両方に使われる
# - 実行時間：render_run_summary_image_compact（正本UI）を使用
#   - 見出し（divider/subheader）は意図的に出さない（必要時に静かに表示）
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
import datetime as dt

# ============================================================
# 依存ライブラリ
# ============================================================
import streamlit as st

# ============================================================
# 正本：sessions（ログイン＋heartbeat）
# ============================================================
from common_lib.sessions.page_entry import page_session_heartbeat
from common_lib.ui.ui_basics import subtitle

# ============================================================
# 正本：AI routing（画像）
# ============================================================
from common_lib.ai.routing import generate_image, edit_image  # type: ignore

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
# 定数（固定）
# ============================================================
MODEL_IMAGE = "gpt-image-1"
PROVIDER_IMAGE = "openai"
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")

# ============================================================
# セッションキー（ページ専用）
# ============================================================
K_LAST_PNG = f"{PAGE_NAME}__last_png"
K_LAST_PROMPT = f"{PAGE_NAME}__last_prompt"
K_LAST_EDIT_PROMPT = f"{PAGE_NAME}__last_edit_prompt"
K_SIZE = f"{PAGE_NAME}__size"  # ★ 生成/修正 共通（ボタン1組）
K_DL_NAME = f"{PAGE_NAME}__dl_name"
K_LAST_RUN_ID = f"{PAGE_NAME}__last_run_id"
K_HAS_TRIED = f"{PAGE_NAME}__has_tried"  # 初回メッセージ抑制用
K_INBOX_FILENAME = f"{PAGE_NAME}__inbox_filename"

# ============================================================
# session_state 初期化
# ============================================================
st.session_state.setdefault(K_LAST_PNG, b"")
st.session_state.setdefault(K_LAST_PROMPT, "")
st.session_state.setdefault(K_LAST_EDIT_PROMPT, "背景を夕焼けに、全体をシネマティックに")
st.session_state.setdefault(K_SIZE, "1024x1024")
st.session_state.setdefault(K_DL_NAME, "")
st.session_state.setdefault(K_LAST_RUN_ID, "")
st.session_state.setdefault(K_HAS_TRIED, False)
st.session_state.setdefault(K_INBOX_FILENAME, "")

# ============================================================
# ImageResult -> PNG bytes（URL取得に timeout）
# ============================================================
def _image_result_to_png_bytes(res, *, url_timeout_sec: float = 30.0) -> bytes:
    """
    ImageResult:
      - image_bytes があればそれを優先
      - image_url の場合は取得して bytes にする（requests 不使用：urllib）
      - URL取得は「生成後の取得」なので、固まり防止のため timeout を入れる
    """
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
# ロガー（JSONL）
# ============================================================
logger = JsonlLogger(
    projects_root=PROJECTS_ROOT,
    app_name=APP_NAME,
    page_name=PAGE_NAME,
    log_name=APP_NAME,      # 例：toolkit_app_YYYY-MM.jsonl
    rotate="monthly",
)
INCLUDE_FULL_PROMPT_IN_LOG = True

# ============================================================
# ページ設定
# ============================================================
st.set_page_config(page_title="Image Maker / 画像生成", page_icon="🧪", layout="wide")
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
    st.title("🎨🖌️ 画像生成")
with right:
    st.success(f"✅ ログイン中: **{sub}**")

subtitle("using image-1")

# ============================================================
# Sidebar：サイズ選択（ボタン1組）＋操作
# ============================================================
with st.sidebar:
    # ------------------------------------------------------------
    # サイズ（生成/修正 共通）
    # ------------------------------------------------------------
    st.header("サイズ（共通）")
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

    # ------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------
    st.divider()
    st.header("操作")

    if st.button("🧹 画像をクリア"):
        st.session_state[K_LAST_PNG] = b""
        st.session_state[K_LAST_RUN_ID] = ""
        st.session_state[K_HAS_TRIED] = False
        st.rerun()

# ============================================================
# 生成 UI
# ============================================================
st.subheader("生成")

prompt = st.text_area(
    "生成プロンプト",
    value=st.session_state.get(K_LAST_PROMPT, ""),
    height=120,
    placeholder="例：春のオフィスで、複数の社員が同時にPCで業務アプリを使っているイラスト",
)
st.session_state[K_LAST_PROMPT] = prompt

size_now = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")
st.caption(f"画像サイズ: **{size_now}**")

# ============================================================
# 生成 実行
# ============================================================
if st.button("🎨 生成する", type="primary"):
    st.session_state[K_HAS_TRIED] = True

    p = (prompt or "").strip()
    if not p:
        st.warning("生成プロンプトを入力してください。")
        st.stop()

    size_now = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")

    try:
        with busy_run(
            projects_root=PROJECTS_ROOT,
            user_sub=str(sub),
            app_name=str(APP_NAME),
            page_name=str(PAGE_NAME),
            task_type="image",
            provider=str(PROVIDER_IMAGE),
            model=str(MODEL_IMAGE),
            meta={
                "feature": "image_generate_template",
                "action": "generate",
                "size": str(size_now),
                "prompt_chars": len(p),
            },
            usd_jpy=None,
        ) as br:
            with st.spinner("画像を生成中…"):
                res = generate_image(
                    provider=str(PROVIDER_IMAGE),
                    model=str(MODEL_IMAGE),
                    prompt=str(p),
                    size=str(size_now),
                    n=1,
                    extra=None,
                )

            png_bytes = _image_result_to_png_bytes(res)
            br.add_finish_meta(note="ok_generate")

            st.session_state[K_LAST_RUN_ID] = br.run_id

    except Exception as e:
        st.error(f"画像生成に失敗: {e}")
        st.stop()

    st.session_state[K_LAST_PNG] = png_bytes

    logger.append(
        {
            "user": str(sub),
            "action": "generate",
            "provider": str(PROVIDER_IMAGE),
            "model": str(MODEL_IMAGE),
            "size": str(size_now),
            "n": 1,
            "prompt_hash": sha256_short(p),
            **({"prompt": p} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
        }
    )

    st.success("生成しました。下で確認・修正できます。")

# ============================================================
# 現在画像の表示（初回はメッセージを出さない）
# ============================================================
st.divider()

png_bytes = st.session_state.get(K_LAST_PNG, b"")
has_tried = bool(st.session_state.get(K_HAS_TRIED, False))

if not png_bytes:
    if has_tried:
        st.info("まだ画像がありません。上で生成してください。")
    st.stop()

st.subheader("現在の画像（修正元）")
st.image(png_bytes, caption="現在の元画像")

# ============================================================
# 修正 UI
# ============================================================
st.subheader("修正（連続）")

edit_prompt = st.text_area(
    "修正内容（プロンプト）",
    value=st.session_state.get(K_LAST_EDIT_PROMPT, ""),
    height=120,
)
st.session_state[K_LAST_EDIT_PROMPT] = edit_prompt

size_now = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")
st.caption(f"画像サイズ: **{size_now}**")

# ============================================================
# 修正 実行
# ============================================================
if st.button("🖌️ 修正版を生成する（この修正内容を反映）", type="primary"):
    st.session_state[K_HAS_TRIED] = True

    ep = (edit_prompt or "").strip()
    if not ep:
        st.warning("修正内容を入力してください。")
        st.stop()

    size_now = str(st.session_state.get(K_SIZE, "1024x1024") or "1024x1024")

    try:
        with busy_run(
            projects_root=PROJECTS_ROOT,
            user_sub=str(sub),
            app_name=str(APP_NAME),
            page_name=str(PAGE_NAME),
            task_type="image",
            provider=str(PROVIDER_IMAGE),
            model=str(MODEL_IMAGE),
            meta={
                "feature": "image_generate_template",
                "action": "edit",
                "size": str(size_now),
                "prompt_chars": len(ep),
                "has_base_image": True,
                "base_image_bytes": int(len(png_bytes)),
            },
            usd_jpy=None,
        ) as br:
            with st.spinner("修正版を生成中…"):
                res2 = edit_image(
                    provider=str(PROVIDER_IMAGE),
                    model=str(MODEL_IMAGE),
                    prompt=str(ep),
                    image_bytes=bytes(png_bytes),
                    size=str(size_now),
                    extra=None,
                )

            out_bytes = _image_result_to_png_bytes(res2)
            br.add_finish_meta(note="ok_edit")

            st.session_state[K_LAST_RUN_ID] = br.run_id

    except Exception as e:
        st.error(f"画像修正に失敗: {e}")
        st.stop()

    st.session_state[K_LAST_PNG] = out_bytes

    logger.append(
        {
            "user": str(sub),
            "action": "edit",
            "provider": str(PROVIDER_IMAGE),
            "model": str(MODEL_IMAGE),
            "size": str(size_now),
            "prompt_hash": sha256_short(ep),
            **({"prompt": ep} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
        }
    )

    st.success("修正版を生成しました（これが次の修正元になります）。")
    st.image(out_bytes, caption="修正版（次の元画像）")

# ============================================================
# 保存（ダウンロード）
# ============================================================
st.divider()
st.subheader("💾 保存（ダウンロード）")

default_name = f"generated_{dt.datetime.now(JST):%Y%m%d_%H%M%S}.png"
if not st.session_state.get(K_DL_NAME):
    st.session_state[K_DL_NAME] = default_name

dl_name = st.text_input("ファイル名（ダウンロード用）", key=K_DL_NAME)

st.download_button(
    "⬇️ PNGをダウンロード",
    data=st.session_state.get(K_LAST_PNG, b""),
    file_name=dl_name,
    mime="image/png",
)

# ============================================================
# Inbox へ保存（正本）
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
        _ = ingest_to_inbox(
            projects_root=PROJECTS_ROOT,
            req=IngestRequest(
                user_sub=str(sub),
                filename=str(inbox_filename),
                data=bytes(st.session_state.get(K_LAST_PNG, b"")),
                tags_json='["toolkit/image_generate"]',
                origin={
                    "app": str(APP_NAME),
                    "page": str(PAGE_NAME),
                    "action": "image_generate_or_edit",
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
    st.info("まだ実行がありません（生成/修正を実行すると表示されます）。")
else:
    render_run_summary_image_compact(
        projects_root=PROJECTS_ROOT,
        run_id=last_run_id,
        model=str(MODEL_IMAGE),
        cost=None,
        note="",
        show_divider=False,
    )
