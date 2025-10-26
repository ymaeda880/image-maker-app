# pages/50
# _画像生成.py
# ============================================================
# 🖼️ 画像生成（DALL·E / Images API）＋ ページ内編集（02と同じ安定手法）
# ------------------------------------------------------------
# - 生成は「コストモード」で dall-e-2 / gpt-image-1 を使い分け
# - ページ内編集（inline）は常に gpt-image-1（DAE2編集は不安定）
# - 「ボタン評価 → プレビュー描画」の順序を厳守（画像が消える問題を防ぐ）
# - st.rerun() を使わず、session_state で状態管理
# - response_format は一切送らない（400回避）
# ============================================================

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

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

# ============== ログ設定 ==============
LOG_DIR = Path("logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "image_gen.log.jsonl"
INCLUDE_FULL_PROMPT_IN_LOG = True

def _sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def _append_log(record: dict) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ============== common_lib 探索（JWT/Cookie） ==============
def _add_commonlib_parent_to_syspath() -> Optional[Path]:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "common_lib").exists():
            import sys
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return parent
    return None
_add_commonlib_parent_to_syspath()

def _get_current_user() -> Optional[str]:
    u = st.session_state.get("current_user")
    if u:
        return u
    try:
        import extra_streamlit_components as stx  # type: ignore
        from common_lib.auth.config import COOKIE_NAME  # type: ignore
        from common_lib.auth.jwt_utils import verify_jwt  # type: ignore
        cm = stx.CookieManager(key="cm_img_gen")
        token = cm.get(COOKIE_NAME)
        payload = verify_jwt(token) if token else None
        if payload and payload.get("sub"):
            return payload.get("sub")
    except Exception:
        pass
    return None

# ============== ページ設定 / クライアント ==============
st.set_page_config(page_title="画像生成（+ページ内編集・安定版）", page_icon="🖼️", layout="wide")
client: OpenAI = get_client()

# ============== セッション初期化（編集まわり） ==============
# 02_画像修正 と同じ考え方：結果や元画像をバイト列で保持し、ボタンはプレビューより前で評価
st.session_state.setdefault("edit_target_png", b"")       # inline 編集の元画像 PNG
st.session_state.setdefault("edit_result_png", b"")       # 直近の編集結果 PNG
st.session_state.setdefault("edit_last_prompt", "")       # 直近の編集プロンプト
st.session_state.setdefault("edit_source_size", "1024x1024")  # 元画像サイズの覚え
st.session_state.setdefault("inline_open", False)         # 編集パネルを開くか
st.session_state.setdefault("inline_loop", True)          # 連続編集モード（修正版を自動昇格）

# ============== ヘッダー（ログイン表示） ==============
user = _get_current_user()
h1, h2 = st.columns([4, 2])
with h1:
    st.title("🖼️ 画像生成（+ページ内編集）")
with h2:
    if user:
        st.success(f"ログイン中: **{user}**")
    else:
        st.warning("未ログイン（Cookie 未検出）")

# ============== サイドバー：コストモード / プリセット ==============
st.sidebar.header("💸 コストモード（生成にのみ適用）")
cost_mode = st.sidebar.radio(
    "開発中は画素数を抑えてコスト最小化できます。",
    ["最安（256px / dall-e-2）", "バランス（512px / dall-e-2）", "標準（1024px / gpt-image-1）"],
    index=2,
)

def _default_gen_model_and_size(mode: str) -> tuple[str, str]:
    if mode.startswith("最安"): return "dall-e-2", "256x256"
    if mode.startswith("バランス"): return "dall-e-2", "512x512"
    return "gpt-image-1", "1024x1024"

st.sidebar.header("🎨 画風（プリセット）")
style_name = st.sidebar.selectbox("画風を選択", list(STYLE_PRESETS.keys()), index=0)
style_snippet = STYLE_PRESETS[style_name]
if style_snippet:
    st.sidebar.code(style_snippet, language="text")

st.sidebar.markdown("---")
st.sidebar.header("📝 マイ・プロンプト")
if "user_presets" not in st.session_state:
    st.session_state.user_presets = load_user_presets()
user_presets = st.session_state.user_presets
user_names = ["（なし）"] + list(user_presets.keys())
sel_user_name = st.sidebar.selectbox("マイ・プロンプトを選択", user_names, index=0)
my_snippet = "" if sel_user_name == "（なし）" else user_presets.get(sel_user_name, "")
if my_snippet:
    st.sidebar.code(my_snippet, language="text")

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
            st.success(f"『{name}』を追加しました。")

if sel_user_name != "（なし）":
    if st.sidebar.button(f"🗑️ 『{sel_user_name}』を削除", use_container_width=True):
        try:
            user_presets.pop(sel_user_name, None)
            st.session_state.user_presets = user_presets
            save_user_presets(user_presets)
            st.sidebar.success("削除しました。")
        except Exception as e:
            st.sidebar.error(f"削除に失敗: {e}")

st.sidebar.markdown("---")

