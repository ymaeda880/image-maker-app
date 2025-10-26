# pages/54
# _画像入れ替え.py
"""
🖼️ 2枚の画像をアップロードして、ボタンで左右の表示位置を入れ替えるだけのページ。

仕様
----
- アップロード直後に即プレビュー（フォームなし）
- 「↔️ 左右を入れ替える」ボタンで表示位置を入れ替え
- それぞれの画像を個別にクリア可能
- どちらか片方がない場合、入れ替えボタンは無効化
"""

from __future__ import annotations

from io import BytesIO
from typing import Optional

import streamlit as st
from PIL import Image

# ----------------------------- ページ設定 -----------------------------
st.set_page_config(page_title="画像入れ替え（2枚）", page_icon="🔁", layout="wide")
st.title("🔁 画像入れ替え（2枚）")

# --------------------------- セッション初期化 --------------------------
st.session_state.setdefault("img_left_bytes", None)   # 左に表示する画像バイト列（PNG）
st.session_state.setdefault("img_right_bytes", None)  # 右に表示する画像バイト列（PNG）
st.session_state.setdefault("uploader_rev", 0)        # アップローダの実クリア用（必要なときに +1 ）

# ----------------------------- ユーティリティ -----------------------------
def _to_png_bytes(img: Image.Image) -> bytes:
    """PIL.Image → PNG のバイト列へ変換."""
    bio = BytesIO()
    # 透過のない JPEG などは RGB、透過があるなら RGBA で保存
    mode = "RGBA" if ("A" in (img.getbands() or ())) else "RGB"
    img.convert(mode).save(bio, format="PNG")
    return bio.getvalue()

def _open_as_pil(file) -> Image.Image:
    """UploadedFile などを PIL.Image として開く（RGBAに寄せる）"""
    # file は UploadedFile（file.getvalue() でバイトを取得可能）
    data = file.getvalue()
    img = Image.open(BytesIO(data))
    # 表示安定のため RGBA に寄せる（透過を含む画像も安全に扱える）
    return img.convert("RGBA")

def _bytes_to_pil(b: Optional[bytes]) -> Optional[Image.Image]:
    """PNG バイト列 → PIL.Image（RGBA）"""
    if not b:
        return None
    try:
        return Image.open(BytesIO(b)).convert("RGBA")
    except Exception:
        return None

def _clear_left():
    st.session_state["img_left_bytes"] = None
    st.session_state["uploader_rev"] += 1

def _clear_right():
    st.session_state["img_right_bytes"] = None
    st.session_state["uploader_rev"] += 1

def _swap_images():
    st.session_state["img_left_bytes"], st.session_state["img_right_bytes"] = (
        st.session_state["img_right_bytes"],
        st.session_state["img_left_bytes"],
    )
    # アップローダの古い残留値で意図せず戻らないよう、key を更新して実クリア
    st.session_state["uploader_rev"] += 1

# ----------------------------- アップローダ -----------------------------
st.caption("それぞれに画像をドロップしてください。ドロップ直後にプレビューされます。")
rev = st.session_state["uploader_rev"]  # key切替でブラウザ側のキャッシュを実クリア

col_up_left, col_up_right = st.columns(2)
with col_up_left:
    up_left = st.file_uploader("左側の画像", type=["png", "jpg", "jpeg"], key=f"up_left_{rev}")
with col_up_right:
    up_right = st.file_uploader("右側の画像", type=["png", "jpg", "jpeg"], key=f"up_right_{rev}")

# ドロップ直後にセッションへ反映（フォーム不要）
if up_left is not None:
    try:
        img = _open_as_pil(up_left)
        st.session_state["img_left_bytes"] = _to_png_bytes(img)
    except Exception as e:
        st.error(f"左の画像読み込みに失敗: {e}")

if up_right is not None:
    try:
        img = _open_as_pil(up_right)
        st.session_state["img_right_bytes"] = _to_png_bytes(img)
    except Exception as e:
        st.error(f"右の画像読み込みに失敗: {e}")

# ----------------------------- 表示 & 操作 -----------------------------
left_img = _bytes_to_pil(st.session_state["img_left_bytes"])
right_img = _bytes_to_pil(st.session_state["img_right_bytes"])

st.markdown("---")
ops_left, ops_center, ops_right = st.columns([1, 1, 1])

with ops_left:
    st.button("🧹 左をクリア", use_container_width=True, on_click=_clear_left)

with ops_center:
    st.button(
        "↔️ 左右を入れ替える",
        use_container_width=True,
        on_click=_swap_images,
        disabled=(left_img is None or right_img is None),
        help="両方の画像が揃うと有効になります。",
    )

with ops_right:
    st.button("🧹 右をクリア", use_container_width=True, on_click=_clear_right)

st.markdown("---")

# 2枚のプレビュー（高さを揃えて見やすく）
c1, c2 = st.columns(2)
with c1:
    if left_img is not None:
        st.image(left_img, caption="左側", use_column_width=True)
    else:
        st.info("左側の画像が未設定です。")
with c2:
    if right_img is not None:
        st.image(right_img, caption="右側", use_column_width=True)
    else:
        st.info("右側の画像が未設定です。")
