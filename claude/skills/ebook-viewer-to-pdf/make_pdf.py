"""トリム済み画像を1つのPDFに結合する（OCRなし・画像のみ）。

  python make_pdf.py --src capture_trimmed --out "C:\\Users\\me\\Desktop\\本.pdf"
"""
import argparse
import glob
import os

import img2pdf
from pypdf import PdfReader

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

files = sorted(glob.glob(os.path.join(a.src, "page_*.png")))
print(f"{len(files)} images -> {a.out}")
with open(a.out, "wb") as f:
    f.write(img2pdf.convert(files))

print(f"PDF pages: {len(PdfReader(a.out).pages)}")
print(f"size: {os.path.getsize(a.out) / 1024 / 1024:.1f} MB")
