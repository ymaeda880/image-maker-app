# lib/openai_client.py
from __future__ import annotations
from openai import OpenAI
import streamlit as st

def get_client() -> OpenAI:
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        st.error("`.streamlit/secrets.toml` の OPENAI_API_KEY が見つかりません。")
        st.stop()
    return OpenAI(api_key=api_key)
