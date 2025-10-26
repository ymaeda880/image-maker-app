# pages/01_画像生成.py
# ============================================================
# 🖼️ 画像生成（DALL·E / Images API）＋ ページ内編集（消えない安定版）
# - 直近の生成結果を session_state に保持して常時表示
# - 「この画像を上で編集」押下で編集ターゲットにセット（画像は消えない）
# - 編集は gpt-image-1 固定 / 生成はコストモードで可変
# - response_format は送らない（400回避）
# ============================================================

from __future__ import annotations

import json, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

import streamlit as st
from PIL import Image
from openai import OpenAI

from lib.openai_client import get_client
from lib.presets import STYLE_PRESETS, load_user_presets, save_user_presets
from lib.image_utils import (
    b64_to_pil,
    pil_to_png_bytes,
    url_to_png_bytes,
    build_prompt,
    as_named_file,
)

# ---------- ログ ----------
LOG_DIR = Path("logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "image_gen.log.jsonl"
INCLUDE_FULL_PROMPT_IN_LOG = True
def _sha256_short(t: str) -> str: return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]
def _append_log(rec: dict) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ---------- common_lib（JWT/Cookie） ----------
def _add_commonlib_parent_to_syspath() -> None:
    here = Path(__file__).resolve()
    import sys
    for p in [here.parent, *here.parents]:
        if (p / "common_lib").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            break
_add_commonlib_parent_to_syspath()

def _get_current_user() -> Optional[str]:
    u = st.session_state.get("current_user")
    if u: return u
    try:
        import extra_streamlit_components as stx  # type: ignore
        from common_lib.auth.config import COOKIE_NAME  # type: ignore
        from common_lib.auth.jwt_utils import verify_jwt  # type: ignore
        cm = stx.CookieManager(key="cm_img_gen")
        token = cm.get(COOKIE_NAME)
        payload = verify_jwt(token) if token else None
        if payload and payload.get("sub"):
            return str(payload["sub"])
    except Exception:
        pass
    return None

# ---------- ページ / クライアント ----------
st.set_page_config(page_title="画像生成（+ページ内編集 / 消えない版）", page_icon="🖼️", layout="wide")
client: OpenAI = get_client()

# ---------- セッション初期化（編集 & 生成履歴） ----------
st.session_state.setdefault("edit_target_png", b"")       # ページ内編集の元画像（PNG）
st.session_state.setdefault("edit_result_png", b"")       # 直近の修正版（PNG）
st.session_state.setdefault("edit_last_prompt", "")       # 直近の編集プロンプト
st.session_state.setdefault("edit_source_size", "1024x1024")
st.session_state.setdefault("inline_open", False)         # 編集パネルの開閉状態

# 直近の生成結果（“消えない”表示のために保持）
# [{"png": bytes, "size": "1024x1024", "model": "gpt-image-1", "prompt": "..."}]
st.session_state.setdefault("last_gen_items", [])         # type: ignore[list-item]
st.session_state.setdefault("last_gen_meta", {})          # 任意の補足

# ---------- ヘッダー ----------
user = _get_current_user()
h1, h2 = st.columns([4, 2])
with h1: st.title("🖼️ 画像生成（+ ページ内編集）")
with h2:
    if user: st.success(f"ログイン中: **{user}**")
    else:    st.warning("未ログイン（Cookie 未検出）")

# ---------- サイドバー（コストモード / プリセット） ----------
st.sidebar.header("💸 コストモード（生成のみ）")
cost_mode = st.sidebar.radio(
    "画素数を抑えてコスト最小化できます。",
    ["最安（256px / dall-e-2）", "バランス（512px / dall-e-2）", "標準（1024px / gpt-image-1）"],
    index=2,
)

def _default_gen_model_and_size(mode: str) -> tuple[str, str]:
    if mode.startswith("最安"):     return "dall-e-2", "256x256"
    if mode.startswith("バランス"): return "dall-e-2", "512x512"
    return "gpt-image-1", "1024x1024"

