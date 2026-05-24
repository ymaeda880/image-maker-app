# app.py（image_maker_app）
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

from pathlib import Path
import sys

import streamlit as st

# ============================================================
# sys.path（設計上の確定事項）※ import より先に必ず実行
#   /Users/macmini2025/projects/image_maker_project/image_maker_app/app.py
#   -> parents[2] = /Users/macmini2025/projects
# ============================================================
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parent
APP_NAME = APP_ROOT.name                  # ← app_name を自動取得
PROJECTS_ROOT = _THIS.parents[2]

if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ============================================================
# common_lib（認証は common_lib に一本化）
# ============================================================
from common_lib.sessions.app_entry import app_session_heartbeat
from common_lib.ui.ui_basics import subtitle
from common_lib.ui.banner_lines import render_banner_line_by_key

# ============================================================
# 基本設定（最初に1回だけ）
# ============================================================
st.set_page_config(page_title="Image Maker", page_icon="🎨", layout="wide")
render_banner_line_by_key("pink_soft")

# ============================================================
# ヒーローバナー（app.py 最上部）
# ============================================================
# BANNER_PATH = (
#     PROJECTS_ROOT
#     / "image_maker_project"
#     / "image_maker_app"
#     / "assets"
#     / "image_maker_banner_1600x320.png"
# )

# if BANNER_PATH.exists():
#     st.image(
#         str(BANNER_PATH),
#         width="stretch",   # use_container_width は使わない方針
#     )

sub = app_session_heartbeat(
    st,
    PROJECTS_ROOT,
    app_name=APP_NAME,
)

left, right = st.columns([2, 1])
with left:
    st.title("🖼️ Image Maker")
with right:
    st.success(f"✅ ログイン中: **{sub}**")
subtitle("AI Creative Studio")



# ============================================================
# 本文（ログイン済み / 未ログイン共通で表示してよい内容）
# ============================================================
st.markdown(
    """
左サイドバーのメニューから、利用したい機能を選択してください。  
まずは **画像生成** ページからお試しください。
"""
)

st.markdown(
    """
## 🚧 このアプリケーションは現在 **開発中** です

本アプリケーションシステム **Image Maker** は、皆様の業務効率を高めることを目的として、継続的に改良を進めています。
実際にご利用いただき、**気づいた点・改善してほしい点・不具合** などについて、ぜひフィードバックをお寄せください。

いただいたご意見をもとにプログラムの改善を行い、より使いやすく、業務に役立つツールへと発展させてまいります。

また、画像修正に使うプロンプトのテンプレートなども今後整備していく予定です。
「こんなプロンプトが欲しい」「こういう使い方がしたい」などのご提案も大歓迎です。

ご協力のほど、どうぞよろしくお願いいたします。
"""
)

st.divider()

# ============================================================
# 料金表示（そのまま）
# ============================================================
st.markdown("１枚約25円かかります．")

st.markdown(
    """
このアプリでは、**プロンプト**を入力して OpenAI GPT-image-1 で画像を生成できます。  
左の「サイドバー」から **『画像生成』** を開いてください。
"""
)

with st.expander("使い方", expanded=False):
    st.markdown(
        """
1. 画像を生成するときは，「サイドバー」の『画像生成』から行ってください．
2. 画像を修正するときは，「サイドバー」の『画像修正』から行ってください．
"""
    )
