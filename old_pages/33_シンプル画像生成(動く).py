# pages/22_シンプル画像生成.py
# ============================================================
# 🧪 最小サンプル：gpt-image-1 で画像生成（1枚のみ）
# - プロンプト + サイズのみ
# - n=1 固定（最小構成）
# - b64 / URL どちらにも対応
# ============================================================

from __future__ import annotations
from io import BytesIO
import base64
from typing import Dict, Any

import streamlit as st
from PIL import Image
from openai import OpenAI
import tempfile

from lib.openai_client import get_client
from lib.image_utils import pil_to_png_bytes, url_to_png_bytes

# --------------------- ページ設定 ---------------------
st.set_page_config(page_title="最小：画像生成（1枚）", page_icon="🧪", layout="wide")
st.title("🧪 最小：画像生成（gpt-image-1, 1枚固定）")

# --------------------- クライアント ---------------------
client: OpenAI = get_client()

# --------------------- セッション初期化 ---------------------
st.session_state.setdefault("simple_last_png", b"")

# --------------------- 入力フォーム ---------------------
prompt = st.text_area(
    "プロンプト",
    placeholder="例）雨上がりの路地、ネオンの反射、映画的、シネマティック",
    height=120,
)
size = st.selectbox(
    "サイズ",
    ["1024x1024", "1024x1536", "1536x1024", "auto"],
    index=0,
)
submit = st.button("生成する", use_container_width=True)

# --------------------- 画像生成 ---------------------
if submit:
    if not prompt.strip():
        st.warning("プロンプトを入力してください。")
        st.stop()

    kwargs: Dict[str, Any] = {"model": "gpt-image-1", "prompt": prompt.strip(), "n": 1}
    if size != "auto":
        kwargs["size"] = size

    with st.spinner("生成中…"):
        try:
            res = client.images.generate(**kwargs)
        except Exception as e:
            st.error(f"生成に失敗しました: {e}")
            st.stop()

    data_list = getattr(res, "data", []) or []
    if not data_list:
        st.error("画像データが返ってきませんでした。")
        st.stop()

    d = data_list[0]
    png_bytes = None

    if getattr(d, "b64_json", None):
        img = Image.open(BytesIO(base64.b64decode(d.b64_json))).convert("RGBA")
        png_bytes = pil_to_png_bytes(img)
        st.image(img, caption=f"生成結果（{size}）", use_container_width=True)
    elif getattr(d, "url", None):
        st.image(d.url, caption=f"生成結果（{size}）", use_container_width=True)
        try:
            png_bytes = url_to_png_bytes(d.url)
        except Exception as e:
            st.info(f"ダウンロード用の取得に失敗: {e}")
    else:
        st.error("画像データが取得できませんでした。")

    if png_bytes:
        st.session_state["simple_last_png"] = png_bytes
        st.download_button(
            "PNGでダウンロード",
            data=png_bytes,
            file_name="simple_image.png",
            mime="image/png",
            use_container_width=True,
        )

# --------------------- 下段：直近の画像表示 ---------------------
st.divider()
st.subheader("直近の生成画像（1枚）")
if st.session_state.get("simple_last_png"):
    st.image(st.session_state["simple_last_png"], caption="最新の生成結果", use_container_width=True)
else:
    st.info("まだ画像がありません。上のプロンプトから生成してください。")



# ============================================================
# 修正
# ============================================================
st.divider()
st.subheader("直近の生成画像を修正")

if st.session_state.get("simple_last_png"):
    st.image(st.session_state["simple_last_png"], caption="元画像", use_container_width=True)
    edit_prompt = st.text_area("修正内容を入力", value="背景を夕焼けに、全体をシネマティックに", height=100)
    edit_size = st.selectbox("修正後のサイズ", ["1024x1024", "1024x1536", "1536x1024"], index=0)

    if st.button("修正版を生成する", use_container_width=True):
        if not edit_prompt.strip():
            st.warning("修正内容を入力してください。")
            st.stop()

        with st.spinner("修正版を生成中..."):
            # BytesIO → 一時ファイルとして渡す（OpenAI API用）
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
                out_bytes = BytesIO()
                img2.save(out_bytes, format="PNG")
                png_bytes = out_bytes.getvalue()
            elif getattr(datum, "url", None):
                png_bytes = url_to_png_bytes(datum.url)
            else:
                st.error("修正結果がありません。")
                st.stop()

            st.session_state["simple_last_png"] = png_bytes
            st.image(png_bytes, caption="修正版", use_container_width=True)

else:
    st.info("まだ画像がありません。上で生成してから修正してください。")



# ====修正======
st.divider()
st.subheader("直近の生成画像（1枚）")
if st.session_state.get("simple_last_png"):
    st.image(st.session_state["simple_last_png"], caption="最新の生成結果", use_container_width=True)
else:
    st.info("まだ画像がありません。上のプロンプトから生成してください。")
