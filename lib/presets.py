# lib/presets.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict

# 固定の画風プリセット（日本語＋英語併記）
STYLE_PRESETS: Dict[str, str] = {
    "（なし）": "",
    "写真風":"プロのカメラマンが一眼レフカメラで撮ったような，素晴らしい写真",
    "水彩画風":"プロの画家が水彩画で描いた素晴らしい絵",
    "油絵画風":"プロの画家が油彩画で描いた素晴らしい絵",
    "アニメ風":"日本のアニメ作家が書いた絵",
    "🎞️ シネマティック風": "映画のような構図とドラマチックな照明（cinematic, dramatic lighting, depth of field, film grain, 35mm lens）",
    "🌅 夕暮れの都市": "夕焼けに染まる都市の風景、温かい光とビルの窓の輝き（sunset cityscape, warm colors, glowing windows, atmospheric light）",
    "🖋️ 水彩画風": "水彩画スタイル、淡い色彩、柔らかい筆致、にじみのある透明感（watercolor painting style, soft brush strokes, gentle tone）",
    "🌌 未来都市": "近未来的な都市、ネオンライト、サイバーパンク風の雰囲気（futuristic city, neon lights, cyberpunk style, ultra-detailed）",
    "🌿 自然・風景": "緑豊かな森、木漏れ日、自然光が差し込むリアルな風景（lush forest, sunlight filtering through trees, vivid colors, realistic lighting）",
    "👩‍💻 AIイラスト風人物": "アニメ風の人物イラスト、繊細な線画と柔らかい光（anime style portrait, highly detailed, soft light, digital art, pastel colors）",
    
}

def _user_presets_path() -> Path:
    # lib/ から 1つ上（プロジェクトルート）→ pages/presets_user.json
    return Path(__file__).resolve().parents[1] / "pages" / "presets_user.json"

def load_user_presets() -> Dict[str, str]:
    p = _user_presets_path()
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_user_presets(presets: Dict[str, str]) -> None:
    p = _user_presets_path()
    try:
        p.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        import streamlit as st
        st.warning(f"マイ・プロンプトの保存に失敗しました: {e}")
