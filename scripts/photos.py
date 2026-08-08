#!/usr/bin/env python3
"""
photos.py — build the photo library for today's video.

Priority 1: photos the owner uploaded to the GitHub release tagged `photos`
            (already downloaded into work/photos by the workflow).
Priority 2: auto-fetch high-resolution, freely-licensed photos from Wikimedia
            Commons for the people named in today's script. For players we
            download several candidates and keep the one with the biggest,
            clearest face — that is what the close-up thumbnail needs.

Credits go to work/photo_credits.txt and are appended to the description.

Usage: python3 scripts/photos.py content/current/script.json
"""
import json, os, re, sys, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "work", "photos")
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "knicks-auto-daily/1.0 (github actions; contact: repo owner)"}
MIN_TIERS = [(1800, 1100), (1400, 900), (1000, 650)]   # relax until something fits

NAMES = ["Jalen Brunson", "Karl-Anthony Towns", "OG Anunoby", "Mikal Bridges",
         "Josh Hart", "Miles McBride", "Mitchell Robinson", "Landry Shamet",
         "Tyler Kolek", "Pacome Dadiet", "Guerschon Yabusele", "Jordan Clarkson",
         "Ariel Hukporti", "Kevin McCullar", "Mike Brown", "Leon Rose",
         "Tom Thibodeau", "Julius Randle", "RJ Barrett", "Immanuel Quickley",
         "Donte DiVincenzo", "Madison Square Garden", "New York Knicks"]

def fetch_json(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def face_score(path):
    """Bigger, sharper faces score higher; 0 when no face is found."""
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return 0.0
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        casc = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = casc.detectMultiScale(gray, 1.1, 5, minSize=(70, 70))
        if len(faces) == 0:
            return 0.0
        fw = max(f[2] for f in faces)
        return fw * (min(w, h) / 1000.0)      # face pixels weighted by resolution
    except Exception:
        return 0.0

def candidates(term):
    """[(area, url, artist, licence, title)] — best resolution first."""
    try:
        d = fetch_json({
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f'filetype:bitmap "{term}"', "gsrnamespace": "6",
            "gsrlimit": "14", "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": "4000"})
    except Exception as e:
        print(f"[photos] search failed for {term}: {e}")
        return []
    pages = (d.get("query") or {}).get("pages") or {}
    rows = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        w, h = ii.get("width", 0), ii.get("height", 0)
        if not ii.get("thumburl"):
            continue
        meta = ii.get("extmetadata") or {}
        artist = re.sub(r"<[^>]+>", "",
                        (meta.get("Artist") or {}).get("value", "")).strip()
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        rows.append((w, h, w * h, ii["thumburl"], artist, lic, p.get("title", "")))
    for min_w, min_h in MIN_TIERS:
        ok = [r for r in rows if r[0] >= min_w and r[1] >= min_h]
        if ok:
            ok.sort(key=lambda r: -r[2])
            return [(r[2], r[3], r[4], r[5], r[6]) for r in ok]
    rows.sort(key=lambda r: -r[2])
    return [(r[2], r[3], r[4], r[5], r[6]) for r in rows]

def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r, open(path, "wb") as o:
        o.write(r.read())

def main():
    os.makedirs(OUT, exist_ok=True)
    existing = [f for f in os.listdir(OUT)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    if len(existing) >= 12:
        print(f"[photos] owner library present ({len(existing)}) — skipping fetch")
        return

    with open(sys.argv[1]) as f:
        script = json.load(f)
    text = json.dumps(script).lower()

    wanted = [n for n in NAMES if n.split()[-1].lower() in text][:10]
    for base in ("Jalen Brunson", "Karl-Anthony Towns", "Mikal Bridges",
                 "OG Anunoby", "Josh Hart", "New York Knicks",
                 "Madison Square Garden"):
        if base not in wanted:
            wanted.append(base)
    wanted = wanted[:14]

    credits, n_ok = [], 0
    for term in wanted:
        query = term if "Garden" in term else term + " basketball"
        cands = candidates(query)
        if not cands:
            print(f"[photos] no candidate for {term}")
            continue
        is_person = term not in ("New York Knicks", "Madison Square Garden")
        dest = os.path.join(OUT, re.sub(r"[^a-z0-9]+", "_", term.lower()) + ".jpg")
        best = None                       # (score, tmp, artist, lic, title)
        for k, (_, url, artist, lic, title) in enumerate(
                cands[:4] if is_person else cands[:1]):
            tmp = f"{dest}.c{k}"
            try:
                download(url, tmp)
            except Exception as e:
                print(f"[photos] dl fail {term} #{k}: {e}")
                continue
            score = face_score(tmp) if is_person else 1.0
            if best is None or score > best[0]:
                if best:
                    os.remove(best[1])
                best = (score, tmp, artist, lic, title)
            else:
                os.remove(tmp)
            if is_person and score > 220:     # already a strong close-up
                break
        if not best:
            continue
        score, tmp, artist, lic, title = best
        os.replace(tmp, dest)
        n_ok += 1
        if artist or lic:
            credits.append(f"{term}: {title.replace('File:', '')} — {artist} "
                           f"({lic}), via Wikimedia Commons")
        try:
            from PIL import Image
            print(f"[photos] {term} -> {Image.open(dest).size} face={score:.0f}")
        except Exception:
            print(f"[photos] {term} ok")

    if credits:
        with open(os.path.join(BASE, "work", "photo_credits.txt"), "w") as f:
            f.write("\n".join(credits) + "\n")
    print(f"[photos] DONE — {n_ok} photos")

if __name__ == "__main__":
    main()
