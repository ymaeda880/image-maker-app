# pages/56_Authデバッグ.py
# ============================================================
# 🔧 認証デバッグページ：ログインユーザー & 管理者判定の確認
# - 現在のログインユーザー表示
# - 管理者判定（is_admin）
# - settings.toml の参照パスと管理者一覧の可視化
# - キャッシュクリア / コンソール出力
# - 任意: restricted 判定テスト
# ============================================================

from __future__ import annotations
from pathlib import Path
import os
import sys
import streamlit as st

# ---- common_lib を見つける（上方向に common_lib がある前提）----
def _add_commonlib_parent_to_syspath():
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "common_lib").is_dir():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return
_add_commonlib_parent_to_syspath()

# ---- helper import ----
from common_lib.auth.auth_helpers import (
    get_current_user_from_session_or_cookie,
    is_admin,
    get_admin_users,
    clear_auth_caches,
    _resolve_settings_path,       # デバッグ用
    is_restricted_allowed,        # 任意チェック用
    debug_dump_admins,            # コンソール出力
)

# ---- ページ設定 ----
st.set_page_config(page_title="Authデバッグ", page_icon="🔧", layout="wide")
st.title("🔧 Auth デバッグ（ログイン/管理者）")

# ============================================================
# 環境変数で settings.toml を固定（任意）
# ============================================================
with st.expander("⚙️ 設定ファイルの上書き（任意）", expanded=False):
    st.caption("※ `.streamlit/settings.toml` を別場所に置いている場合に指定。変更後は『キャッシュクリア』を押してください。")
    env_path = st.text_input("ADMIN_SETTINGS_FILE（絶対パス）", os.environ.get("ADMIN_SETTINGS_FILE", ""))
    col_a1, col_a2 = st.columns([1,1])
    with col_a1:
        if st.button("環境変数を設定/更新", use_container_width=True):
            if env_path.strip():
                os.environ["ADMIN_SETTINGS_FILE"] = env_path.strip()
                st.success("ADMIN_SETTINGS_FILE を設定しました。『キャッシュクリア』を押して再読込してください。")
            else:
                st.warning("パスを入力してください。")
    with col_a2:
        if st.button("環境変数を解除", use_container_width=True):
            os.environ.pop("ADMIN_SETTINGS_FILE", None)
            st.success("ADMIN_SETTINGS_FILE を解除しました。『キャッシュクリア』を押して再読込してください。")

# ============================================================
# 基本情報
# ============================================================
user, payload = get_current_user_from_session_or_cookie(st)

c1, c2, c3 = st.columns([1,1,2])
with c1:
    st.subheader("👤 現在のユーザー")
    st.write(user or "（未ログイン）")

with c2:
    st.subheader("🛡️ 管理者判定")
    if user and is_admin(user):
        st.success("管理者: True")
    else:
        st.error("管理者: False")

with c3:
    st.subheader("📄 設定ファイルの参照パス")
    st.code(str(_resolve_settings_path()))

st.divider()

# ============================================================
# 管理者一覧 / 操作
# ============================================================
st.subheader("👥 管理者一覧（settings.toml 読み込み結果）")
admins = sorted(get_admin_users())
st.write(admins)

col_b1, col_b2 = st.columns([1,1])
with col_b1:
    if st.button("🔁 キャッシュクリア（再読込）", use_container_width=True):
        clear_auth_caches()
        st.success("キャッシュをクリアしました。ページを再実行しています…")
        st.experimental_rerun()
with col_b2:
    if st.button("🖨 コンソールに管理者一覧を出力（debug_dump_admins）", use_container_width=True):
        debug_dump_admins()
        st.info("サーバーのコンソール（標準出力）に設定パスと管理者一覧を出力しました。")

# ============================================================
# 任意：restricted 判定の手動チェック
# ============================================================
with st.expander("🔒 restricted 判定テスト（任意）", expanded=False):
    st.caption("settings.toml の [restricted_users] セクションで app_key を使っている場合のチェック。")
    app_key = st.text_input("app_key（例: login_test）", value="login_test")
    test_user = st.text_input("ユーザー名（空=現在のユーザー）", value=user or "")
    if st.button("判定する", use_container_width=True):
        target = test_user or user
        if not target:
            st.warning("ユーザー名がありません。ログインするか、ユーザー名を入力してください。")
        else:
            allowed = is_restricted_allowed(target, app_key)
            if allowed:
                st.success(f"allowed: True（user={target}, app_key={app_key}）")
            else:
                st.error(f"allowed: False（user={target}, app_key={app_key}）")

st.info("✅ このページで『現在のユーザー』『管理者判定』『設定ファイル参照パス』『管理者一覧』を確認できます。")
