# pages/01_画像生成.py
from __future__ import annotations

import streamlit as st
from PIL import Image

from lib.openai_client import get_client
from lib.presets import STYLE_PRESETS, load_user_presets, save_user_presets
from lib.image_utils import b64_to_pil, pil_to_png_bytes, url_to_png_bytes, build_prompt
from lib.session_bridge import consume_goto_hook, send_image_bytes_and_go
from openai import OpenAI

st.set_page_config(page_title="画像生成（DALL·E / Images API）", page_icon="🖼️", layout="wide")

# ===== rerunフック：01→02 の確実遷移 =====
consume_goto_hook()

client: OpenAI = get_client()

# ===== サイドバー：画風・マイプロンプト =====
st.sidebar.header("🎨 画風（プリセット）")
style_name = st.sidebar.selectbox("画風を選択", list(STYLE_PRESETS.keys()), index=0)
style_snippet = STYLE_PRESETS[style_name]
if style_snippet:
    st.sidebar.code(style_snippet, language="text")

st.sidebar.markdown("---")
st.sidebar.header("📝 マイ・プロンプト（自分のプリセット）")
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
    if st.button("追加する", width="stretch"):
        name = new_name.strip()
        text = new_text.strip()
        if not name or not text:
            st.warning("プリセット名と本文の両方を入力してください。")
        elif name in user_presets:
            st.warning("同名のプリセットが既に存在します。別名にしてください。")
        else:
            user_presets[name] = text
            st.session_state.user_presets = user_presets
            save_user_presets(user_presets)
            st.success(f"『{name}』を追加しました。再描画すると選択肢に現れます。")

if sel_user_name != "（なし）":
    if st.sidebar.button(f"🗑️ 『{sel_user_name}』を削除", width="stretch"):
        try:
            user_presets.pop(sel_user_name, None)
            st.session_state.user_presets = user_presets
            save_user_presets(user_presets)
            st.sidebar.success("削除しました。")
        except Exception as e:
            st.sidebar.error(f"削除に失敗: {e}")

st.sidebar.markdown("---")
st.sidebar.page_link("pages/02_画像修正.py", label="➡ 02_画像修正へ", width="content")  # 保険

st.title("🖼️ 画像生成（DALL·E / Images API）")

# ===== メインフォーム =====
with st.form("gen_form", clear_on_submit=False):
    prompt_free = st.text_area(
        "自由入力（画風・マイ・プロンプトに“追記”する内容）",
        placeholder="例）高層ビルの屋上から見下ろす、雨上がりの濡れた路面、望遠、ボケ味",
        height=130,
        value="",
    )
    c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    with c1:
        size_label = st.selectbox(
            "サイズ（size）",
            ["正方形 (1024x1024)", "縦長 (1024x1536)", "横長 (1536x1024)", "自動 (auto)"],
            index=0,
        )
        label_to_size = {
            "正方形 (1024x1024)": "1024x1024",
            "縦長 (1024x1536)": "1024x1536",
            "横長 (1536x1024)": "1536x1024",
            "自動 (auto)": "auto",
        }
        size = label_to_size[size_label]
    with c2:
        n = st.slider("枚数（n）", min_value=1, max_value=4, value=1)
    with c3:
        submit = st.form_submit_button("生成する", width="stretch")

if submit:
    final_prompt = build_prompt(style_snippet, my_snippet, prompt_free)
    if not final_prompt.strip():
        st.warning("少なくともどれか一つ（画風 / マイ・プロンプト / 自由入力）を入力・選択してください。")
        st.stop()

    st.caption("**送信プロンプト（結合結果）**")
    st.code(final_prompt, language="text")

    with st.spinner("画像を生成中…"):
        try:
            try_model = "gpt-image-1"
            res = client.images.generate(model=try_model, prompt=final_prompt, size=size, n=n)
        except Exception as e1:
            msg = str(e1)
            if "must be verified" in msg or "403" in msg:
                try_model = "dall-e-2"
                st.info("フォールバック: dall-e-2 は縦長/横長/auto 非対応のため、1024x1024 に変換します。")
                res = client.images.generate(model=try_model, prompt=final_prompt, size="1024x1024", n=n)
            else:
                raise

    st.success(f"生成完了！（model: {try_model}）")
    st.subheader("生成結果")
    cols = st.columns(n)

    for i, datum in enumerate(res.data):
        with cols[i]:
            try:
                if getattr(datum, "b64_json", None):
                    img: Image.Image = b64_to_pil(datum.b64_json)
                    st.image(img, caption=f"{i+1} / {n}（{size}）", width="stretch")

                    png_bytes = pil_to_png_bytes(img)
                    st.download_button(
                        "PNGでダウンロード",
                        data=png_bytes,
                        file_name=f"generated_{i+1}.png",
                        mime="image/png",
                        width="stretch",
                    )

                    if st.button("この画像を編集へ送る", key=f"send_edit_{i}", width="stretch"):
                        send_image_bytes_and_go(png_bytes, size=size, model=try_model, prompt=final_prompt)

                elif getattr(datum, "url", None):
                    st.image(datum.url, caption=f"{i+1} / {n}（{size}）", width="stretch")
                    st.link_button("画像URLを開く", datum.url, width="stretch")

                    try:
                        png_bytes = url_to_png_bytes(datum.url)
                    except Exception as e:
                        st.error(f"画像の取得に失敗: {e}")
                        png_bytes = None

                    if st.button("この画像を編集へ送る", key=f"send_edit_url_{i}", width="stretch"):
                        if png_bytes:
                            send_image_bytes_and_go(png_bytes, size=size, model=try_model, prompt=final_prompt)
                        else:
                            st.warning("URL画像の取得に失敗したため、編集ページへ送れませんでした。")
                else:
                    st.error(f"{i+1}枚目の結果に画像データが見つかりませんでした。")
            except Exception as e:
                st.error(f"{i+1}枚目の表示に失敗: {e}")
