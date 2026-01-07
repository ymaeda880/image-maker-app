# pages/99_画像ログ集計.py
# ============================================================
# 📊 画像生成/修正ログ 集計ビューア（管理者専用）
# ============================================================

from __future__ import annotations
from pathlib import Path
import json
import datetime as dt
from typing import List, Dict, Any

import streamlit as st
import pandas as pd

# --- add this at the very top BEFORE importing common_lib ---
import sys
from pathlib import Path

def _add_commonlib_parent_to_syspath():
    here = Path(__file__).resolve()
    # 自分のファイルから上方向に辿って common_lib フォルダを探す
    for parent in [here.parent, *here.parents]:
        for name in ("common_lib", "COMMON_LIB"):
            if (parent / name).is_dir():
                if str(parent) not in sys.path:
                    sys.path.insert(0, str(parent))  # 親を追加（親/ common_lib が import 対象になる）
                return str(parent)
    return None

_add_commonlib_parent_to_syspath()
# --- then your original imports ---
from common_lib.auth.auth_helpers import get_current_user_from_session_or_cookie, is_admin
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root
from common_lib.auth.auth_helpers import require_admin_user




# ============================================================
# アクセス制御
# ============================================================
#user, payload = get_current_user_from_session_or_cookie(st)

st.set_page_config(page_title="画像ログ集計（管理者専用）", page_icon="📊", layout="wide")


#
# デバッグ用
#

# from common_lib.auth.auth_helpers import (
#     _resolve_settings_path, get_admin_users, clear_auth_caches
# )

#clear_auth_caches()  # ← 念のためキャッシュ削除
# st.write("🪶 設定ファイル探索結果:", _resolve_settings_path())
# st.write("🪶 管理者一覧:", sorted(get_admin_users()))
#st.write("🪶 現在のユーザー:", user)


sub = require_admin_user(st)
if not sub:
    st.error("🚫 このページは管理者のみアクセスできます。")
    st.stop()

st.success(f"✅ 管理者ログイン中: **{sub}**")  # ← 表示はここで自由に

user=sub

# if not user:
#     st.warning("未ログインです。サインインしてください。")
#     st.stop()

# if not is_admin(user):
#     st.error("🚫 このページは管理者のみアクセスできます。")
#     st.stop()



# ============================================================
# 基本設定（Storages/logs/<app_name>/ の monthly JSONL を読む）
# ============================================================
st.title("📊 画像生成/修正 ログ集計（管理者専用）")

HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
APP_NAME = APP_DIR.name

# projects ルート（このページの既存構造に合わせる：pages -> app -> project -> monorepo）
PROJ_DIR = HERE.parents[2]
MONO_ROOT = HERE.parents[3]
PROJECTS_ROOT = MONO_ROOT

# Storages ルート
STORAGE_ROOT = resolve_storage_subdir_root(PROJECTS_ROOT, subdir="Storages")

# monthly ログの置き場所：Storages/logs/<app_name>/
LOG_DIR = (Path(STORAGE_ROOT) / "logs" / APP_NAME).resolve()

JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")



# ============================================================
# ログ読込
# ============================================================
@st.cache_data(show_spinner=False)
def load_logs(paths: List[Path]) -> pd.DataFrame:
    # 存在するファイルだけ読む
    targets = [p for p in paths if p and p.exists()]
    if not targets:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    for path in targets:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            continue

    df = pd.DataFrame(rows)

    if "ts" in df.columns:
        ts = pd.to_datetime(df["ts"], errors="coerce")
        try:
            if getattr(ts.dt, "tz", None) is None:
                ts = ts.dt.tz_localize("Asia/Tokyo", nonexistent="shift_forward", ambiguous="NaT")
        except Exception:
            pass
        try:
            ts = ts.dt.tz_convert("Asia/Tokyo")
        except Exception:
            ts = ts.dt.tz_localize("Asia/Tokyo", nonexistent="shift_forward", ambiguous="NaT")

        df["ts"] = ts
        df["date"] = df["ts"].dt.date
        df["month"] = df["ts"].dt.strftime("%Y-%m")
    else:
        df["ts"] = pd.NaT
        df["date"] = pd.NaT
        df["month"] = None

    df["user"] = df.get("user", "(anonymous)").fillna("(anonymous)")
    return df


