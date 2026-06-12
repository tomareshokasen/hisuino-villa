"""Gemini 2.0 Flash image editing module."""
import io
import base64
import json
import re
from PIL import Image

_api_key: str = ""


def configure(api_key: str) -> None:
    global _api_key
    _api_key = api_key
    import google.generativeai as genai
    genai.configure(api_key=api_key)


def _get_model(model_name: str = "gemini-2.0-flash-exp"):
    import google.generativeai as genai
    return genai.GenerativeModel(model_name)


def _img_to_part(img: Image.Image):
    """Convert PIL image to Gemini inline_data part."""
    import google.generativeai as genai
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return {"mime_type": "image/jpeg", "data": base64.b64encode(buf.read()).decode()}


def _extract_image(response) -> Image.Image:
    """Extract the first image from a Gemini response."""
    for part in response.candidates[0].content.parts:
        # SDK may expose .inline_data or .data depending on version
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            raw = inline.data
            if isinstance(raw, str):
                raw = base64.b64decode(raw)
            return Image.open(io.BytesIO(raw))
    raise ValueError("Geminiから画像が返されませんでした。モデルがこの編集に対応していない可能性があります。")


def _edit(img: Image.Image, prompt: str) -> Image.Image:
    import google.generativeai as genai
    model = _get_model()
    response = model.generate_content(
        [_img_to_part(img), prompt],
        generation_config=genai.GenerationConfig(
            response_modalities=["TEXT", "IMAGE"]
        )
    )
    return _extract_image(response)


def enhance_quality(img: Image.Image) -> Image.Image:
    return _edit(img,
        "この写真を高画質・高解像度に補正してください。ノイズを除去し、"
        "シャープさを向上させ、自然な色調に調整してください。人物の表情・特徴はそのままにしてください。")


def change_necktie_black(img: Image.Image) -> Image.Image:
    return _edit(img,
        "この人物のネクタイを黒色に変えてください。"
        "顔・髪型・体・服装（ネクタイ以外）・背景はそのままにしてください。")


def change_clothing(img: Image.Image, prompt: str) -> Image.Image:
    full = f"この人物の服装を変更してください。変更内容：{prompt}。顔・髪型・ポーズはそのままにしてください。"
    return _edit(img, full)


def remove_props(img: Image.Image) -> Image.Image:
    return _edit(img,
        "この人物が手に持っているもの、または体に付属している不要な小道具（花束・ピースサイン・"
        "飲み物・帽子・眼鏡など）を除去してください。"
        "顔・体・服装はそのままにし、除去した部分は自然に補完してください。")


def remove_others_fill(img: Image.Image) -> Image.Image:
    return _edit(img,
        "この画像の中心の人物に重なっている他の人物をすべて除去してください。"
        "他の人に隠れていた中心人物の体の部分（腕・肩・体など）を自然に補完してください。"
        "中心人物の顔・表情・服装は変えないでください。背景も自然に補完してください。")


def isolate_person(img: Image.Image, label: str) -> Image.Image:
    return _edit(img,
        f"この写真から「{label}」の人物のみを画像中央に自然に残し、"
        "他の人物をすべて除去してください。背景も自然に補完してください。"
        "残す人物の顔・体・服装はそのままにしてください。")


def detect_persons(img: Image.Image) -> list:
    """Return list of person bounding boxes as {index, label, x, y, w, h} (0-1 ratios)."""
    model = _get_model("gemini-2.0-flash")
    import google.generativeai as genai
    response = model.generate_content(
        [_img_to_part(img),
         "この写真に写っている人物全員の顔の位置をJSON配列で返してください。"
         "形式: [{\"index\":0,\"label\":\"人物1\",\"x\":0.1,\"y\":0.05,\"w\":0.2,\"h\":0.35}, ...]"
         "x,y,w,hは画像全体に対する割合（0.0〜1.0）。左上が原点。indexは左から順。"
         "JSONのみ返してください。"]
    )
    text = response.text.strip()
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []
