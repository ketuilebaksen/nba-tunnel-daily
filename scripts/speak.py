#!/usr/bin/env python3
"""
speak.py — turn a plain text file into the narration recording.

The queue used to accept only finished audio, because the voice was recorded
elsewhere. This lets the same queue accept a .txt: the file is read, spoken by
ElevenLabs, and written out as an mp3 with the SAME name. From that point on
nothing else changes — the file goes into exactly the pipeline a recording
would have gone into, gets transcribed with word-level timings, and the edit is
cut to the voice as usual.

Doing it that way rather than editing straight from the text is deliberate. The
editor keys off where the speaker actually breathes, and that is only knowable
from the audio; synthesised speech does not land where the punctuation says it
will.

Long scripts are spoken in chunks and joined. One request for fifteen minutes
of speech times out, and a failure halfway through would cost the whole video.

Usage:  python3 scripts/speak.py content/queue/"Title.txt" work/spoken.mp3
Env:    ELEVEN_API_KEY   required
        ELEVEN_VOICE_ID  overrides the channel's voice
        ELEVEN_MODEL     default eleven_flash_v2_5
"""
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tts  # noqa: E402  — reuse the engine that already works

# ElevenLabs takes far more than this per request, but a chunk that is too big
# is a chunk that can time out and be retried expensively. Around 2500
# characters is a comfortable paragraph group.
CHUNK = int(os.environ.get("SPEAK_CHUNK", "2500"))
GAP = float(os.environ.get("SPEAK_GAP", "0.45"))     # seconds between chunks


def blocks(text):
    """Split into speakable chunks on paragraph, then sentence boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= CHUNK:
            cur = f"{cur}\n\n{p}" if cur else p
            continue
        if cur:
            out.append(cur)
            cur = ""
        if len(p) <= CHUNK:
            cur = p
            continue
        # a single paragraph longer than a chunk: break it on sentences
        sent, buf = re.split(r"(?<=[.!?])\s+", p), ""
        for s in sent:
            if len(buf) + len(s) + 1 <= CHUNK:
                buf = f"{buf} {s}".strip()
            else:
                if buf:
                    out.append(buf)
                buf = s
        cur = buf
    if cur:
        out.append(cur)
    return out


def clean(text):
    """Strip the things a narrator should not read out loud."""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"^\s*#{1,6}\s*", "", t, flags=re.M)      # markdown headings
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)       # bullet markers
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)               # bold
    t = re.sub(r"\*(.+?)\*", r"\1", t)                   # italic
    t = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", t)            # links
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, "work",
                                                             "spoken.mp3")
    with open(src, encoding="utf-8-sig", errors="replace") as f:
        text = clean(f.read())
    if not text:
        raise SystemExit(f"[speak] {src} bos — okunacak metin yok")

    key = os.environ.get("ELEVEN_API_KEY", "").strip()
    if not key:
        raise SystemExit("[speak] ELEVEN_API_KEY yok — depo ayarlarindan ekle")
    voice = tts.pick_voice(key)

    parts = blocks(text)
    words = len(text.split())
    print(f"[speak] {words} kelime, {len(parts)} parca, ses {voice}", flush=True)

    tmp = os.path.join(BASE, "work", "speak")
    os.makedirs(tmp, exist_ok=True)
    pieces = []
    for i, part in enumerate(parts):
        p = os.path.join(tmp, f"s_{i:03d}.mp3")
        if not (os.path.exists(p) and os.path.getsize(p) > 2000):
            print(f"[speak] {i + 1}/{len(parts)} ({len(part)} karakter)",
                  flush=True)
            tts.synth_eleven(part, p, key, voice)
        pieces.append(p)

    # A short silence between chunks, so the joins read as breaths rather than
    # as edits. Concatenating the mp3s directly would butt them together.
    sil = os.path.join(tmp, "gap.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=mono", "-t", f"{GAP}",
                    "-c:a", "libmp3lame", "-b:a", "128k", sil], check=True)

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        for i, p in enumerate(pieces):
            f.write(f"file '{p}'\n")
            if i != len(pieces) - 1:
                f.write(f"file '{sil}'\n")

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", out], check=True)

    dur = tts.ffdur(out)
    print(f"[speak] HAZIR -> {out} ({dur / 60:.1f} dakika)", flush=True)


if __name__ == "__main__":
    main()
