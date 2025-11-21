# pages/23_（新版）画像修正.py
# ============================================================
# 🧪 画像アップロード → 何度でも修正（gpt-image-1）
# + ログイン表示（common_lib/auth/auth_helpers.py）
# + ログ（upload/reset/edit を JSONL に保存, JST, app_name/page_name 自動付与）
# + ログファイルは logs/{app_name}.log.jsonl（共通ロガー）
# ============================================================

from __future__ import annotations
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
# ★ 共通JSONLロガー
from common_lib.logs.jsonl_logger import JsonlLogger, sha256_short

# --------------------- ページ設定 ---------------------
st.set_page_config(page_title="画像アップロード→修正", page_icon="🧪", layout="wide")

# ヘッダー：タイトル + ログインバッジ
left, right = st.columns([5, 2], vertical_alignment="center")
with left:
    st.title("🧪 アップロード画像を修正")
with right:
    user, _payload = get_current_user_from_session_or_cookie(st)
    if user:
        st.success(f"ログイン中: **{user}**")
    else:
        st.warning("未ログイン（Cookie 未検出）")

# --------------------- ロガー初期化（logs/{app_name}.log.jsonl） ---------------------
APP_DIR = Path(__file__).resolve().parents[1]
PAGE_NAME = Path(__file__).stem
logger = JsonlLogger(app_dir=APP_DIR, page_name=PAGE_NAME)

INCLUDE_FULL_PROMPT_IN_LOG = True
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")

# --------------------- クライアント & セッション ---------------------
client: OpenAI = get_client()
st.session_state.setdefault("simple_last_png", b"")  # 現在の修正対象PNG（常に最新）
st.session_state.setdefault("uploaded_png", b"")     # アップロード直後のPNG（初期元画像）

# ============================================================
# 1) 画像アップロード
# ============================================================
st.subheader("1) 画像をアップロード")
uploaded = st.file_uploader(
    "PNG/JPG(JPEG) 画像を選択してください",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=False
)

col_up1, col_up2 = st.columns([1,1])
with col_up1:
    reset_clicked = st.button("🔁 リセット（画像クリア）", width="stretch")
with col_up2:
    use_uploaded_clicked = st.button("⬆️ アップロード画像を読み込む", width="stretch")

if reset_clicked:
    st.session_state["uploaded_png"] = b""
    st.session_state["simple_last_png"] = b""
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
            st.session_state["uploaded_png"] = png_bytes
            st.session_state["simple_last_png"] = png_bytes  # 初期の修正対象に昇格
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
current_png = st.session_state.get("simple_last_png", b"")
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
    if not st.session_state.get("simple_last_png"):
        st.warning("修正する元画像がありません。アップロード→読み込みを行ってください。")
        st.stop()

    with st.spinner("修正版を生成中..."):
        # 一時ファイルにPNGを書き出して images.edit へ
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(st.session_state["simple_last_png"])
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
            st.error("修正結果が取得できませんでした。"); st.stop()

        # 🔁 修正版を再び元画像に昇格（連続修正OK）
        st.session_state["simple_last_png"] = out_bytes

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

png_bytes = st.session_state.get("simple_last_png", b"")
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
        "⬇️ ブラウザに保存（.png）",
        data=png_bytes,
        file_name=dl_name,
        mime="image/png",
        width="stretch",
    )
else:
    st.info("保存できる画像がありません。上で修正を実行してください。")