# ============================================================
# サイドバー：ログ再読込ボタン（★ 追加 ★）
# ============================================================
with st.sidebar:
    st.header("ログ")
    st.caption("ログが更新されても画面に反映されないときは、ここで再読込してください。")

    if st.button("🔄 ログを読み直す", use_container_width=True):
        # cache_data の全キャッシュを落として、即 rerun
        st.cache_data.clear()
        st.rerun()


# ============================================================
# ログファイル列挙（monthly：<app_name>_YYYY-MM.jsonl）
# ============================================================
all_files = []
if LOG_DIR.exists():
    # 例：image_maker_app_2025-12.jsonl
    all_files = sorted(LOG_DIR.glob(f"{APP_NAME}_*.jsonl"))

# ファイル名から YYYY-MM を抽出
def _month_from_name(p: Path) -> str | None:
    stem = p.stem  # e.g. image_maker_app_2025-12
    suffix = stem.replace(f"{APP_NAME}_", "", 1)
    # 厳密チェックはしない（想定外ファイルは無視）
    if len(suffix) == 7 and suffix[4] == "-":
        return suffix
    return None

month_to_file: dict[str, Path] = {}
for p in all_files:
    m = _month_from_name(p)
    if m:
        month_to_file[m] = p

available_months = sorted(month_to_file.keys())

with st.sidebar:
    st.header("ログ")
    st.caption("Storages/logs/<app_name>/ の monthly ログを読みます。")
    if not available_months:
        st.warning("ログファイルが見つかりません。")
    picked_months = st.multiselect(
        "対象年月（YYYY-MM）",
        options=available_months,
        default=available_months[-3:] if len(available_months) >= 3 else available_months,
        help="複数選択可。未選択の場合は空になります。"
    )

    if st.button("🔄 ログを読み直す"):
        st.cache_data.clear()
        st.rerun()

selected_paths = [month_to_file[m] for m in picked_months if m in month_to_file]
df = load_logs(selected_paths)



# ============================================================
# ファイル情報
# ============================================================
with st.expander("📁 ログファイル情報", expanded=False):
    st.write(f"**Dir:** `{LOG_DIR}`")
    if not selected_paths:
        st.warning("対象年月が未選択、またはログファイルがありません。")
        st.stop()

    st.write("**Files:**")
    for p in selected_paths:
        st.write(f"- `{p.name}`")

    # 最終更新（選択ファイルの最大）
    try:
        latest = max(selected_paths, key=lambda p: p.stat().st_mtime)
        mtime = dt.datetime.fromtimestamp(latest.stat().st_mtime, tz=JST)
        st.write(f"**最終更新（最大）:** {mtime:%Y-%m-%d %H:%M:%S %Z}")
    except Exception:
        pass

    st.write(f"**行数（読み込み後）:** {len(df):,}")


# ============================================================
# フィルタ
# ============================================================
st.divider()
st.subheader("🔍 フィルタ")

c1, c2, c3 = st.columns([1, 1, 2])
min_date, max_date = df["date"].min(), df["date"].max()

with c1:
    date_from = st.date_input("開始日", value=min_date or dt.date.today())
with c2:
    date_to = st.date_input("終了日", value=max_date or dt.date.today())
with c3:
    users = sorted(df["user"].dropna().unique().tolist())
    picked_users = st.multiselect("ユーザー選択", options=users, default=users)

mask = (df["date"] >= date_from) & (df["date"] <= date_to)
mask &= df["user"].isin(picked_users)
fdf = df[mask].copy()

