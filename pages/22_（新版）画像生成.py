# pages/22_（新版）画像生成.py
# ============================================================
# 🧪 最小サンプル：画像生成＋何度でも修正（gpt-image-1）
# + ログイン表示（common_lib/auth/auth_helpers.py）
# + ログ（JSONL：app_name.log に統一、JST、app/page 自動付与）
# ============================================================

from __future__ import annotations

# ---- パス設定（共通ライブラリ読み込みのため）----
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
APP_DIR = _THIS.parents[1]
PROJ_DIR = _THIS.parents[2]
MONO_ROOT = _THIS.parents[3]
for p in (MONO_ROOT, PROJ_DIR, APP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PAGE_NAME = _THIS.stem  # ← ファイル名ベースのページ名
# ------------------------------------------------------------

from io import BytesIO
import base64, tempfile
from typing import Dict, Any
import streamlit as st
from PIL import Image
from openai import OpenAI

import datetime as dt

# ---- 共通ライブラリの読み込み ----
from lib.openai_client import get_client
from lib.image_utils import pil_to_png_bytes, url_to_png_bytes

# ログイン関連
from common_lib.auth.auth_helpers import get_current_user_from_session_or_cookie

# ★ 追加：共通JSONLロガー
from common_lib.logs.jsonl_logger import JsonlLogger, sha256_short


# ============================================================
# ページ設定
# ============================================================
st.set_page_config(page_title="画像生成＋修正", page_icon="🧪", layout="wide")

# ----------------- タイトル + ログインバッジ -----------------
col_title, col_user = st.columns([5, 2], vertical_alignment="center")

with col_title:
    st.title("🎨🖌️ 画像生成")

with col_user:
    user, _payload = get_current_user_from_session_or_cookie(st)
    if user:
        st.success(f"ログイン中: **{user}**")
    else:
        st.warning("未ログイン（Cookie 未検出）")

# ============================================================
# 環境初期化
# ============================================================
client: OpenAI = get_client()

# ★ ページ専用のセッションキー（他ページと衝突しないようにする）
SESSION_KEY_LAST = f"{PAGE_NAME}_simple_last_png"
st.session_state.setdefault(SESSION_KEY_LAST, b"")

# ★ 共通ロガー（出力: APP_DIR/logs/{APP_DIR.name}.log）
logger = JsonlLogger(app_dir=APP_DIR, page_name=PAGE_NAME)

# JST はファイル名や表示に利用（ロガーは内部でJST時刻を付与）
JST = dt.timezone(dt.timedelta(hours=9), name="Asia/Tokyo")

# ログにプロンプト全文を含めるか
INCLUDE_FULL_PROMPT_IN_LOG = True


# ============================================================
# 画像生成
# ============================================================
prompt = st.text_area("生成プロンプト", height=100)
size = st.selectbox("サイズ", ["1024x1024", "1024x1536", "1536x1024"], index=0)

if st.button("生成する", type="primary", width="stretch"):
    if not prompt.strip():
        st.warning("プロンプトを入力してください。")
        st.stop()

    with st.spinner("画像を生成中…"):
        res = client.images.generate(
            model="gpt-image-1",
            prompt=prompt.strip(),
            n=1,
            size=size,
        )
    d = res.data[0]

    # バイナリ変換
    if getattr(d, "b64_json", None):
        img = Image.open(BytesIO(base64.b64decode(d.b64_json))).convert("RGBA")
        png_bytes = pil_to_png_bytes(img)
    elif getattr(d, "url", None):
        png_bytes = url_to_png_bytes(d.url)
    else:
        st.error("画像が返ってきませんでした。")
        st.stop()

    # 状態保存（★ ページ専用キーを使用）
    st.session_state[SESSION_KEY_LAST] = png_bytes

    # ===== ログ記録（生成） =====
    current_user = user or "(anonymous)"
    logger.append({
        "user": current_user,
        "action": "generate",
        "model": "gpt-image-1",
        "size": size,
        "n": 1,
        "prompt_hash": sha256_short(prompt.strip()),
        **({"prompt": prompt.strip()} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
    })

    # 表示
    st.subheader("生成された画像")
    st.image(png_bytes, caption="生成結果", width="stretch")


# ============================================================
# 修正ループ
# ============================================================
st.divider()

if not st.session_state.get(SESSION_KEY_LAST):
    st.stop()

st.subheader("現在の処理対象画像（修正元になる画像）")
st.image(
    st.session_state[SESSION_KEY_LAST],
    caption="現在の元画像",
    width="stretch",
)

edit_prompt = st.text_area(
    "修正内容を入力",
    value="背景を夕焼けに、全体をシネマティックに",
    height=100,
)
edit_size = st.selectbox(
    "修正後のサイズ",
    ["1024x1024", "1024x1536", "1536x1024"],
    index=0,
)

if st.button(
    "修正版を生成する（修正内容のプロンプトを反映します．修正のプロンプトを入力してからクリックしてください．）",
    type="primary",
    width="stretch",
):
    if not edit_prompt.strip():
        st.warning("修正内容を入力してください。")
        st.stop()

    with st.spinner("修正版を生成中..."):
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(st.session_state[SESSION_KEY_LAST])
            tmp.seek(0)
            res2 = client.images.edit(
                model="gpt-image-1",
                image=("image.png", tmp),
                prompt=edit_prompt.strip(),
                size=edit_size,
            )

        datum = res2.data[0]
        if getattr(datum, "b64_json", None):
            img2 = Image.open(BytesIO(base64.b64decode(datum.b64_json))).convert("RGBA")
            out_bytes = pil_to_png_bytes(img2)
        elif getattr(datum, "url", None):
            out_bytes = url_to_png_bytes(datum.url)
        else:
            st.error("修正結果がありません。")
            st.stop()

        # 🔁 修正版を再び元画像に昇格（連続修正OK）
        st.session_state[SESSION_KEY_LAST] = out_bytes

        # ===== ログ記録（修正） =====
        current_user = user or "(anonymous)"
        logger.append({
            "user": current_user,
            "action": "edit",
            "source": "inline",
            "model": "gpt-image-1",
            "size": edit_size,
            "prompt_hash": sha256_short(edit_prompt.strip()),
            **({"prompt": edit_prompt.strip()} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
        })

        st.success("修正版を生成しました。さらに修正を続けられます。")

        st.subheader("プロンプトによって修正された画像（今回の修正元画像）")
        st.image(out_bytes, caption="修正版（次の元画像）", width="stretch")


# ============================================================
# 画像保存セクション（ページ下部）
# ============================================================
st.divider()
st.subheader("💾 生成画像の保存")

png_bytes = st.session_state.get(SESSION_KEY_LAST, b"")

if png_bytes:
    # サムネイル表示
    try:
        thumb = Image.open(BytesIO(png_bytes)).copy()
        thumb.thumbnail((256, 256))
        st.image(thumb, caption="現在の画像（サムネイル表示）")
    except Exception as e:
        st.warning(f"サムネイル生成に失敗しました: {e}")

    # ダウンロードボタン（ファイル名もJST基準）
    default_name = f"generated_{dt.datetime.now(JST):%Y%m%d_%H%M%S}.png"
    dl_name = st.text_input("ファイル名（ダウンロード用）", value=default_name)
    st.download_button(
        "⬇️ 保存（.png）",
        data=png_bytes,
        file_name=dl_name,
        mime="image/png",
        width="stretch",
    )
else:
    st.info("まだ保存できる画像がありません。上で生成または修正を行ってください。")