# ============== 生成フォーム ==============
gen_model_default, gen_size_default = _default_gen_model_and_size(cost_mode)
with st.form("gen_form", clear_on_submit=False):
    prompt_free = st.text_area(
        "自由入力（画風・マイ・プロンプトに“追記”）",
        placeholder="例）夕焼けの空、広角、映画的、濡れた路面の反射、ボケ味",
        height=130,
        value="",
    )

    c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    with c1:
        st.selectbox("モデル（生成）", [gen_model_default], index=0, disabled=True)
    with c2:
        if gen_model_default == "dall-e-2":
            size = st.selectbox(
                "サイズ（正方形のみ）",
                ["256x256", "512x512", "1024x1024"],
                index=["256x256", "512x512", "1024x1024"].index(gen_size_default),
            )
        else:
            size_label = st.selectbox(
                "サイズ（gpt-image-1）",
                ["1024x1024", "1024x1536", "1536x1024", "自動 (auto)"],
                index=["1024x1024", "1024x1536", "1536x1024", "自動 (auto)"].index(
                    gen_size_default if gen_size_default in {"1024x1024", "1024x1536", "1536x1024"} else "1024x1024"
                ),
            )
            size = {"自動 (auto)": "auto"}.get(size_label, size_label)
    with c3:
        n = st.slider("枚数（n）", min_value=1, max_value=4, value=1)

    submit = st.form_submit_button("生成する", use_container_width=True)

# ============== 生成実行 ==============
if submit:
    final_prompt = build_prompt(style_snippet, my_snippet, prompt_free)
    if not final_prompt.strip():
        st.warning("少なくともどれか一つ（画風 / マイ・プロンプト / 自由入力）を入力・選択してください。")
        st.stop()

    st.caption("**送信プロンプト（結合結果）**")
    st.code(final_prompt, language="text")

    with st.spinner("画像を生成中…"):
        try:
            try_model = gen_model_default
            kwargs: Dict[str, Any] = {"model": try_model, "prompt": final_prompt, "n": n}
            if size != "auto":
                kwargs["size"] = size
            res = client.images.generate(**kwargs)
        except Exception as e1:
            msg = str(e1)
            if "must be verified" in msg or "403" in msg:
                try:
                    try_model = "dall-e-2"
                    st.info("フォールバック: dall-e-2 は縦長/横長/auto 非対応のため、1024x1024 に固定します。")
                    res = client.images.generate(model=try_model, prompt=final_prompt, size="1024x1024", n=n)
                    size = "1024x1024"
                except Exception as e2:
                    st.exception(e2); st.stop()
            else:
                st.exception(e1); st.stop()

    # ログ
    current_user = user or _get_current_user() or "(anonymous)"
    _append_log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": current_user,
        "action": "generate",
        "model": try_model,
        "size": size,
        "n": n,
        "style_name": style_name,
        "user_preset_name": (None if sel_user_name == "（なし）" else sel_user_name),
        "prompt_hash": _sha256_short(final_prompt),
        "cost_mode": cost_mode,
        **({"prompt": final_prompt} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
    })

    st.success(f"生成完了！（model: {try_model}）")
    st.subheader("生成結果")

    data_list = getattr(res, "data", []) or []
    if not data_list:
        st.error("画像データが返ってきませんでした。"); st.stop()

    cols = st.columns(len(data_list))

    def _set_url_to_edit_target(url: str, size_str: str, prompt_text: str, btn_key: str):
        """URL返却の画像を“編集対象”にセット（押下時にダウンロード）。"""
        if st.button("🔧 この画像を上で編集", key=btn_key, use_container_width=True):
            with st.spinner("画像を取得中…"):
                try:
                    png_bytes = url_to_png_bytes(url)
                except Exception as e:
                    st.warning(f"URL画像の取得に失敗: {e}")
                    return
            st.session_state["edit_target_png"] = png_bytes
            st.session_state["edit_result_png"] = b""
            st.session_state["edit_last_prompt"] = prompt_text
            st.session_state["edit_source_size"] = size_str
            st.session_state["inline_open"] = True
            st.success("編集対象にセットしました。下の編集セクションを開いてください。")

    for i, datum in enumerate(data_list):
        with cols[i]:
            try:
                if getattr(datum, "b64_json", None):
                    img: Image.Image = b64_to_pil(datum.b64_json)
                    st.image(img, caption=f"{i+1} / {len(data_list)}（{size}）", use_container_width=True)
                    png_bytes = pil_to_png_bytes(img)
                    st.download_button(
                        "PNGでダウンロード",
                        data=png_bytes, file_name=f"generated_{i+1}.png", mime="image/png",
                        use_container_width=True,
                    )
                    if st.button("🔧 この画像を上で編集", key=f"send_edit_{i}", use_container_width=True):
                        st.session_state["edit_target_png"] = png_bytes
                        st.session_state["edit_result_png"] = b""
                        st.session_state["edit_last_prompt"] = final_prompt
                        st.session_state["edit_source_size"] = size
                        st.session_state["inline_open"] = True
                        st.success("編集対象にセットしました。下の編集セクションを開いてください。")
                elif getattr(datum, "url", None):
                    st.image(datum.url, caption=f"{i+1} / {len(data_list)}（{size}）", use_container_width=True)
                    st.link_button("画像URLを開く", datum.url, use_container_width=True)
                    _set_url_to_edit_target(datum.url, size, final_prompt, btn_key=f"send_edit_url_{i}")
                else:
                    st.error(f"{i+1}枚目の結果に画像データが見つかりませんでした。")
            except Exception as e:
                st.error(f"{i+1}枚目の表示に失敗: {e}")

