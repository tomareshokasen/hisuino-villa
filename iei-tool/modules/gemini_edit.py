import io
import json
import re

import google.generativeai as genai
from PIL import Image


def configure(api_key: str):
    genai.configure(api_key=api_key)


def _get_model(name: str = "gemini-2.0-flash-exp"):
    return genai.GenerativeModel(name)


def _edit(img: Image.Image, prompt: str) -> Image.Image:
    """Send image + instruction to Gemini, return the edited image."""
    model = _get_model()
    response = model.generate_content(
        [prompt, img.convert("RGB")],
        generation_config=genai.GenerationConfig(
            response_modalities=["TEXT", "IMAGE"]
        ),
    )
    for part in response.candidates[0].content.parts:
        # SDK may surface image data under different attributes depending on version
        data = None
        if hasattr(part, "inline_data") and part.inline_data:
            data = part.inline_data.data
        elif hasattr(part, "data") and part.mime_type and part.mime_type.startswith("image/"):
            data = part.data
        if data:
            import base64
            raw = base64.b64decode(data) if isinstance(data, str) else data
            return Image.open(io.BytesIO(raw)).convert("RGBA")
    raise ValueError("Geminiから画像が返されませんでした。APIキーと権限を確認してください。")


def enhance_quality(img: Image.Image) -> Image.Image:
    return _edit(
        img,
        "この写真を高画質・高解像度に補正してください。"
        "ノイズを除去し、シャープさを向上させ、自然な色調に調整してください。",
    )


def change_necktie_black(img: Image.Image) -> Image.Image:
    return _edit(
        img,
        "この人物のネクタイを黒色に変えてください。"
        "顔・髪型・体・服・背景はそのままにし、ネクタイの色だけ黒にしてください。",
    )


def change_clothing(img: Image.Image, prompt: str) -> Image.Image:
    return _edit(
        img,
        f"この人物の服装を変更してください。指示：{prompt}"
        "顔・髪型・ポーズ・背景はそのままにしてください。",
    )


def remove_objects(img: Image.Image) -> Image.Image:
    """Remove hand-held items (bouquets, props, peace signs, etc.)."""
    return _edit(
        img,
        "この人物の手や体の周りにある持ち物（花束・ピースサイン・小道具・飲み物など）を除去してください。"
        "顔・体・服装はそのままにし、持ち物が消えた部分は自然に補完してください。",
    )


def remove_others_fill(img: Image.Image) -> Image.Image:
    """Remove overlapping people and fill missing body parts of the subject."""
    return _edit(
        img,
        "この画像で中心の人物に重なっている他の人物を除去してください。"
        "他の人に隠れていた中心人物の体（腕・肩など）を自然に補完・修復してください。"
        "中心人物の顔・表情・服装は変えないでください。",
    )


def detect_persons(img: Image.Image) -> list:
    """Return list of person bounding boxes as relative coords (0..1)."""
    model = _get_model("gemini-2.0-flash")
    response = model.generate_content(
        [
            "この写真に写っている人物全員の位置を特定してください。"
            "JSON配列のみ返してください（説明不要）。"
            '形式: [{"index":0,"label":"人物1","x":0.1,"y":0.05,"w":0.2,"h":0.4}, ...]'
            "x,y,w,hは画像全体に対する割合（0.0〜1.0）。左上が原点。",
            img.convert("RGB"),
        ]
    )
    text = response.text.strip()
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []


def isolate_person(img: Image.Image, label: str) -> Image.Image:
    return _edit(
        img,
        f"この写真から「{label}」の人物だけを残してください。"
        "他の人物は自然に除去し、隠れていた背景を補完してください。"
        "対象人物の顔・体・服装は変えないでください。",
    )
