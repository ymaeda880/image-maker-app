# lib/ui.py
from __future__ import annotations
from io import BytesIO
from PIL import Image
import streamlit as st

def show_image(img_or_url, *, caption: str | None = None, width: str = "stretch") -> None:
    """st.image の薄いラッパ（width='stretch' / 'content'）。"""
    st.image(img_or_url, caption=caption, width=width)

def download_img_buttons(img: Image.Image, basename: str) -> None:
    """PNG/WEBP のDLボタン（幅APIを width= に置換）。"""
    # PNG
    png_buf = BytesIO()
    img.save(png_buf, format="PNG")
    st.download_button(
        "PNGでダウンロード",
        data=png_buf.getvalue(),
        file_name=f"{basename}.png",
        mime="image/png",
        width="stretch",
    )
    # WEBP
    webp_buf = BytesIO()
    img.save(webp_buf, format="WEBP")
    st.download_button(
        "WEBPでダウンロード",
        data=webp_buf.getvalue(),
        file_name=f"{basename}.webp",
        mime="image/webp",
        width="stretch",
    )
