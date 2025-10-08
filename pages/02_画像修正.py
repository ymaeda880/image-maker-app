# pages/02_画像修正.py
from __future__ import annotations

from io import BytesIO
from typing import Optional

import streamlit as st
from PIL import Image
from openai import OpenAI

from lib.openai_client import get_client
from lib.image_utils import pil_open, pil_to_png_bytes, as_named_file
from lib.session_bridge import clear_edit_payload
from lib.ui import show_image, download_img_buttons

st.set_page_config(page_title="画像修正（inpainting/edit）", page_icon="🪄", layout="wide")

client: OpenAI = get_client()

def _get_session_image_if_any() -> Optional[Image.Image]:
    b = st.session_state.get("edit_src_bytes")
    if b:
        try:
            return Image.open(BytesIO(b)).convert("RGBA")
        except Exception:
            st.warning("セッションの画像バイトを開けませんでした。")
    return None

st.title("🪄 画像修正（inpainting / edit）")
with st.expander("💰 概算料金（1ドル=150円換算）"):
    st.markdown("""
**gpt-image-1（Images API）** 目安：**約 6〜25円 / 枚**  
**dall-e-2**（フォールバック）1024×1024：**約 3円 / 枚**
""")

st.markdown("元画像に対して、プロンプトで修正を加えます。必要に応じて **マスクPNG**（透明＝編集、非透明＝保持）も指定できます。")

prefill_img = _get_session_image_if_any()
prefill_prompt = st.session_state.get("edit_src_prompt", "")

if prefill_img is not None:
    st.success("『01_画像生成』から画像を受け取りました。アップロード無しでこのまま修正できます。")
    show_image(prefill_img, caption="受け取り画像（編集対象）", width="stretch")

st.markdown("---")

with st.form("edit_form", clear_on_submit=False):
    c0, c1 = st.columns([1, 1])
    with c0:
        src_file = st.file_uploader("🖼 元画像（PNG/JPG）", type=["png", "jpg", "jpeg"])
        mask_file = st.file_uploader("🎭 マスクPNG（任意・透明＝編集、非透明＝保持）", type=["png"])
    with c1:
        edit_prompt = st.text_area(
            "修正プロンプト",
            placeholder="例）背景を夕焼けに変更、人物の服を赤に、全体をシネマティックに",
            height=140,
            value=prefill_prompt,
        )
        size_label = st.selectbox(
            "サイズ（gpt-image-1 対応）",
            ["正方形 (1024x1024)", "縦長 (1024x1536)", "横長 (1536x1024)"],
            index=0,
        )
        label_to_size = {
            "正方形 (1024x1024)": "1024x1024",
            "縦長 (1024x1536)": "1024x1536",
            "横長 (1536x1024)": "1536x1024",
        }
        size = label_to_size[size_label]

    submitted = st.form_submit_button("修正を実行", width="stretch")

# プレビュー
if src_file and prefill_img is None:
    src_preview = pil_open(src_file)
    st.subheader("入力プレビュー")
    cc1, cc2 = st.columns([2, 1])
    with cc1:
        show_image(src_preview, caption="元画像", width="stretch")
    with cc2:
        if mask_file:
            mask_preview = pil_open(mask_file)
            show_image(mask_preview, caption="マスク（透明＝編集 / 不透明＝保持）", width="stretch")
        else:
            st.info("マスク未指定（全体を編集対象にします）")

st.markdown("---")

# 実行
if submitted:
    # 画像ソース
    if prefill_img is not None:
        src_img = prefill_img
        src_png_bytes = pil_to_png_bytes(src_img)
    else:
        if not src_file:
            st.warning("元画像がありません。アップロードするか、01ページからの受け渡しをご利用ください。")
            st.stop()
        src_img = pil_open(src_file)
        src_png_bytes = pil_to_png_bytes(src_img)

    if not edit_prompt.strip():
        st.warning("修正プロンプトを入力してください。")
        st.stop()

    # マスクは任意
    mask_png_bytes: Optional[bytes] = None
    if mask_file:
        mask_img = pil_open(mask_file)
        mask_png_bytes = pil_to_png_bytes(mask_img)

    with st.spinner("修正中…"):
        try:
            try_model = "gpt-image-1"
            kwargs = dict(model=try_model, prompt=edit_prompt.strip(), size=size)
            img_file = as_named_file(src_png_bytes, "image.png")
            if mask_png_bytes:
                mask_file_named = as_named_file(mask_png_bytes, "mask.png")
                res = client.images.edit(image=img_file, mask=mask_file_named, **kwargs)
            else:
                res = client.images.edit(image=img_file, **kwargs)
        except Exception as e1:
            msg = str(e1)
            if "must be verified" in msg or "403" in msg:
                try_model = "dall-e-2"
                st.info("フォールバック: `dall-e-2` は正方形のみ対応のため、サイズは 1024x1024 に変換します。")
                kwargs = dict(model=try_model, prompt=edit_prompt.strip(), size="1024x1024")
                img_file = as_named_file(src_png_bytes, "image.png")
                if mask_png_bytes:
                    mask_file_named = as_named_file(mask_png_bytes, "mask.png")
                    res = client.images.edit(image=img_file, mask=mask_file_named, **kwargs)
                else:
                    res = client.images.edit(image=img_file, **kwargs)
            else:
                st.error(f"Images API の編集に失敗しました: {e1}")
                st.stop()

    st.success(f"修正完了！（model: {try_model}）")
    data0 = res.data[0]
    out_img: Optional[Image.Image] = None
    if getattr(data0, "b64_json", None):
        out_img = Image.open(BytesIO(__import__("base64").b64decode(data0.b64_json))).convert("RGBA")
    elif getattr(data0, "url", None):
        show_image(data0.url, caption="修正結果（URL）", width="stretch")

    if out_img is not None:
        st.subheader("結果比較")
        a, b = st.columns(2)
        with a:
            show_image(src_img, caption="修正前（元画像）", width="stretch")
        with b:
            show_image(out_img, caption="修正後（結果）", width="stretch")
        st.markdown("#### ダウンロード")
        download_img_buttons(out_img, basename="edited_result")

    clear_edit_payload()
