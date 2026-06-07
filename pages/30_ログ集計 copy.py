# -*- coding: utf-8 -*-
# pages/30_ログ集計.py
# ============================================================
# 📊 ログ集計（ログインユーザー専用 / このアプリのみ）
# ============================================================

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

# ============================================================
# common_lib を import 可能にする（99 と同じ方式）
# ============================================================
def _add_commonlib_parent_to_syspath():
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        for name in ("common_lib", "COMMON_LIB"):
            if (parent / name).is_dir():
                if str(parent) not in sys.path:
                    sys.path.insert(0, str(parent))
                return str(parent)
    return None


_add_commonlib_parent_to_syspath()

from common_lib.auth.auth_helpers import require_login  # noqa: E402
from common_lib.logs.paths import get_log_layout, month_to_file_map  # noqa: E402
from common_lib.logs.jsonl_reader import read_jsonl_files  # noqa: E402
from common_lib.logs.normalize import normalize_log_df  # noqa: E402
from common_lib.ui.banner_lines import render_banner_line_by_key

# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="Image Maker / ログ集計",
    page_icon="📊",
    layout="wide",
)
render_banner_line_by_key("pink_soft")

# ============================================================
# ログイン必須（★ 管理者ではない ★）
# ============================================================

sub = require_login(st)
if not sub:
    st.stop()
left, right = st.columns([2, 1])
with left:
    st.title("📊 利用履歴")
with right:
    st.success(f"✅ ログイン中: **{sub}**")


# ============================================================
# 基本設定（このアプリのログのみ）
# ============================================================
# st.title("📊 ログ集計（利用履歴）")

HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
APP_NAME = APP_DIR.name

MONO_ROOT = HERE.parents[3]
PROJECTS_ROOT = MONO_ROOT

# ✅ common_lib 側の正本で log_dir を決定
_layout = get_log_layout(PROJECTS_ROOT, APP_NAME)
LOG_DIR = _layout.log_dir


# ============================================================
# ログ読込（common_lib に寄せた Reader/Normalizer を利用）
# ============================================================
@st.cache_data(show_spinner=False)
def load_logs(paths: List[Path]) -> pd.DataFrame:
    targets = [Path(p) for p in (paths or []) if p and Path(p).exists()]
    if not targets:
        # 下流で df["date"] 等に触れるので、最低限の列は用意
        return pd.DataFrame(columns=["ts", "date", "month", "user", "action"])

    df = read_jsonl_files(targets)
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts", "date", "month", "user", "action"])

    df = normalize_log_df(df)

    # 念のため：下流が参照する列を保証
    for col, default in [
        ("ts", pd.NaT),
        ("date", pd.NaT),
        ("month", None),
        ("user", "(anonymous)"),
    ]:
        if col not in df.columns:
            df[col] = default

    return df


# ============================================================
# サイドバー：再読込 & 月選択
# ============================================================
with st.sidebar:
    st.header("ログ")
    st.caption("このアプリのログのみを表示します。")

    if st.button("🔄 ログを読み直す"):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# 月次ログファイル列挙（common_lib の正本に寄せる）
# ============================================================
month_to_file = month_to_file_map(LOG_DIR, log_name=APP_NAME)
available_months = sorted(month_to_file.keys())

with st.sidebar:
    if not available_months:
        st.warning("ログファイルが見つかりません。")
    picked_months = st.multiselect(
        "対象年月（YYYY-MM）",
        options=available_months,
        default=available_months[-3:] if len(available_months) >= 3 else available_months,
    )

selected_paths = [month_to_file[m] for m in picked_months if m in month_to_file]
df = load_logs(selected_paths)


# ============================================================
# ファイル情報
# ============================================================
with st.expander("📁 ログファイル情報", expanded=False):
    st.write(f"**Dir:** `{LOG_DIR}`")
    if not selected_paths:
        st.warning("対象年月が未選択、またはログがありません。")
        st.stop()

    for p in selected_paths:
        st.write(f"- `{p.name}`")

    st.write(f"**行数（読み込み後）:** {len(df):,}")


# ============================================================
# 自分のログのみに限定（★ 重要 ★）
# ============================================================
if "user" not in df.columns:
    st.warning("ログに user 列が見つからないため、自分のログに絞り込めません。")
    st.stop()

df = df[df["user"] == sub].copy()

if df.empty:
    st.info("この期間にログはありません。")
    st.stop()


# ============================================================
# フィルタ（日付）
# ============================================================
st.divider()
st.subheader("🔍 フィルタ")

if "date" not in df.columns:
    st.warning("ログに date 列が見つからないため、日付フィルタが使えません。")
    st.stop()

c1, c2 = st.columns(2)
min_date, max_date = df["date"].min(), df["date"].max()

with c1:
    date_from = st.date_input("開始日", value=min_date)
with c2:
    date_to = st.date_input("終了日", value=max_date)

mask = (df["date"] >= date_from) & (df["date"] <= date_to)
fdf = df[mask].copy()

st.caption(f"対象レコード: **{len(fdf):,} / {len(df):,}**")


# ============================================================
# サマリ
# ============================================================
if "action" not in fdf.columns:
    fdf["action"] = None

gen_cnt = (fdf["action"] == "generate").sum()
edit_cnt = (fdf["action"] == "edit").sum()
total_cnt = len(fdf)

m1, m2, m3 = st.columns(3)
m1.metric("作成（generate）", f"{gen_cnt:,}")
m2.metric("改修（edit）", f"{edit_cnt:,}")
m3.metric("合計", f"{total_cnt:,}")


# ============================================================
# 月別集計
# ============================================================
st.divider()
st.subheader("🗓️ 月別 集計")

if "month" not in fdf.columns:
    st.warning("ログに month 列が見つからないため、月別集計ができません。")
    st.stop()

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
    file_name="my_monthly_summary.csv",
    mime="text/csv",
)

# ============================================================
# 終了
# ============================================================
# st.info(f"✅ {sub} として、自分のログのみを表示しています。")
