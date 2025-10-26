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



# ============================================================
# アクセス制御
# ============================================================
user, payload = get_current_user_from_session_or_cookie(st)

st.set_page_config(page_title="画像ログ集計（管理者専用）", page_icon="📊", layout="wide")


#
# デバッグ用
#

from common_lib.auth.auth_helpers import (
    _resolve_settings_path, get_admin_users, clear_auth_caches
)

clear_auth_caches()  # ← 念のためキャッシュ削除
# st.write("🪶 設定ファイル探索結果:", _resolve_settings_path())
# st.write("🪶 管理者一覧:", sorted(get_admin_users()))
st.write("🪶 現在のユーザー:", user)



if not user:
    st.warning("未ログインです。サインインしてください。")
    st.stop()

if not is_admin(user):
    st.error("🚫 このページは管理者のみアクセスできます。")
    st.stop()



# ============================================================
# 基本設定
# ============================================================
st.title("📊 画像生成/修正 ログ集計（管理者専用）")

APP_DIR = Path(__file__).resolve().parents[1]
APP_NAME = APP_DIR.name
# ★ ここを変更：共通ロガーの出力規約（logs/{app_name}.log.jsonl）に合わせる
LOG_FILE = (APP_DIR / "logs" / f"{APP_NAME}.log.jsonl").resolve()

JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")


# ============================================================
# ログ読込
# ============================================================
@st.cache_data(show_spinner=False)
def load_logs(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line.strip()))
            except Exception:
                continue

    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        df["ts"] = ts.dt.tz_convert("Asia/Tokyo")
        df["date"] = df["ts"].dt.date
        df["month"] = df["ts"].dt.strftime("%Y-%m")
    else:
        df["ts"] = pd.NaT
        df["date"] = pd.NaT
        df["month"] = None

    df["user"] = df.get("user", "(anonymous)").fillna("(anonymous)")
    return df


df = load_logs(LOG_FILE)


# ============================================================
# ファイル情報
# ============================================================
with st.expander("📁 ログファイル情報", expanded=False):
    st.write(f"**Path:** `{LOG_FILE}`")
    if LOG_FILE.exists():
        mtime = dt.datetime.fromtimestamp(LOG_FILE.stat().st_mtime, tz=JST)
        st.write(f"**最終更新:** {mtime:%Y-%m-%d %H:%M:%S %Z}")
        st.write(f"**行数:** {len(df):,}")
    else:
        st.warning("ログファイルが存在しません。")
        st.stop()

if df.empty:
    st.warning("ログデータがありません。")
    st.stop()


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
        .groupby(["user", "month"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=months, fill_value=0)
        .sort_index()
    )

    # 個別アクション
    def pivot_for(action: str) -> pd.DataFrame:
        _tmp = (
            df_um[df_um["action"] == action]
            .groupby(["user", "month"])
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
# 🧹 年月でログ削除（JSONLを物理削除）
# ============================================================
st.divider()
st.subheader("🧹 年月でログ削除")

# 利用可能な年月リスト（YYYY-MM）
all_months = sorted(df["month"].dropna().unique().tolist())
sel_months = st.multiselect(
    "削除する年月（複数選択可）", options=all_months,
    help="選んだ年月に属する行（generate / edit など全イベント）を物理削除します。元に戻せないため注意。"
)

# 安全な原子的書き換え
def _atomic_write_jsonl(path: Path, records: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)

if sel_months:
    # 削除見込み件数（全体 df ベース）
    to_delete_count = int(df[df["month"].isin(sel_months)].shape[0])
    st.warning(f"削除対象: **{to_delete_count:,} 行**（{', '.join(sel_months)}）")

    # 最終確認
    confirm = st.text_input("確認のため DELETE と入力してください", placeholder="DELETE")

    # 実行ボタン
    do_purge = st.button("選択した年月のログを削除する", type="secondary", disabled=(to_delete_count == 0))
    if do_purge:
        if confirm != "DELETE":
            st.error("確認文字列が一致しません。DELETE と入力してください。")
        elif not LOG_FILE.exists():
            st.error("ログファイルが見つかりません。")
        else:
            # 1) 全行を読み、ts→YYYY-MM を算出してフィルタ
            original: list[dict] = []
            kept: list[dict] = []
            with LOG_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        # 読めない行は温存（安全側）
                        kept.append({"_raw": line})
                        continue

                    original.append(rec)
                    ts = rec.get("ts")
                    month = None
                    if ts:
                        try:
                            # ts から JST で YYYY-MM を算出
                            month = pd.to_datetime(ts, utc=True, errors="coerce").tz_convert("Asia/Tokyo").strftime("%Y-%m")
                        except Exception:
                            month = None

                    if month not in sel_months:
                        kept.append(rec)

            removed = len(original) - (len([r for r in kept if isinstance(r, dict)]))
            # 2) バックアップ
            try:
                backup = LOG_FILE.with_suffix(".jsonl.bak")  # 例: *.log.jsonl.bak
                backup.write_text(LOG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception as e:
                st.error(f"バックアップ作成に失敗しました: {e}")
                st.stop()

            # 3) 原子的に書き換え
            try:
                tmp = LOG_FILE.with_suffix(LOG_FILE.suffix + ".tmp")
                with tmp.open("w", encoding="utf-8") as wf:
                    for r in kept:
                        if isinstance(r, dict) and "_raw" in r:
                            wf.write(r["_raw"] + "\n")
                        else:
                            wf.write(json.dumps(r, ensure_ascii=False) + "\n")
                tmp.replace(LOG_FILE)

                st.success(f"削除完了: **{removed:,} 行** を削除 / 残り {len(kept):,} 行")
                st.caption(f"バックアップを作成: `{backup.name}`")

                # キャッシュ無効化 → リロード
                load_logs.clear()
                st.rerun()

            except Exception as e:
                st.error(f"削除に失敗しました: {e}")
else:
    st.caption("削除する年月を選ぶと実行ボタンが現れます。")



# ============================================================
# 終了メッセージ
# ============================================================
st.info(f"✅ 管理者 {user} として閲覧中。")