# ============== ✏️ 下部：ページ内編集（02準拠の順番） ==============
with st.expander(
    "✏️ 選択した画像のページ内編集（下の生成結果からセットできます）",
    expanded=bool(st.session_state.get("inline_open", False)),
):
    # 入力系（上） → ボタン（中） → プレビュー（下）の順
    default_size = st.session_state.get("edit_source_size", "1024x1024")
    if default_size not in {"512x512","1024x1024","1024x1536","1536x1024"}:
        default_size = "1024x1024"

    edit_size = st.selectbox(
        "修正サイズ（gpt-image-1）",
        ["512x512","1024x1024","1024x1536","1536x1024"],
        index=["512x512","1024x1024","1024x1536","1536x1024"].index(default_size),
    )

    edit_prompt = st.text_area(
        "修正内容（例：夜景に、ネオンの反射、シネマティック）",
        value=st.session_state.get("edit_last_prompt", ""),
        height=100,
        key="inline_edit_prompt",
    )

    # 連続編集モード（修正版を自動昇格）
    st.session_state["inline_loop"] = st.checkbox(
        "連続編集モード（修正版を自動で“次の元画像”にセット）",
        value=st.session_state.get("inline_loop", True),
        help="オンの間は、修正版が出た直後にそれを元画像に昇格して、続けて修正できます。",
    )

    # ---- 操作ボタン（プレビューより“前”に評価） ----
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        do_edit = st.button("🪄 修正版を生成（gpt-image-1）", use_container_width=True)
    with c2:
        keep_as_source = st.button(
            "📥 修正版を“次の元画像”にセット",
            use_container_width=True,
            disabled=(not st.session_state.get("edit_result_png")),
            help="修正版が出たあとに有効になります。",
        )
    with c3:
        clear_edit = st.button("🧹 編集対象をクリア", use_container_width=True)

    # ---- ボタン効果を先に反映 ----
    if keep_as_source and st.session_state.get("edit_result_png"):
        st.session_state["edit_target_png"] = st.session_state["edit_result_png"]
        st.session_state["edit_result_png"] = b""
        st.session_state["edit_source_size"] = edit_size
        st.session_state["edit_last_prompt"] = ""
        st.info("修正版を“次の元画像”にセットしました。続けて修正できます。")

    if clear_edit:
        st.session_state["edit_target_png"] = b""
        st.session_state["edit_result_png"] = b""
        st.session_state["edit_last_prompt"] = ""
        st.session_state["inline_open"] = False
        st.info("編集対象をクリアしました。")

    # ---- 元画像プレビュー（ボタン適用“後”に描画） ----
    if st.session_state.get("edit_target_png"):
        st.image(st.session_state["edit_target_png"], caption="編集対象（元画像）", use_container_width=True)
    else:
        st.info("下の『画像生成』から画像を作成し、『🔧 この画像を上で編集』を押すと、ここに表示されます。")

    # ---- 修正版の生成 ----
    if do_edit:
        if not st.session_state.get("edit_target_png"):
            st.warning("編集対象の画像がありません。まず『🔧 この画像を上で編集』でセットしてください。")
        elif not edit_prompt.strip():
            st.warning("修正プロンプトを入力してください。")
        else:
            with st.spinner(f"修正版を生成中...（model=gpt-image-1, size={edit_size}）"):
                try:
                    image_file = as_named_file(st.session_state["edit_target_png"], "image.png")
                    res2 = client.images.edit(
                        model="gpt-image-1",
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
                        st.error("修正結果に画像が見つかりませんでした。"); st.stop()

                    # 状態更新
                    st.session_state["edit_last_prompt"] = edit_prompt.strip()
                    st.session_state["edit_source_size"] = edit_size
                    st.session_state["inline_open"] = True

                    # ログ
                    current_user = _get_current_user() or "(anonymous)"
                    _append_log({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "user": current_user,
                        "action": "edit",
                        "source": "inline",   # ページ内編集
                        "model": "gpt-image-1",
                        "size": edit_size,
                        "prompt_hash": _sha256_short(edit_prompt.strip()),
                        **({"prompt": edit_prompt.strip()} if INCLUDE_FULL_PROMPT_IN_LOG else {}),
                    })

                    st.success("修正版を生成しました！")

                    # ★ 連続編集モード：修正版を自動昇格
                    if st.session_state.get("inline_loop") and st.session_state.get("edit_result_png"):
                        st.session_state["edit_target_png"] = st.session_state["edit_result_png"]
                        st.session_state["edit_result_png"] = b""
                        st.info("修正版を“次の元画像”に自動セットしました。続けて修正できます。")

                except Exception as e:
                    st.error(f"修正に失敗しました: {e}")

    # ---- 修正版プレビュー（最後に表示） ----
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
