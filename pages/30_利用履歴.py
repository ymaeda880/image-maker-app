# -*- coding: utf-8 -*-
# image_maker_app/pages/30_利用履歴.py
# ============================================================
# 📊 利用履歴：ログ集計（ログインユーザー専用 / このアプリのみ）
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

from common_lib.logs.paths import get_log_layout, month_to_file_map  # noqa: E402
from common_lib.logs.jsonl_reader import read_jsonl_files  # noqa: E402
from common_lib.logs.normalize import normalize_log_df  # noqa: E402

from common_lib.ui.page_header import render_standard_page_header  # noqa: E402

from lib.explanation.exp_image_usage import (  # noqa: E402
    render_image_usage_page_intro,
    render_image_usage_help_expander,
)

# ============================================================
# 基本設定
# ============================================================
HERE = Path(__file__).resolve()
APP_DIR = HERE.parents[1]
APP_NAME = APP_DIR.name
PAGE_NAME = HERE.stem

MONO_ROOT = HERE.parents[3]
PROJECTS_ROOT = MONO_ROOT


# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="Image Maker / 利用履歴",
    page_icon="📊",
    layout="wide",
)


# ============================================================
# 共通ヘッダー
# - settings.toml から BANNER_KEY を取得
# - banner / theme / intro CSS を描画
# - page_session_heartbeat を実行
# - title / subtitle / ログイン状態を描画
# ============================================================
sub, theme, BANNER_KEY, settings = render_standard_page_header(
    st_module=st,
    projects_root=PROJECTS_ROOT,
    app_dir=APP_DIR,
    app_name=APP_NAME,
    page_name=PAGE_NAME,
    title="📊 利用履歴",
    subtitle_text="画像生成・画像修正の利用状況を確認",
    default_banner_key="pink_soft",
)


# ============================================================
# ページ説明
# ============================================================
render_image_usage_page_intro()


# ============================================================
# 詳細説明
# ============================================================
render_image_usage_help_expander(
    theme=theme,
    banner_key=BANNER_KEY,
)


# ============================================================
# 基本設定（このアプリのログのみ）
# ============================================================
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
m2.metric("修正（edit）", f"{edit_cnt:,}")
m3.metric("合計", f"{total_cnt:,}")

# ============================================================
# 月別集計
# ============================================================
st.divider()
st.subheader("🗓️ 月別 画像生成枚数")

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

monthly_display = monthly.rename(
    columns={
        "month": "月",
        "generate": "画像生成",
        "edit": "画像修正",
        "total": "総数",
    }
)

monthly_display = monthly_display[
    [
        "月",
        "画像生成",
        "画像修正",
        "総数",
    ]
]

st.dataframe(monthly_display, width="stretch")

st.download_button(
    "⬇️ 月別集計 CSV",
    data=monthly_display.to_csv(index=False).encode("utf-8-sig"),
    file_name="my_monthly_summary.csv",
    mime="text/csv",
)


# ============================================================
# 月別・モデル別集計
# ============================================================
st.divider()
st.subheader("🧠 月別・モデル別 画像生成枚数")

for col in ["provider", "model"]:
    if col not in fdf.columns:
        fdf[col] = ""

model_df = fdf[fdf["action"].isin(["generate", "edit"])].copy()

if model_df.empty:
    st.info("月別・モデル別に集計できるログがありません。")
else:
    model_df["provider"] = model_df["provider"].fillna("").astype(str)
    model_df["model"] = model_df["model"].fillna("").astype(str)

    model_df["model_label"] = model_df.apply(
        lambda r: f"{r['provider']} / {r['model']}".strip(" /"),
        axis=1,
    )

    monthly_model = (
        model_df
        .groupby(["month", "model_label", "action"])["ts"]
        .count()
        .unstack(fill_value=0)
        .reset_index()
    )

    for col in ["generate", "edit"]:
        if col not in monthly_model.columns:
            monthly_model[col] = 0

    monthly_model["total"] = monthly_model["generate"] + monthly_model["edit"]
    monthly_model = monthly_model.sort_values(["month", "model_label"])

    monthly_model_display = monthly_model.rename(
        columns={
            "month": "月",
            "model_label": "モデル",
            "generate": "画像生成",
            "edit": "画像修正",
            "total": "総数",
        }
    )

    monthly_model_display = monthly_model_display[
        [
            "月",
            "モデル",
            "画像生成",
            "画像修正",
            "総数",
        ]
    ]

    st.dataframe(monthly_model_display, width="stretch")

    st.download_button(
        "⬇️ 月別・モデル別集計 CSV",
        data=monthly_model.to_csv(index=False).encode("utf-8-sig"),
        file_name="my_monthly_model_summary.csv",
        mime="text/csv",
    )

# ============================================================
# 終了
# ============================================================
# st.info(f"✅ {sub} として、自分のログのみを表示しています。")
