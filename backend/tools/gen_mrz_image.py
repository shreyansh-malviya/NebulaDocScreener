"""Render legal synthetic passport MRZ images (valid + tampered) to test the image path.
Run from backend/:  python -m tools.gen_mrz_image [out_dir]
"""
import sys

from PIL import Image, ImageDraw, ImageFont

from app.core import mrz


def render(l1: str, l2: str, path: str) -> None:
    im = Image.new("RGB", (1080, 260), (250, 250, 250))
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/cour.ttf", 34)   # Courier New (monospace)
    except Exception:
        font = ImageFont.load_default()
    d.text((15, 60), l1, fill=(0, 0, 0), font=font)
    d.text((15, 150), l2, fill=(0, 0, 0), font=font)
    im.save(path)
    print("wrote", path)


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    v = mrz.sample_passport(tampered=False)
    t = mrz.sample_passport(tampered=True)
    render(v["line1"], v["line2"], f"{out}/mrz_valid.png")
    render(t["line1"], t["line2"], f"{out}/mrz_tampered.png")


if __name__ == "__main__":
    main()
