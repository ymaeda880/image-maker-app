# pages/30_ログ集計.py
# ============================================================
# 📊 ログ集計（ログインユーザー専用 / このアプリのみ）
# ============================================================

from __future__ import annotations

import sys
from pathlib import Path
import json
import datetime as dt
from typing import List, Dict, Any

import streamlit as st
import pandas as pd

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

from common_lib.auth.auth_helpers import require_login
from common_lib.storage.external_ssd_root import resolve_storage_subdir_root


# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="ログ集計（自分の利用履歴）",
    page_icon="📊",
    layout="wide",
)

# ============================================================
# ログイン必須（★ 管理者ではない ★）
# ============================================================
sub = require_login(st)
if not sub:
    st.stop()

st.success(f"✅ ログイン中: **{sub}**")


# ============================================================
# 基本設定（このアプリのログのみ）
# ============================================================
st.title("📊 ログ集計（自分の利用履歴）")

HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
APP_NAME = APP_DIR.name

MONO_ROOT = HERE.parents[3]
PROJECTS_ROOT = MONO_ROOT

STORAGE_ROOT = resolve_storage_subdir_root(PROJECTS_ROOT, subdir="Storages")
LOG_DIR = (Path(STORAGE_ROOT) / "logs" / APP_NAME).resolve()

JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


# ============================================================
# ログ読込
# ============================================================
@st.cache_data(show_spinner=False)
def load_logs(paths: List[Path]) -> pd.DataFrame:
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
# サイドバー：再読込 & 月選択
# ============================================================
with st.sidebar:
    st.header("ログ")
    st.caption("このアプリのログのみを表示します。")

    if st.button("🔄 ログを読み直す"):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# 月次ログファイル列挙
# ============================================================
all_files = []
if LOG_DIR.exists():
    all_files = sorted(LOG_DIR.glob(f"{APP_NAME}_*.jsonl"))

def _month_from_name(p: Path) -> str | None:
    stem = p.stem
    suffix = stem.replace(f"{APP_NAME}_", "", 1)
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
df = df[df["user"] == sub].copy()

if df.empty:
    st.info("この期間にログはありません。")
    st.stop()


# ============================================================
# フィルタ（日付）
# ============================================================
st.divider()
st.subheader("🔍 フィルタ")

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
st.info(f"✅ {sub} として、自分のログのみを表示しています。")
