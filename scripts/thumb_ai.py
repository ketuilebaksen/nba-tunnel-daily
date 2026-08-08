#!/usr/bin/env python3
"""
thumb_ai.py — AI-generated YouTube thumbnail (Google Gemini / Imagen).

The daily script writer supplies `thumb_prompt` (the scene) and `thumb_word`
(the punch phrase). This module wraps them in a fixed house-style prompt so
every thumbnail looks like the same channel, then asks the image model.

Env:
  GEMINI_API_KEY   (falls back to GOOGLE_TTS_KEY — same Google API key works
                    if "Generative Language API" is enabled on the project)
  IMAGE_MODEL      override model id

Returns the path of a 16:9 image, or None so the caller can fall back to the
template thumbnail. Never raises.
"""
import base64, json, os, sys, time, urllib.error, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://generativelanguage.googleapis.com/v1beta/models"
MODELS = [
    os.environ.get("IMAGE_MODEL", "").strip(),
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
]

HYPE_STYLE = (
    "Ultra high quality 16:9 YouTube thumbnail, cinematic sports-hype poster art. "
    "Photoreal basketball arena atmosphere: Madison Square Garden style crowd, "
    "dramatic stage lighting, glowing embers, volumetric light beams, subtle smoke, "
    "New York Knicks colour language (deep blue and vivid orange) with fiery accents. "
    "Bold depth of field, rim lighting on the subject, rich contrast, sharp focus, "
    "professional colour grading. Composition leaves the lower right area clear. "
    "No watermarks, no logos of other brands, no gibberish text anywhere."
)

DOC_STYLE = (
    "Ultra high quality 16:9 YouTube thumbnail in a cinematic sports-documentary "
    "style. Moody, restrained and premium: deep navy and cool steel-blue palette, "
    "one warm key light, soft haze, film grain, shallow depth of field, archival "
    "atmosphere of an empty or dimly lit basketball arena. Editorial composition "
    "with generous negative space in the lower third. Understated and classy, NOT "
    "loud or garish. No watermarks, no other brands' logos, no gibberish text."
)

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import channel as _CH
    HOUSE_STYLE = DOC_STYLE if _CH.get("editorial") == "documentary" else HYPE_STYLE
except Exception:
    HOUSE_STYLE = HYPE_STYLE

def _key():
    return (os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_TTS_KEY", "").strip())

def build_prompt(scene, word=None, subject=None):
    parts = [HOUSE_STYLE]
    if subject:
        parts.append(f"Main subject: {subject}. Generic basketball player, "
                     "no real person's likeness, blue and orange New York uniform, "
                     "intense expression, upper body, left third of the frame.")
    parts.append(f"Scene: {scene}")
    if word:
        parts.append(
            f'Render exactly this text in the lower third: "{word}". '
            + ("Clean bold condensed sans-serif, white with a thin blue underline, "
               "understated and editorial. "
               if HOUSE_STYLE is DOC_STYLE else
               "Heavy extruded 3D display lettering, white and gold with a red "
               "outline and a soft glow. ")
            + "Spell it perfectly. No other text in the image.")
    else:
        parts.append("Do not render any text in the image.")
    return " ".join(parts)


# ----------------------------------------------------------------- OpenAI
OPENAI_URL = "https://api.openai.com/v1/images/generations"

def _openai_key():
    return os.environ.get("OPENAI_API_KEY", "").strip()

def _openai_call(prompt, key, timeout=300):
    body = {
        "model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        "prompt": prompt[:3900],
        "size": os.environ.get("OPENAI_IMAGE_SIZE", "1536x1024"),   # 3:2, cropped to 16:9
        "quality": os.environ.get("OPENAI_IMAGE_QUALITY", "high"),
        "n": 1,
    }
    req = urllib.request.Request(
        OPENAI_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    item = data["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    with urllib.request.urlopen(item["url"], timeout=timeout) as r:   # url mode
        return r.read()

def _call(model, prompt, key, timeout=180):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    req = urllib.request.Request(
        f"{API}/{model}:generateContent?key={key}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("no image part in response")

def generate(scene, word=None, subject=None, out=None):
    if not scene:
        print("[thumb-ai] no scene prompt in script — skipping")
        return None
    prompt = build_prompt(scene, word, subject)
    out = out or os.path.join(BASE, "work", "thumbnail_ai.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 1) OpenAI first when available — this is the look the owner picked
    okey = _openai_key()
    if okey:
        for attempt in range(2):
            try:
                raw = _openai_call(prompt, okey)
                with open(out, "wb") as f:
                    f.write(raw)
                print(f"[thumb-ai] generated with OpenAI "
                      f"{os.environ.get('OPENAI_IMAGE_MODEL', 'gpt-image-1')} "
                      f"({os.path.getsize(out)//1024} KB)")
                return out
            except urllib.error.HTTPError as e:
                msg = ""
                try:
                    msg = e.read().decode()[:250]
                except Exception:
                    pass
                print(f"[thumb-ai] OpenAI HTTP {e.code}: {msg}")
                if e.code in (400, 401, 403, 404):
                    break
                time.sleep(5)
            except Exception as e:
                print(f"[thumb-ai] OpenAI failed: {e}")
                time.sleep(4)

    # 2) Google Gemini / Imagen fallback
    key = _key()
    if not key:
        print("[thumb-ai] no OPENAI_API_KEY / GEMINI_API_KEY — skipping")
        return None

    for model in [m for m in MODELS if m]:
        for attempt in range(2):
            try:
                raw = _call(model, prompt, key)
                with open(out, "wb") as f:
                    f.write(raw)
                print(f"[thumb-ai] generated with {model} "
                      f"({os.path.getsize(out)//1024} KB)")
                return out
            except urllib.error.HTTPError as e:
                msg = ""
                try:
                    msg = e.read().decode()[:220]
                except Exception:
                    pass
                print(f"[thumb-ai] {model} HTTP {e.code}: {msg}")
                if e.code in (400, 401, 403, 404):
                    break              # wrong model / no access -> try next
                time.sleep(4)
            except Exception as e:
                print(f"[thumb-ai] {model} failed: {e}")
                time.sleep(3)
    print("[thumb-ai] all models failed — falling back to template")
    return None

def finish(path, out=None):
    """Crop/pad to exact 16:9, save a 4K master and a <2MB 1280x720 upload copy."""
    try:
        from PIL import Image
    except Exception:
        return path
    out = out or os.path.join(BASE, "work", "thumbnail.jpg")
    img = Image.open(path).convert("RGB")
    target = 16 / 9
    w, h = img.size
    if abs(w / h - target) > 0.01:      # centre-crop to 16:9
        if w / h > target:
            nw = int(h * target)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / target)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    img = img.resize((3840, 2160), Image.LANCZOS)
    img.save(out, quality=95, subsampling=0)
    img.resize((1280, 720), Image.LANCZOS).save(
        out.replace(".jpg", "_yt.jpg"), quality=92)
    return out

if __name__ == "__main__":
    scene = sys.argv[1] if len(sys.argv) > 1 else "a torn contract burning on the court"
    word = sys.argv[2] if len(sys.argv) > 2 else "3 DAYS DEADLINE!"
    p = generate(scene, word)
    if p:
        print(finish(p))
