# lib/session_bridge.py
from __future__ import annotations
import streamlit as st

EDIT_PAGE_PATH = "pages/02_画像修正.py"

def consume_goto_hook() -> None:
    """01ページ先頭で呼ぶ。rerunフラグがあれば02へ遷移。"""
    if st.session_state.get("_goto_edit_page"):
        st.session_state.pop("_goto_edit_page", None)
        try:
            st.switch_page(EDIT_PAGE_PATH)
        except Exception:
            st.warning("自動遷移に失敗しました。下のリンクから『02_画像修正』へ移動してください。")
            st.page_link(EDIT_PAGE_PATH, label="➡ 02_画像修正へ移動", width="content")

def send_image_bytes_and_go(png_bytes: bytes, *, size: str, model: str, prompt: str) -> None:
    """画像PNGバイトとメタをセッションへ保存 → rerun → consume_goto_hook で02へ。"""
    st.session_state["edit_src_bytes"] = png_bytes
    st.session_state["edit_src_size"] = size
    st.session_state["edit_src_model"] = model
    st.session_state["edit_src_prompt"] = prompt
    st.session_state["_goto_edit_page"] = True
    st.rerun()

def clear_edit_payload() -> None:
    for k in ["edit_src_bytes", "edit_src_kind", "edit_src_data",
              "edit_src_size", "edit_src_model", "edit_src_prompt"]:
        if k in st.session_state:
            del st.session_state[k]