st.sidebar.header("🎨 画風（プリセット）")
style_name = st.sidebar.selectbox("画風を選択", list(STYLE_PRESETS.keys()), index=0)
style_snippet = STYLE_PRESETS[style_name]
if style_snippet: st.sidebar.code(style_snippet, language="text")

st.sidebar.markdown("---")
st.sidebar.header("📝 マイ・プロンプト")
if "user_presets" not in st.session_state:
    st.session_state.user_presets = load_user_presets()
user_presets = st.session_state.user_presets
user_names = ["（なし）"] + list(user_presets.keys())
sel_user_name = st.sidebar.selectbox("マイ・プロンプトを選択", user_names, index=0)
my_snippet = "" if sel_user_name == "（なし）" else user_presets.get(sel_user_name, "")
if my_snippet: st.sidebar.code(my_snippet, language="text")

with st.sidebar.expander("➕ 新規プリセットを追加", expanded=False):
    new_name = st.text_input("プリセット名")
    new_text = st.text_area("プロンプト本文", height=120)
    if st.button("追加する", use_container_width=True):
        name, text = new_name.strip(), new_text.strip()
        if not name or not text:
            st.warning("プリセット名と本文の両方を入力してください。")
        elif name in user_presets:
            st.warning("同名のプリセットが既に存在します。別名にしてください。")
        else:
            user_presets[name] = text
            st.session_state.user_presets = user_presets
            save_user_presets(user_presets)
            st.success("追加しました。")

if sel_user_name != "（なし）":
    if st.sidebar.button(f"🗑️ 『{sel_user_name}』を削除", use_container_width=True):
        try:
            user_presets.pop(sel_user_name, None)
            st.session_state.user_presets = user_presets
            save_user_presets(user_presets)
            st.sidebar.success("削除しました。")
        except Exception as e:
            st.sidebar.error(f"削除に失敗: {e}")

# ---------- 生成フォーム ----------
gen_model_default, gen_size_default = _default_gen_model_and_size(cost_mode)
with st.form("gen_form", clear_on_submit=False):
    prompt_free = st.text_area(
        "自由入力",
        placeholder="例）ライオン / 夕焼け / 広角 / 映画的 など",
        height=120,
        value="",
    )
    c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    with c1:
        st.selectbox("モデル: gpt-image-1" if gen_model_default=="gpt-image-1" else "モデル: dall-e-2",
                     [gen_model_default], index=0, disabled=True)
    with c2:
        if gen_model_default == "dall-e-2":
            size = st.selectbox("サイズ（正方形のみ）", ["256x256", "512x512", "1024x1024"],
                                index=["256x256","512x512","1024x1024"].index(gen_size_default))
        else:
            size_label = st.selectbox("サイズ", ["1024x1024", "1024x1536", "1536x1024", "自動 (auto)"],
                                      index=["1024x1024","1024x1536","1536x1024","自動 (auto)"].index(
                                          gen_size_default if gen_size_default in {"1024x1024","1024x1536","1536x1024"} else "1024x1024"
                                      ))
            size = {"自動 (auto)": "auto"}.get(size_label, size_label)
    with c3:
        n = st.slider("枚数", 1, 4, 1)

    submit = st.form_submit_button("生成する", use_container_width=True)

