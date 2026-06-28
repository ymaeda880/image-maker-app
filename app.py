# -*- coding: utf-8 -*-
# image_maker_app/app.py
# ============================================================
# Image Maker app entry
#
# 機能：
# - st.navigation によるページ構成
# - トップページ / 画像生成 / 画像修正 / 利用履歴 / 管理者ログ / ポータル戻り
# - copy ファイルや区切り用ファイルは navigation から除外
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from pathlib import Path
import sys

import streamlit as st


# ============================================================
# パス設定（app.py 用）
# ============================================================
_THIS = Path(__file__).resolve()

APP_DIR = _THIS.parent
PROJ_DIR = _THIS.parents[1]
MONO_ROOT = _THIS.parents[2]

for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PROJECTS_ROOT = MONO_ROOT
APP_NAME = APP_DIR.name
PAGE_NAME = _THIS.stem


# ============================================================
# navigation icons
# ============================================================
from common_lib.ui.nav_icons import (
    NAV_HOME_ICON,
    NAV_PORTAL_RETURN_ICON,
    NAV_PROCESS_ICON,
    NAV_CONSTRUCTION_ICON,
    NAV_STOP_ICON,
    PAGE_HOME_ICON,
    PAGE_PORTAL_RETURN_ICON,
)


# ============================================================
# page config
# ============================================================
st.set_page_config(
    page_title="Image Maker",
    page_icon="🎨",
    layout="wide",
)


# ============================================================
# navigation
# ============================================================
pg = st.navigation(
    {
        f"{NAV_HOME_ICON}": [
            st.Page(
                "pages/00_トップ.py",
                title="Home",
                icon=PAGE_HOME_ICON,
                default=True,
                url_path="top",
            ),
        ],

        f"{NAV_PROCESS_ICON} 画像処理": [
            st.Page(
                "pages/22_画像生成.py",
                title="画像生成",
                icon="🎨",
                url_path="22_画像生成",
            ),
            st.Page(
                "pages/23_画像修正.py",
                title="画像修正",
                icon="✏️",
                url_path="23_画像修正",
            ),
        ],

        f"{NAV_PROCESS_ICON} 利用履歴": [
            st.Page(
                "pages/30_ログ集計.py",
                title="利用履歴",
                icon="📊",
                url_path="30_ログ集計",
            ),
        ],

        f"{NAV_PORTAL_RETURN_ICON}": [
            st.Page(
                "pages/50_ポータルへ戻る.py",
                title="ポータルへ戻る",
                icon=PAGE_PORTAL_RETURN_ICON,
                url_path="50_ポータルへ戻る",
            ),
        ],

        f"{NAV_STOP_ICON} 開発・管理": [
            st.Page(
                "pages/99_画像ログ集計.py",
                title="画像ログ集計",
                icon="📊",
                url_path="99_画像ログ集計",
            ),
        ],

        f"{NAV_STOP_ICON} 開発・管理": [
            st.Page(
                "pages/999_開発用管理者ログイン.py",
                title="開発用 管理者ログイン",
                icon="🔐",
                url_path="999_開発用管理者ログイン",
            ),
        ],  
        
    }
)


# ============================================================
# run
# ============================================================
pg.run()