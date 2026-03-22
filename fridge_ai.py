"""Vision analysis for fridge photos via OpenAI. Falls back to demo mode if no API key."""
import base64
import json
import os
import re

def _image_to_data_url(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    with open(path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def analyze_fridge_image(image_path: str) -> dict:
    """
    Returns dict with keys:
      is_fridge (bool), ingredients (list[str]), short_notes (str), demo (bool optional)
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "is_fridge": True,
            "ingredients": ["milk", "eggs", "cheese", "tomatoes", "lettuce"],
            "short_notes": "Demo mode (set OPENAI_API_KEY for real vision analysis).",
            "demo": True,
        }

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Install the openai package: pip install openai")

    client = OpenAI(api_key=api_key)
    data_url = _image_to_data_url(image_path)

    prompt = """Look at this image carefully.

1) Decide if this is primarily a photo of the INSIDE of a refrigerator (or similar food cold storage) with visible food items. Reject if it is not a fridge interior (e.g. a person, outdoor scene, empty room, screenshot, or unrelated object).

2) If it is a fridge interior, list food ingredients you can reasonably identify from packaging or appearance. Use short English names (e.g. "milk", "cheddar cheese", "cherry tomatoes"). If unsure, omit. Aim for up to 15 items.

Respond with ONLY valid JSON in this exact shape (no markdown):
{"is_fridge": true or false, "ingredients": ["..."], "short_notes": "one short sentence"}"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                ],
            }
        ],
        max_tokens=500,
    )
    raw = (resp.choices[0].message.content or "").strip()
    try:
        data = _parse_json_response(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model did not return valid JSON: {raw[:300]}") from exc
    is_fridge = bool(data.get("is_fridge"))
    ingredients = data.get("ingredients") or []
    if not isinstance(ingredients, list):
        ingredients = []
    ingredients = [str(x).strip() for x in ingredients if str(x).strip()]
    notes = str(data.get("short_notes", "")).strip()
    return {
        "is_fridge": is_fridge,
        "ingredients": ingredients[:20],
        "short_notes": notes,
        "demo": False,
    }

def generate_ai_recipes(ingredients):
    from openai import OpenAI
    client = OpenAI() # It will automatically look for the env var
    
    prompt = f"I have {', '.join(ingredients)}. Suggest 3 creative recipes."
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content