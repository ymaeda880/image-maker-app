# pages/52_画像修正.py
# =============================================================================
# 🪄 画像修正（inpainting / edit）— ボタンをプレビューより“前”に配置した安定版
# =============================================================================

from __future__ import annotations

import json, hashlib
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from typing import Optional

import streamlit as st
from PIL import Image
from openai import OpenAI

from lib.openai_client import get_client
from lib.image_utils import pil_open, pil_to_png_bytes, as_named_file
from lib.session_bridge import clear_edit_payload
from lib.ui import show_image, download_img_buttons

# ───────────────────────────── ログ設定 ─────────────────────────────
LOG_DIR = Path("logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "image_gen.log.jsonl"
INCLUDE_FULL_PROMPT_IN_LOG = True

def _sha256_short(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]

def _append_log(rec: dict) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ───────────── common_lib 検出 → JWT からユーザー名を得る ────────────
def _add_commonlib_parent_to_syspath() -> None:
    here = Path(__file__).resolve()
    import sys
    for p in [here.parent, *here.parents]:
        if (p / "common_lib").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            break
_add_commonlib_parent_to_syspath()

def _get_user() -> str:
    u = st.session_state.get("current_user")
    if u: return u
    try:
        import extra_streamlit_components as stx
        from common_lib.auth.config import COOKIE_NAME
        from common_lib.auth.jwt_utils import verify_jwt
        cm = stx.CookieManager(key="cm_img_edit")
        tok = cm.get(COOKIE_NAME)
        payload = verify_jwt(tok) if tok else None
        if payload and payload.get("sub"):
            return str(payload["sub"])
    except Exception:
        pass
    return "(anonymous)"

# ───────────────────────────── ページ設定 ────────────────────────────
st.set_page_config(page_title="画像修正（inpainting/edit）", page_icon="🪄", layout="wide")
client: OpenAI = get_client()

# ───────────────────────────── セッション初期化 ───────────────────────
st.session_state.setdefault("uploader_rev", 0)           # file_uploader 実クリア用
st.session_state.setdefault("force_session_src", False)  # セッション画像を優先
st.session_state.setdefault("edit_src_bytes", None)      # 元画像PNG
st.session_state.setdefault("edit_src_prompt", "")       # 次回の初期プロンプト
st.session_state.setdefault("last_result_bytes", None)   # 直近の結果PNG（上部ボタンで昇格）

# ───────────────────────────── ヘッダ ───────────────────────────────
user = _get_user()
h1, h2 = st.columns([4, 2])
with h1: st.title("🪄 画像修正（inpainting / edit）")
with h2: st.info(f"👤 {user}")

with st.expander("💰 概算料金（1ドル=150円換算）", expanded=False):
    st.markdown("**gpt-image-1**: 約6〜25円/枚・**dall-e-2**: 約3円/枚（概算）")

# ────────────────────────── 上部：結果→元画像 反映ボタン ─────────────────
def _apply_last_result_as_source():
    b = st.session_state.get("last_result_bytes")
    if not b:
        return
    # 直近の結果を「元画像」に昇格
    st.session_state["edit_src_bytes"] = b
    st.session_state["force_session_src"] = True
    # file_uploader の残留値で戻らないよう key 更新 & 直前キー破棄
    prev_rev = st.session_state.get("uploader_rev", 0)
    st.session_state["uploader_rev"] = prev_rev + 1
    st.session_state.pop(f"src_file_{prev_rev}", None)
    st.session_state.pop(f"mask_file_{prev_rev}", None)

top_l, top_r = st.columns([3, 1])
with top_r:
    st.button(
        "🔁 直近の結果を元画像に反映",
        use_container_width=True,
        on_click=_apply_last_result_as_source,
        disabled=(st.session_state.get("last_result_bytes") is None),
        help="直前に生成/編集した結果を、次の元画像として採用します。",
    )

st.markdown("元画像に対して、プロンプトで修正します。必要なら **マスクPNG**（透明=編集/不透明=保持）も指定。")

# ────────────────────────── アップローダ（フォーム外） ──────────────────
rev = st.session_state["uploader_rev"]
ul, ur = st.columns(2)
with ul:
    src_file = st.file_uploader("🖼 元画像（PNG/JPG）", type=["png", "jpg", "jpeg"], key=f"src_file_{rev}")
with ur:
    mask_file = st.file_uploader("🎭 マスクPNG（任意）", type=["png"], key=f"mask_file_{rev}")

if src_file is not None:
    # 新規アップロードが来たらユーザー操作を優先（セッション優先を下げる）
    st.session_state["force_session_src"] = False

# ────────────────────────── ユーティリティ ──────────────────────────
def _get_session_image_if_any() -> Optional[Image.Image]:
    b = st.session_state.get("edit_src_bytes")
    if not b:
        return None
    try:
        return Image.open(BytesIO(b)).convert("RGBA")
    except Exception:
        st.warning("セッションの元画像を開けませんでした。")
        return None

def _set_session_image(img: Image.Image, prompt_hint: str = "") -> None:
    st.session_state["edit_src_bytes"] = pil_to_png_bytes(img)
    if prompt_hint:
        st.session_state["edit_src_prompt"] = prompt_hint
    st.session_state["force_session_src"] = True
    prev_rev = st.session_state.get("uploader_rev", 0)
    st.session_state["uploader_rev"] = prev_rev + 1
    st.session_state.pop(f"src_file_{prev_rev}", None)
    st.session_state.pop(f"mask_file_{prev_rev}", None)

def _reset_all() -> None:
    st.session_state["edit_src_bytes"] = None
    st.session_state["edit_src_prompt"] = ""
    st.session_state["last_result_bytes"] = None
    st.session_state["force_session_src"] = False
    prev_rev = st.session_state.get("uploader_rev", 0)
    st.session_state["uploader_rev"] = prev_rev + 1
    st.session_state.pop(f"src_file_{prev_rev}", None)
    st.session_state.pop(f"mask_file_{prev_rev}", None)
    clear_edit_payload()

# ────────────────────────── 元画像の決定（※ボタン→ここ→プレビューの順） ─────────
prefill_img = _get_session_image_if_any()
prefill_prompt = st.session_state.get("edit_src_prompt", "")
force = st.session_state.get("force_session_src", False)

effective_src_img: Optional[Image.Image] = None
effective_src_label = ""

if force and prefill_img is not None:
    effective_src_img, effective_src_label = prefill_img, "元画像（セッション優先）"
elif src_file is not None:
    try:
        effective_src_img, effective_src_label = pil_open(src_file), "元画像（アップロード）"
    except Exception as e:
        st.error(f"アップロード画像の読み込みに失敗: {e}")
elif prefill_img is not None:
    effective_src_img, effective_src_label = prefill_img, "元画像（セッション受取）"

# ────────────────────────── プレビュー ────────────────────────────────
if effective_src_img is not None:
    st.subheader("入力プレビュー")
    pl, pr = st.columns([2, 1])
    with pl:
        show_image(effective_src_img, caption=effective_src_label, width="stretch")
    with pr:
        if mask_file:
            try:
                show_image(pil_open(mask_file), caption="マスク（透明=編集 / 不透明=保持）", width="stretch")
            except Exception as e:
                st.warning(f"マスクの読み込みに失敗: {e}")
        else:
            st.info("マスク未指定（全体を編集対象にします）")
else:
    st.info("画像をアップロードするか、前ページの生成結果を受け渡してください。")

st.markdown("---")

# ────────────────────────── 入力フォーム（送信用） ─────────────────────
with st.form("edit_form", clear_on_submit=False):
    edit_prompt = st.text_area(
        "修正プロンプト",
        placeholder="例）背景を夕焼けに、服を赤に、全体をシネマティックに",
        height=140,
        value=prefill_prompt,
    )
    size_label = st.selectbox("サイズ（gpt-image-1 対応）", ["1024x1024", "1024x1536", "1536x1024"], index=0)
    c_run, c_reset = st.columns([2, 1])
    submitted = c_run.form_submit_button("✨ 修正を実行", use_container_width=True)
    do_reset = c_reset.form_submit_button("🧹 リセット", use_container_width=True)

if do_reset:
    _reset_all()
    st.success("セッションをリセットしました。")

# ────────────────────────── 実行（Images API） ────────────────────────
if submitted:
    if effective_src_img is None:
        st.warning("元画像がありません。")
        st.stop()
    if not edit_prompt.strip():
        st.warning("修正プロンプトを入力してください。")
        st.stop()

    src_png = pil_to_png_bytes(effective_src_img)

    mask_png: Optional[bytes] = None
    if mask_file:
        try:
            mask_png = pil_to_png_bytes(pil_open(mask_file))
        except Exception as e:
            st.warning(f"マスク読み込みに失敗したため未使用で続行: {e}")

    with st.spinner("修正中…"):
        try:
            try_model = "gpt-image-1"
            kwargs = dict(model=try_model, prompt=edit_prompt.strip(), size=size_label)
            img_file = as_named_file(src_png, "image.png")
            if mask_png:
                res = client.images.edit(image=img_file, mask=as_named_file(mask_png, "mask.png"), **kwargs)
            else:
                res = client.images.edit(image=img_file, **kwargs)
        except Exception as e1:
            if "must be verified" in str(e1) or "403" in str(e1):
                try_model = "dall-e-2"
                st.info("フォールバック: `dall-e-2` は正方形のみ対応のため 1024x1024 に変換します。")
                kwargs = dict(model=try_model, prompt=edit_prompt.strip(), size="1024x1024")
                img_file = as_named_file(src_png, "image.png")
                if mask_png:
                    res = client.images.edit(image=img_file, mask=as_named_file(mask_png, "mask.png"), **kwargs)
                else:
                    res = client.images.edit(image=img_file, **kwargs)
            else:
                st.error(f"Images API の編集に失敗しました: {e1}")
                st.stop()

    st.success(f"修正完了！（model: {try_model}）")

    # 結果の取り出し
    data0 = res.data[0]
    out_img: Optional[Image.Image] = None
    if getattr(data0, "b64_json", None):
        out_img = Image.open(BytesIO(__import__("base64").b64decode(data0.b64_json))).convert("RGBA")
    elif getattr(data0, "url", None):
        show_image(data0.url, caption="修正結果（URL）", width="stretch")

    # ログ
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "action": "edit",
        "source": "page02",                # ← どのページかを明示
        "model": try_model,
        "size": size_label,
        "mask_used": bool(mask_png),
        "prompt_hash": _sha256_short(edit_prompt.strip()),
    }
    if INCLUDE_FULL_PROMPT_IN_LOG:
        rec["prompt"] = edit_prompt.strip()
    _append_log(rec)

    # 結果の提示 & ダウンロード & 次の元画像にする
    if out_img is not None:
        st.subheader("結果比較")
        a, b = st.columns(2)
        with a: show_image(effective_src_img, caption="修正前（入力）", width="stretch")
        with b: show_image(out_img, caption="修正後（結果）", width="stretch")

        st.markdown("#### ダウンロード")
        download_img_buttons(out_img, basename="edited_result")

        # 下のボタンは state 更新のみ（rerun 不要）
        def _take_over():
            _set_session_image(out_img, prompt_hint=edit_prompt.strip())
            # 上部ボタンでも反映できるよう直近結果にも保持
            st.session_state["last_result_bytes"] = pil_to_png_bytes(out_img)

        st.button("🔁 この結果を次の元画像にする", use_container_width=True, on_click=_take_over)

        # 直近結果として保存（上部ボタンの有効化にも使う）
        st.session_state["last_result_bytes"] = pil_to_png_bytes(out_img)
    else:
        st.info("結果がURLのみの場合は、保存してから再アップロードして再編集してください。")