st.caption(f"対象レコード: **{len(fdf):,} / {len(df):,}**")


# ============================================================
# サマリメトリクス
# ============================================================
gen_cnt = (fdf["action"] == "generate").sum()
edit_cnt = (fdf["action"] == "edit").sum()
unique_users = fdf["user"].nunique()

m1, m2, m3 = st.columns(3)
m1.metric("作成（generate）", f"{gen_cnt:,}")
m2.metric("改修（edit）", f"{edit_cnt:,}")
m3.metric("ユニークユーザー", f"{unique_users:,}")


# ============================================================
# ユーザー別 集計
# ============================================================
st.divider()
st.subheader("👤 ユーザー別 集計")

user_pivot = (
    fdf[fdf["action"].isin(["generate", "edit"])]
    .pivot_table(index="user", columns="action", values="ts", aggfunc="count", fill_value=0)
    .reset_index()
)

for col in ["generate", "edit"]:
    if col not in user_pivot.columns:
        user_pivot[col] = 0

user_pivot["total"] = user_pivot["generate"] + user_pivot["edit"]
user_pivot = user_pivot.sort_values("total", ascending=False)

st.dataframe(user_pivot, width="stretch")
st.download_button(
    "⬇️ ユーザー別集計 CSV",
    data=user_pivot.to_csv(index=False).encode("utf-8-sig"),
    file_name="user_summary.csv",
    mime="text/csv",
)

# ============================================================
# 月別 集計
# ============================================================
st.divider()
st.subheader("🗓️ 月別 集計")

monthly = (
    fdf[fdf["action"].isin(["generate", "edit"])]
    .groupby(["month", "action"])["ts"]
    .count()
    .unstack(fill_value=0)
    .reset_index()
)

for col in ["generate", "edit"]:
    if col not in monthly.columns:
        monthly[col] = 0

monthly["total"] = monthly["generate"] + monthly["edit"]
monthly = monthly.sort_values("month")

st.dataframe(monthly, width="stretch")
st.bar_chart(monthly.set_index("month")[["generate", "edit"]])

st.download_button(
    "⬇️ 月別集計 CSV",
    data=monthly.to_csv(index=False).encode("utf-8-sig"),
    file_name="monthly_summary.csv",
    mime="text/csv",
)



# ============================================================
# ユーザー × 月別 集計（合計 / generate / edit）
# ============================================================
st.divider()
st.subheader("👥🗓️ ユーザー × 月別 集計")

# 対象データ（generate / edit のみ）
df_um = fdf[fdf["action"].isin(["generate", "edit"])].copy()
if df_um.empty:
    st.info("対象期間・ユーザーに該当するログがありません。")
