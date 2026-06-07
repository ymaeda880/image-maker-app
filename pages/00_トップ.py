# -*- coding: utf-8 -*-
# image_maker_app/pages/00_トップ.py
# ============================================================
# Image Maker top page
#
# 機能：
# - Image Maker のトップページ
# - ログイン状態表示
# - アプリ概要、料金目安、使い方の表示
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
import sys

import streamlit as st


# ============================================================
# パス設定
# ============================================================
_THIS = Path(__file__).resolve()

APP_DIR = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
MONO_ROOT = _THIS.parents[3]

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PROJECTS_ROOT = MONO_ROOT
APP_NAME = APP_DIR.name
PAGE_NAME = _THIS.stem


# ============================================================
# common_lib imports
# ============================================================
from common_lib.sessions.app_entry import app_session_heartbeat
from common_lib.ui.banner_lines import render_banner_line_by_key
from common_lib.ui.intro_panel import (
    render_hero_panel,
    render_intro_css,
    render_two_column_cards,
)
from common_lib.ui.theme_colors import get_theme_colors_from_banner_key
from common_lib.ui.ui_basics import subtitle


# ============================================================
# theme / banner
# ============================================================
BANNER_KEY = "pink_soft"

render_banner_line_by_key(BANNER_KEY)

theme = get_theme_colors_from_banner_key(BANNER_KEY)
render_intro_css(theme)


# ============================================================
# session heartbeat
# ============================================================
sub = app_session_heartbeat(
    st,
    PROJECTS_ROOT,
    app_name=APP_NAME,
)


# ============================================================
# ヘッダ
# ============================================================
left, right = st.columns([2, 1])

with left:
    st.title("🖼️ Image Maker")

with right:
    st.success(f"✅ ログイン中: **{sub}**")

subtitle("画像生成：画像を生成するAIスタジオ")


# ============================================================
# short description
# ============================================================
st.caption("Generate・Edit・Refine・Template — all in one creative workspace.")

st.markdown(
    """
左サイドバーのメニューから、利用したい機能を選択してください。  
まずは **画像生成** ページからお試しください。
"""
)


# ============================================================
# hero
# ============================================================
render_hero_panel(
    kicker="IMAGE MAKER",
    title="アイデアを、すばやく画像に。画像を、もっと使いやすく。",
    body_html="""
<span class="ts-highlight">Image Maker</span> は、
画像生成・画像修正・プロンプト活用をまとめて扱うための
AIクリエイティブスタジオです。<br>

左サイドバーから目的に応じた機能を選び、
まずは
<span class="ts-highlight">画像生成</span>
ページをお試しください。
""",
    chips=[
        "Generate",
        "Edit",
        "Prompt",
        "Refine",
    ],
)


# ============================================================
# info cards
# ============================================================
render_two_column_cards(
    left_title="🚧 現在も開発中です",
    left_body_html="""
本アプリケーションは、
皆様の業務効率を高めることを目的として、
継続的に改良を進めています。<br><br>

気づいた点・改善してほしい点・不具合などがありましたら、
ぜひフィードバックをお寄せください。
""",
    right_title="🎨 画像生成・画像修正に対応します",
    right_body_html="""
プロンプトから画像を生成したり、
既存画像を目的に合わせて修正したりできます。<br><br>

今後は、画像修正用プロンプトのテンプレートも
整備していく予定です。
""",
)


# ============================================================
# cost / usage cards
# ============================================================
st.markdown(
    '<div style="height:24px;"></div>',
    unsafe_allow_html=True,
)

render_two_column_cards(
    left_title="💰 料金の目安",
    left_body_html="""
画像生成の料金は使用するモデルによって異なります。<br><br>

OpenAI gpt-image-1 は
<span class="ts-highlight">1枚あたり約25円</span>、
Gemini 2.5 Flash Image は
<span class="ts-highlight">1枚あたり約8円</span>
が目安です。<br><br>

大量に生成する場合は、枚数と用途を確認しながら利用してください。
""",
    right_title="🧭 使い方",
    right_body_html="""
画像を生成するときは、左サイドバーの
<span class="ts-highlight">画像生成</span>
を開いてください。<br><br>

画像を修正するときは、左サイドバーの
<span class="ts-highlight">画像修正</span>
を開いてください。
""",
)


# ============================================================
# expander
# ============================================================
st.markdown(
    '<div style="height:16px;"></div>',
    unsafe_allow_html=True,
)

with st.expander("使い方", expanded=False):
    st.markdown(
        """
1. 画像を生成するときは、「サイドバー」の **画像生成** から行ってください。
2. 画像を修正するときは、「サイドバー」の **画像修正** から行ってください。
3. プロンプトのテンプレートは、今後順次整備していく予定です。
"""
    )