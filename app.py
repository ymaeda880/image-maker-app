# app.py
import streamlit as st

st.set_page_config(page_title="image_maker_app", page_icon="🎨", layout="wide")

st.title("🎨 image_maker_app")
with st.expander("💰 概算料金（1ドル=150円換算）"):
    st.markdown("""
**gpt-image-1（Images API）**  
| 品質 | 価格(USD) | 価格(円, 概算) |
|------|------------|----------------|
| Low | $0.01 | 約 **1.5円 / 枚** |
| Medium | $0.04 | 約 **6円 / 枚** |
| High | $0.17 | 約 **25.5円 / 枚** |

> 実際の請求はトークン課金（入力テキスト／入力画像／出力画像の各トークン）で算出されます。

**フォールバックモデル（DALL·E 2）**  
| サイズ | 価格(USD) | 価格(円, 概算) |
|---------|------------|----------------|
| 1024×1024 | $0.02 | 約 **3円 / 枚** |
| 512×512 | $0.018 | 約 **2.7円 / 枚** |
| 256×256 | $0.016 | 約 **2.4円 / 枚** |

📝 **注意事項**  
- 為替・仕様変更により変動します（上記は概算目安）。  
- 最新情報は公式Pricingを参照してください。
""")

st.markdown("""
このアプリでは、**プロンプト**を入力して OpenAI Images API（DALL·E）で画像を生成できます。  
左の「ページ」から **『01_画像生成』** を開いてください。
""")

with st.expander("使い方（setup）", expanded=False):
    st.markdown("""
1. `.venv` を作成し `requirements.txt` をインストール  
2. `.streamlit/secrets.toml` に `OPENAI_API_KEY = "sk-XXX"` を設定  
3. `streamlit run app.py` を実行  
4. サイドバーから **01_画像生成** を選択
""")