else:
    # 月の並び順を固定（欠損月も0で埋められるように）
    months = sorted(df_um["month"].dropna().unique().tolist())
    df_um["month"] = pd.Categorical(df_um["month"], categories=months, ordered=True)

    # 合計（generate + edit）
    pivot_total = (
        df_um
        .groupby(["user", "month"], observed=False)
        .size()
        .unstack(fill_value=0)
        .reindex(columns=months, fill_value=0)
        .sort_index()
    )

    # 個別アクション
    def pivot_for(action: str) -> pd.DataFrame:
        _tmp = (
            df_um[df_um["action"] == action]
            .groupby(["user", "month"], observed=False)
            .size()
            .unstack(fill_value=0)
            .reindex(columns=months, fill_value=0)
            .sort_index()
        )
        # 全ユーザー・全月に0で揃える
        return _tmp.reindex(index=sorted(df_um["user"].unique()), fill_value=0)

    pivot_gen  = pivot_for("generate")
    pivot_edit = pivot_for("edit")

    tab_total, tab_gen, tab_edit, tab_chart = st.tabs(["合計", "generate", "edit", "チャート"])

    with tab_total:
        st.caption("ユーザー × 月 列：月 / 値：件数（generate + edit）")
        st.dataframe(pivot_total, width="stretch")
        st.download_button(
            "⬇️ 合計（ユーザー×月）CSV",
            data=pivot_total.to_csv(index=True).encode("utf-8-sig"),
            file_name="user_by_month_total.csv",
            mime="text/csv",
        )

    with tab_gen:
        st.caption("ユーザー × 月 列：月 / 値：件数（generate）")
        st.dataframe(pivot_gen, width="stretch")
        st.download_button(
            "⬇️ generate（ユーザー×月）CSV",
            data=pivot_gen.to_csv(index=True).encode("utf-8-sig"),
            file_name="user_by_month_generate.csv",
            mime="text/csv",
        )

    with tab_edit:
        st.caption("ユーザー × 月 列：月 / 値：件数（edit）")
        st.dataframe(pivot_edit, width="stretch")
        st.download_button(
            "⬇️ edit（ユーザー×月）CSV",
            data=pivot_edit.to_csv(index=True).encode("utf-8-sig"),
            file_name="user_by_month_edit.csv",
            mime="text/csv",
        )

    with tab_chart:
        st.caption("ユーザーを選ぶと月次推移を表示（合計 / 内訳を切替可）")
        chart_kind = st.radio("系列", ["合計", "generate", "edit"], horizontal=True)
        pick_users = st.multiselect(
            "ユーザーを選択（複数可）",
            options=sorted(pivot_total.index.tolist()),
            default=sorted(pivot_total.index.tolist())[:5],
        )

        if chart_kind == "合計":
            df_plot = pivot_total
        elif chart_kind == "generate":
            df_plot = pivot_gen
        else:
            df_plot = pivot_edit

        df_plot = df_plot.loc[df_plot.index.intersection(pick_users)]
        if df_plot.empty:
            st.info("表示対象のユーザーが選択されていません。")
        else:
            # 月をインデックスに転置して可視化（縦：月、横：ユーザーの複数系列）
            st.bar_chart(df_plot.T)

# ============================================================
# 🧹 年月でログ削除（monthly ファイルを物理削除）
# ============================================================
st.divider()
st.subheader("🧹 年月でログ削除（monthlyファイル削除）")

all_months = available_months
sel_months = st.multiselect(
    "削除する年月（複数選択可）",
    options=all_months,
    help="選んだ年月の monthly ログファイル（例：app_YYYY-MM.jsonl）を物理削除します。元に戻せないため注意。"
)

if sel_months:
    files_to_delete = [month_to_file[m] for m in sel_months if m in month_to_file]
    st.warning("削除対象ファイル:")
    for p in files_to_delete:
        st.write(f"- `{p.name}`")

    confirm = st.text_input("確認のため DELETE と入力してください", placeholder="DELETE")
    do_purge = st.button("選択した年月のログファイルを削除する", type="secondary")

    if do_purge:
        if confirm != "DELETE":
            st.error("確認文字列が一致しません。DELETE と入力してください。")
        else:
            # バックアップしてから削除（同階層に .bak を作る）
            ok = 0
            ng = 0
            for p in files_to_delete:
                try:
                    if not p.exists():
                        continue
                    bak = p.with_suffix(p.suffix + ".bak")
                    # 既存bakがあれば上書きしない（安全側）
                    if not bak.exists():
                        bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
                    p.unlink()
                    ok += 1
                except Exception:
                    ng += 1

            if ng == 0:
                st.success(f"削除完了: {ok} ファイル")
            else:
                st.warning(f"削除: {ok} 成功 / {ng} 失敗（権限やI/Oを確認）")

            st.cache_data.clear()
            st.rerun()
else:
    st.caption("削除する年月を選ぶと削除ボタンが有効になります。")



# ============================================================
# 終了メッセージ
# ============================================================
st.info(f"✅ 管理者 {user} として閲覧中。")