# ---------- 生成実行 ----------
if submit:
    final_prompt = build_prompt(style_snippet, my_snippet, prompt_free)
    if not final_prompt.strip():
        st.warning("少なくともどれか一つ（画風 / マイ・プロンプト / 自由入力）を入力してください。")
        st.stop()

    st.caption("送信プロンプト（結合結果）"); st.code(final_prompt, language="text")

    with st.spinner("画像を生成中…"):
        try:
            try_model = gen_model_default
            kwargs: Dict[str, Any] = {"model": try_model, "prompt": final_prompt, "n": n}
            if size != "auto": kwargs["size"] = size
            res = client.images.generate(**kwargs)
        except Exception as e1:
            msg = str(e1)
            if "must be verified" in msg or "403" in msg:
                try:
                    try_model = "dall-e-2"
                    st.info("フォールバック：dall-e-2 は縦長/横長/auto 非対応のため 1024x1024 固定にします。")
                    res = client.images.generate(model=try_model, prompt=final_prompt, size="1024x1024", n=n)
                    size = "1024x1024"
                except Exception as e2:
                    st.exception(e2); st.stop()
            else:
                st.exception(e1); st.stop()

    # ---- 直近生成結果をセッションへ保存（= 次の再実行でも消えない）----
    data_list = getattr(res, "data", []) or []
    new_items: List[dict] = []
    for datum in data_list:
        try:
            if getattr(datum, "b64_json", None):
                img = b64_to_pil(datum.b64_json)
                new_items.append({"png": pil_to_png_bytes(img), "size": size, "model": try_model, "prompt": final_prompt})
            elif getattr(datum, "url", None):
                png = url_to_png_bytes(datum.url)  # 押下時取得でも良いが、ここで取ってしまうと後が楽
                new_items.append({"png": png, "size": size, "model": try_model, "prompt": final_prompt})
        except Exception as e:
            st.warning(f"1枚の保存に失敗: {e}")

    st.session_state["last_gen_items"] = new_items
    st.session_state["last_gen_meta"] = {"model": try_model, "size": size, "prompt": final_prompt}

    # ---- ログ（生成）----
    current_user = user or _get_current_user() or "(anonymous)"
    _append_log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": current_user,
        "action": "generate",
        "model": try_model,
        "size": size,
        "n": len(new_items),
        "style_name": style_name,
        "user_preset_name": (None if sel_user_name == "（なし）" else sel_user_name),
        "prompt_hash": _sha256_short(final_prompt),
        "cost_mode": cost_mode,
        **({"prompt": final_prompt} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
    })

    st.success(f"生成完了！（model: {try_model}）")

# ---------- 直近の生成結果（常に表示：消えない） ----------
items: List[dict] = st.session_state.get("last_gen_items") or []
meta: dict = st.session_state.get("last_gen_meta") or {}
if items:
    st.subheader("直近の生成結果")
    cols = st.columns(len(items))
    for i, it in enumerate(items):
        with cols[i]:
            st.image(it["png"], caption=f"{i+1} / {len(items)}（{it['size']}）", use_container_width=True)
            st.download_button(
                "PNGでダウンロード",
                data=it["png"], file_name=f"generated_{i+1}.png", mime="image/png",
                use_container_width=True,
            )
            if st.button("🔧 この画像を上で編集", key=f"edit_set_{i}", use_container_width=True):
                st.session_state["edit_target_png"]  = it["png"]
                st.session_state["edit_result_png"]  = b""
                st.session_state["edit_last_prompt"] = meta.get("prompt", "")
                st.session_state["edit_source_size"] = it.get("size", "1024x1024")
                st.session_state["inline_open"] = True
                st.success("編集対象にセットしました。下の『ページ内編集』を開いてください。")
else:
    st.info("下の『画像生成』から画像を作成すると、ここに最新の結果が表示されます。")

st.markdown("---")

