# lib/image_utils.py
from __future__ import annotations
import base64
from io import BytesIO
from typing import List
from urllib.request import urlopen

from PIL import Image, ImageOps

def pil_open(file) -> Image.Image:
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")

def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def b64_to_pil(b64data: str) -> Image.Image:
    raw = base64.b64decode(b64data)
    return Image.open(BytesIO(raw)).convert("RGBA")

def url_to_png_bytes(url: str) -> bytes:
    with urlopen(url) as resp:
        data = resp.read()
    img = Image.open(BytesIO(data)).convert("RGBA")
    return pil_to_png_bytes(img)

def as_named_file(data: bytes, filename: str) -> BytesIO:
    bio = BytesIO(data)
    bio.name = filename  # OpenAI Images API がMIME推定に使用
    bio.seek(0)
    return bio

def build_prompt(style_snippet: str, my_snippet: str, free_prompt: str) -> str:
    parts: List[str] = []
    if style_snippet.strip():
        parts.append(style_snippet.strip())
    if my_snippet.strip():
        parts.append(my_snippet.strip())
    if free_prompt.strip():
        parts.append(free_prompt.strip())
    return " :: ".join(parts)
