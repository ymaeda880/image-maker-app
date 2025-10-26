# app.py（image_maker_app）
"""
🎨 image_maker_app（ログイン必須ガード付き）

目的
----
- このアプリは **ログインしていないと来れない** 前提。
- Cookie の JWT を検証して未ログインなら即ブロックし、ログインページへ誘導。
- ログイン済みならヘッダー右上に「現在のユーザー名」を表示（任意でログアウトも可能）。

実装メモ
--------
- Cookie 名や JWT の発行/検証は共通ライブラリ（common_lib）に委譲。
- extra_streamlit_components.CookieManager を使って Cookie を読み書き。
- JWT 失効/改ざん検出時は Cookie を掃除して状態不整合を防止。
- Streamlit 1.31+ の `st.page_link` があればログインページへのリンクを出す。
"""

from __future__ import annotations

from pathlib import Path
import datetime as dt
import sys
from typing import Optional

import streamlit as st
import extra_streamlit_components as stx

# このファイルの場所: /Users/macmini2025/projects/image_maker_project/image_maker_app/app.py
# → 3つ上に /Users/macmini2025/projects がある
PROJECTS_DIR = Path(__file__).resolve().parents[2]  # /Users/macmini2025/projects

# 念のため存在確認
if not (PROJECTS_DIR / "common_lib").exists():
    import streamlit as st
    st.set_page_config(page_title="image_maker_app", page_icon="🎨", layout="wide")
    st.error(f"common_lib が見つかりません: {(PROJECTS_DIR / 'common_lib')}")
    st.stop()

# ★ sys.path に入れるのは「/Users/macmini2025/projects」
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))



# ✅ デバッグ用（削除してOK）
# import sys; print("sys.path =", sys.path)
# 共有ユーティリティ（前提：pages/10_ログイン_最小.py と同じ場所から import できる構成）
from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import verify_jwt  # issue は不要（ここは閲覧ガードのみ）

# ========== ページ基本設定 ==========
st.set_page_config(page_title="image_maker_app", page_icon="🎨", layout="wide")

# -----------------------------------------------------------------------------
# Cookie ヘルパ
# -----------------------------------------------------------------------------
cm = stx.CookieManager(key="cm_image_maker")

def _clear_cookie_everywhere(name: str) -> None:
    """
    Cookie をできるだけ確実に無効化する。
    - path="/" を明示した上書き
    - 現在パスでの上書き
    - delete() 呼び出し
    """
    epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    cm.set(name, "", expires_at=epoch, path="/")
    cm.set(name, "", expires_at=epoch)
    cm.delete(name)

# -----------------------------------------------------------------------------
# 🔒 入場ガード：Cookie → JWT 検証
# -----------------------------------------------------------------------------
token: Optional[str] = cm.get(COOKIE_NAME)
payload = verify_jwt(token) if token else None

if not payload:
    # 失効や改ざんの場合は Cookie を掃除
    if token:
        _clear_cookie_everywhere(COOKIE_NAME)

    st.error("このアプリはログインが必要です。")
    # Streamlit 1.31+ の page_link があれば、ページリンクを表示（存在しなくてもクラッシュしない）
    try:
        st.page_link("pages/10_ログイン_最小.py", label="🔐 ログインページへ移動", icon="🔑")
    except Exception:
        st.info("サイドバーの『ポータルへ戻る』ページからサインインしてください。")
    st.stop()

# 以降はログイン済み
current_user = payload.get("sub") or "(unknown)"

# -----------------------------------------------------------------------------
# ヘッダー：タイトル＋ログイン中ユーザーの表示（任意でログアウト）
# -----------------------------------------------------------------------------
# 右上にユーザー名を出す軽いヘッダーバー
h1, h2 = st.columns([4, 1])
with h1:
    st.title("🎨 image_maker_app")
with h2:
    st.caption("ログイン中ユーザー")
    st.success(f"**{current_user}**")

# -----------------------------------------------------------------------------
# （以下、従来のアプリ内容）
# -----------------------------------------------------------------------------

st.markdown("""
    １枚約25円かかります．ユーザー毎に集計して月末に請求を行います．        
            """)


st.markdown("""
このアプリでは、**プロンプト**を入力して OpenAI GPT-image-1Images API（DALL·E 3の改良版）で画像を生成できます。
左の「サイドバー」から **『画像生成』** を開いてください。
""")

with st.expander("使い方", expanded=False):
    st.markdown("""
1. 画像を生成するときは，「サイドバー」の『画像生成』から行ってください．
2. 画像を修正するときは，「サイドバー」の『画像修正』から行ってください．
""")
