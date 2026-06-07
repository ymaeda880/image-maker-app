# image_maker_app/app.py
"""
🎨 image_maker_app（ポータルログイン誘導付き）

目的
----
- この app.py は「入口ページ」。
- 未ログインでも画面は表示する（ブロックしない）。
- ただし未ログインなら「ポータルでログインして」と警告し、
  可能ならポータルへのリンク（/ or /portal 等）を案内する。

設計方針
--------
- 認証判定は common_lib に一本化（Cookie/JWT/session復元）
- app.py 側は「誰がログイン中か？」を関数で聞くだけ
- Cookie の set/delete（ログイン/ログアウト）はこのアプリでは行わない
"""

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import sys
from pathlib import Path

import streamlit as st


# ============================================================
# sys.path（設計上の確定事項）※ import より先に必ず実行
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parent
APP_NAME = APP_ROOT.name
PROJECTS_ROOT = _THIS.parents[2]

if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))


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
# 基本設定
# ============================================================
st.set_page_config(
    page_title="Image Maker",
    page_icon="🎨",
    layout="wide",
)


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


# # ============================================================
# # expander
# # ============================================================
# with st.expander("使い方", expanded=False):
#     st.markdown(
#         """
# 1. 画像を生成するときは、「サイドバー」の **画像生成** から行ってください。
# 2. 画像を修正するときは、「サイドバー」の **画像修正** から行ってください。
# 3. プロンプトのテンプレートは、今後順次整備していく予定です。
# """
#     )

# ============================================================
# intro message
# ============================================================
render_hero_panel(
    kicker="IMAGE MAKER",
    title="アイデアを、すばやく画像に。画像を、もっと使いやすく。",
    body_html='<span class="ts-highlight">Image Maker</span> は、画像生成・画像修正・プロンプト活用をまとめて扱うためのAIクリエイティブスタジオです。<br>左サイドバーから目的に応じた機能を選び、まずは <span class="ts-highlight">画像生成</span> ページをお試しください。',
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
    left_body_html="本アプリケーションは、皆様の業務効率を高めることを目的として、継続的に改良を進めています。<br><br>気づいた点・改善してほしい点・不具合などがありましたら、ぜひフィードバックをお寄せください。",
    right_title="🎨 画像生成・画像修正に対応します",
    right_body_html="プロンプトから画像を生成したり、既存画像を目的に合わせて修正したりできます。<br><br>今後は、画像修正用プロンプトのテンプレートも整備していく予定です。",
)


# ============================================================
# cost / usage cards
# ============================================================
#st.divider()
st.markdown(
    '<div style="height:24px;"></div>',
    unsafe_allow_html=True,
)

render_two_column_cards(
    left_title="💰 料金の目安",
    left_body_html="画像生成の料金は使用するモデルによって異なります。<br><br>OpenAI gpt-image-1 は1枚あたり25円、Gemini 2.5 Flash Image は1枚あたり8円が目安です。<br><br>大量に生成する場合は、枚数と用途を確認しながら利用してください。",
    right_title="🧭 使い方",
    right_body_html="画像を生成するときは、左サイドバーの <span class=\"ts-highlight\">画像生成</span> を開いてください。<br><br>画像を修正するときは、左サイドバーの <span class=\"ts-highlight\">画像修正</span> を開いてください。",
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