# ---------- ページ内編集（02と同じ順序：ボタン→プレビュー） ----------
if True:  # 常に描画（expander の開閉は状態で制御）
    with st.expander("✏️ 選択した画像のページ内編集（下の生成結果からセットできます）",
                     expanded=bool(st.session_state.get("inline_open", False))):
        edit_model = "gpt-image-1"
        default_size = st.session_state.get("edit_source_size", "1024x1024")
        if default_size not in {"512x512","1024x1024","1024x1536","1536x1024"}:
            default_size = "1024x1024"

        edit_size = st.selectbox(
            "修正サイズ（gpt-image-1）",
            ["512x512","1024x1024","1024x1536","1536x1024"],
            index=["512x512","1024x1024","1024x1536","1536x1024"].index(default_size),
            key="inline_size_select",
        )

        edit_prompt = st.text_area(
            "修正内容（例：森を背景に、幻想的に）",
            value=st.session_state.get("edit_last_prompt", ""),
            height=110,
            key="inline_edit_prompt",
        )

        # --- ボタン（評価を先に） ---
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            do_edit = st.button("🪄 修正版を生成（gpt-image-1）", use_container_width=True)
        with c2:
            keep_as_source = st.button("📥 修正版を“次の元画像”にセット", use_container_width=True,
                                       disabled=(not st.session_state.get("edit_result_png")))
        with c3:
            clear_edit = st.button("🧹 編集対象をクリア", use_container_width=True,
                                   disabled=(not st.session_state.get("edit_target_png")))

        # --- ボタンの効果を適用 ---
        if keep_as_source and st.session_state.get("edit_result_png"):
            st.session_state["edit_target_png"]  = st.session_state["edit_result_png"]
            st.session_state["edit_result_png"]  = b""
            st.session_state["edit_source_size"] = edit_size
            st.session_state["edit_last_prompt"] = ""
            st.session_state["inline_open"] = True
            st.info("修正版を“次の元画像”にセットしました。続けて修正できます。")

        if clear_edit and st.session_state.get("edit_target_png"):
            st.session_state["edit_target_png"]  = b""
            st.session_state["edit_result_png"]  = b""
            st.session_state["edit_last_prompt"] = ""
            st.session_state["inline_open"] = False
            st.info("編集対象をクリアしました。")

        # --- 元画像プレビュー（ボタン適用後に描画） ---
        if st.session_state.get("edit_target_png"):
            st.image(st.session_state["edit_target_png"], caption="編集対象（元画像）", use_container_width=True)
        else:
            st.info("下の『画像生成』から画像を作成し、『🔧 この画像を上で編集』を押すと、ここに表示されます。")

        # --- 修正版の生成（フォーム外） ---
        if do_edit:
            if not st.session_state.get("edit_target_png"):
                st.warning("編集対象画像がありません。下の生成結果からセットしてください。")
            elif not (edit_prompt or "").strip():
                st.warning("修正内容を入力してください。")
            else:
                with st.spinner(f"修正版を生成中…（model={edit_model}, size={edit_size}）"):
                    try:
                        image_file = as_named_file(st.session_state["edit_target_png"], "image.png")
                        res2 = client.images.edit(
                            model=edit_model,
                            image=image_file,
                            prompt=edit_prompt.strip(),
                            size=edit_size,
                        )
                        datum2 = res2.data[0]
                        if getattr(datum2, "b64_json", None):
                            img2: Image.Image = b64_to_pil(datum2.b64_json)
                            st.session_state["edit_result_png"] = pil_to_png_bytes(img2)
                        elif getattr(datum2, "url", None):
                            st.session_state["edit_result_png"] = url_to_png_bytes(datum2.url)
                        else:
                            st.error("修正結果に画像が見つかりませんでした。")
                        st.session_state["edit_last_prompt"] = edit_prompt.strip()
                        st.session_state["edit_source_size"] = edit_size
                        st.session_state["inline_open"] = True

                        # ログ（編集）
                        current_user = _get_current_user() or "(anonymous)"
                        _append_log({
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "user": current_user,
                            "action": "edit",
                            "source": "inline",
                            "model": edit_model,
                            "size": edit_size,
                            "prompt_hash": _sha256_short(edit_prompt.strip()),
                            **({"prompt": edit_prompt.strip()} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
                        })

                        st.success("修正版を生成しました！")
                    except Exception as e:
                        st.error(f"修正に失敗しました: {e}")

        # --- 修正版プレビュー（最後に描画） ---
        if st.session_state.get("edit_result_png"):
            st.markdown("#### 🪄 修正版プレビュー")
            st.image(st.session_state["edit_result_png"], caption="修正結果", use_container_width=True)
            st.download_button(
                "修正版をダウンロード（PNG）",
                data=st.session_state["edit_result_png"],
                file_name="edited_image.png",
                mime="image/png",
                use_container_width=True,
            )
