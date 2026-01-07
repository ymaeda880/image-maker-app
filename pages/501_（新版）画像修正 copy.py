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

# # ヘッダー：タイトル + ログインバッジ
# left, right = st.columns([5, 2], vertical_alignment="center")
# with left:
#     st.title("✏️🖼️ 画像修正")
# with right:
#     user, _payload = get_current_user_from_session_or_cookie(st)
#     if user:
#         st.success(f"ログイン中: **{user}**")
#     else:
#         st.warning("未ログイン（Cookie 未検出）")

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
else:
    st.info("保存できる画像がありません。上で修正を実行してください。")
