"""Classical image-forensics bank for Module 3 (CPU, no GPU, no model downloads).

An ensemble of weak, explainable signals — each returns a 0..1 risk score, optional
regions, and a heatmap/visualisation PNG. They are FUSED (noisy-OR + spatial agreement);
none is trusted alone. The strong DL localizer (TruFor/CAT-Net) is added later behind a
fallback so this bank always works. See Rough/research/02-tampering-forensics.md.

Honest limits (encoded as low weights): ELA is a demo visual, weak alone; metadata can only
RAISE suspicion (scans legitimately have none). Copy-move (duplicated region) is the strong,
document-relevant classical cue — it directly targets stamp/seal cloning.
"""
from __future__ import annotations

import io
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance

try:
    import piexif
except Exception:  # pragma: no cover
    piexif = None


def _decode(image_bytes: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes() if ok else b""


# ---------------------------------------------------------------------------
def ela(image_bytes: bytes, quality: int = 90) -> dict:
    """Error Level Analysis — re-save at known JPEG quality, amplify the difference.
    Weak alone (edges always light up), so weighted LOW; included for the heatmap."""
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf)
    diff = ImageChops.difference(im, resaved)
    extrema = diff.getextrema()
    max_diff = max((e[1] for e in extrema), default=1) or 1
    amplified = ImageEnhance.Brightness(diff).enhance(255.0 / max_diff)
    gray = np.asarray(amplified.convert("L"), dtype=np.float32)
    # heuristic score: how much of the image shows elevated recompression error
    score = float(np.clip((gray > 40).mean() * 2.5, 0.0, 1.0))
    heat = cv2.applyColorMap(gray.astype(np.uint8), cv2.COLORMAP_JET)
    return {"name": "ela", "score": round(score, 4), "regions": [], "heatmap": _png(heat),
            "weight": 0.10, "note": "ELA amplified recompression error (weak signal)."}


def copy_move(image_bytes: bytes, min_dist: float = 40.0, desc_thresh: int = 48,
              min_cluster: int = 15, bin_size: int = 8) -> dict:
    """Copy-move detection via ORB self-matching + TRANSLATION-OFFSET clustering.

    A genuine duplicated region shares ONE consistent (dx, dy) offset between source and
    copy; a single textured region's internal matches scatter across many offsets. So we
    score only the DOMINANT consistent-offset cluster — this avoids the false positive
    where one noisy patch would otherwise look 'duplicated'.
    """
    from collections import Counter

    img = _decode(image_bytes)
    if img is None:
        return {"name": "copy_move", "score": 0.0, "regions": [], "heatmap": b"",
                "weight": 0.45, "note": "undecodable image"}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=3000)
    kp, des = orb.detectAndCompute(gray, None)

    good: list[tuple] = []   # (p1, p2, dx, dy)
    if des is not None and len(kp) > 3:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        for m in bf.knnMatch(des, des, k=3):
            for cand in m[1:]:                       # m[0] is the descriptor matching itself
                p1, p2 = kp[cand.queryIdx].pt, kp[cand.trainIdx].pt
                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                if cand.distance < desc_thresh and (dx * dx + dy * dy) ** 0.5 > min_dist:
                    good.append((p1, p2, dx, dy))

    # cluster by quantised offset; the largest cluster = the duplicated translation
    offsets = Counter((round(g[2] / bin_size), round(g[3] / bin_size)) for g in good)
    dominant_key, dominant = (offsets.most_common(1)[0] if offsets else (None, 0))
    cluster = [g for g in good
               if dominant_key and (round(g[2] / bin_size), round(g[3] / bin_size)) == dominant_key]

    vis = img.copy()
    for p1, p2, _, _ in cluster[:300]:
        cv2.line(vis, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 0, 255), 1)
    regions = []
    if cluster:
        xs = [int(c) for g in cluster for c in (g[0][0], g[1][0])]
        ys = [int(c) for g in cluster for c in (g[0][1], g[1][1])]
        regions = [[min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]]

    score = (float(np.clip(dominant / (min_cluster * 2.0), 0.0, 1.0))
             if dominant >= min_cluster else float(dominant / (min_cluster * 4.0)))
    return {"name": "copy_move", "score": round(score, 4), "regions": regions, "heatmap": _png(vis),
            "weight": 0.45,
            "note": f"{dominant} matches share a consistent offset (of {len(good)} candidates)."}


def metadata(image_bytes: bytes) -> dict:
    """EXIF triage — editing-software signature can only RAISE suspicion, never clear."""
    notes: list[str] = []
    score = 0.0
    if piexif is not None:
        try:
            ex = piexif.load(image_bytes)
            soft = ex.get("0th", {}).get(piexif.ImageIFD.Software)
            if soft:
                s = soft.decode(errors="replace") if isinstance(soft, (bytes, bytearray)) else str(soft)
                notes.append(f"Software tag: {s}")
                if any(k in s.lower() for k in ("photoshop", "gimp", "snapseed", "paint", "affinity", "pixelmator")):
                    score = 0.6
                    notes.append("Editing-software signature present.")
        except Exception as exc:
            notes.append(f"no readable EXIF ({exc})")
    else:
        notes.append("piexif unavailable")
    return {"name": "metadata", "score": round(score, 4), "regions": [], "heatmap": b"",
            "weight": 0.15, "note": "; ".join(notes) or "no metadata findings"}


# ---------------------------------------------------------------------------
def _iou(a: list[int], b: list[int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix, iy = max(ax, bx), max(ay, by)
    iX, iY = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, iX - ix) * max(0, iY - iy)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def analyze(image_bytes: bytes) -> list[dict]:
    """Run the classical bank; return one dict per signal."""
    return [copy_move(image_bytes), ela(image_bytes), metadata(image_bytes)]


def fuse_scores(signals: list[dict]) -> tuple[float, bool]:
    """Noisy-OR fusion + spatial-agreement bonus (≥2 region-bearing signals overlap)."""
    prod = 1.0
    for s in signals:
        prod *= (1.0 - s["weight"] * float(s["score"]))
    fused = 1.0 - prod
    region_sets = [s["regions"] for s in signals if s.get("regions")]
    agreement = False
    for i in range(len(region_sets)):
        for j in range(i + 1, len(region_sets)):
            if any(_iou(r1, r2) > 0.1 for r1 in region_sets[i] for r2 in region_sets[j]):
                agreement = True
    if agreement:
        fused = min(1.0, fused + 0.15)
    return round(float(fused), 4), agreement
