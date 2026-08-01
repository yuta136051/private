"""OCR付き（検索可能）PDFを作る。画像はそのまま、裏に不可視テキスト層を重ねる。

縦書きページ: 列検出 -> 文字の切れ目で14文字ずつ -> manga-ocr（バッチ）
横組みページ（表紙・奥付など）: EasyOCR
ほぼ白紙のページはOCRを丸ごとスキップする。

  python make_ocr_pdf.py --src capture_trimmed --out out.pdf
  python make_ocr_pdf.py --src capture_trimmed --out test.pdf --start 83 --limit 3

高速化の実測（i5-7200U / 2コア4スレッド, 1ページ約12列）:
  14文字/チャンク が 10文字より 21%速く、しかも精度が高い（境界の重複誤りが減る）
  22文字以上は認識が崩壊する
  int8動的量子化は約10%速いが数字を誤る（70%→20%）ので使わない
  マルチプロセスは2コアでは逆に遅い（1プロセス4スレッドが最速）
"""
import argparse
import glob
import os
import time

import numpy as np
import torch
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

import vcolumns as V

FONT_NAME = "HeiseiMin-W3"  # reportlab内蔵のCID日本語フォント。外部フォント不要
pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

CHARS_PER_CHUNK = 14
BATCH = 12
MAX_COLS_FOR_VERTICAL = 30   # これより多ければ縦書きではなく画像/横組みページ
MIN_MEDIAN_COL_H = 150
BLANK_DARK_FRAC = 0.006      # これ未満ならほぼ白紙としてOCRしない（章扉は0.01程度なので残る）

torch.set_num_threads(os.cpu_count() or 4)


class BatchMangaOcr:
    def __init__(self):
        from manga_ocr import MangaOcr
        self.m = MangaOcr()

    def run(self, images):
        out = []
        for i in range(0, len(images), BATCH):
            px = torch.stack([self.m._preprocess(im) for im in images[i:i + BATCH]])
            with torch.no_grad():
                ids = self.m.model.generate(px.to(self.m.model.device), max_length=300)
            out += [self.m.tokenizer.decode(r.cpu(), skip_special_tokens=True).replace(" ", "")
                    for r in ids]
        return out


def is_blank(path):
    a = np.array(Image.open(path).convert("L"))
    h, w = a.shape
    return float((a[:, int(w * 0.1):int(w * 0.9)] < 128).mean()) < BLANK_DARK_FRAC


def is_vertical(boxes):
    if not boxes or len(boxes) > MAX_COLS_FOR_VERTICAL:
        return False
    return float(np.median([b[3] - b[1] for b in boxes])) >= MIN_MEDIAN_COL_H


def chunks_for(path, boxes):
    """列を文字の切れ目で CHARS_PER_CHUNK 文字ずつに切る"""
    out = []
    for b in boxes:
        chars = V.char_runs(path, b)
        if not chars:
            out.append((b[0], b[1], b[2], b[3]))
            continue
        for i in range(0, len(chars), CHARS_PER_CHUNK):
            g = chars[i:i + CHARS_PER_CHUNK]
            out.append((b[0], g[0][0], b[2], g[-1][1]))
    return out


def draw_vertical(c, text, box, page_h):
    if not text:
        return
    x0, y0, x1, y1 = box
    size = max(4, x1 - x0)
    span = max(1, y1 - y0)
    c.saveState()
    c.translate(x1, page_h - y0)
    c.rotate(-90)                      # 以降ローカルのx軸が画面の下方向になる＝縦書き
    to = c.beginText()
    to.setTextRenderMode(3)            # 3=不可視。Canvasには無いので beginText() 経由で呼ぶ
    to.setFont(FONT_NAME, size)
    to.setTextOrigin(0, -size * 0.85)
    tw = c.stringWidth(text, FONT_NAME, size)
    if tw > 0:
        to.setHorizScale(100.0 * span / tw)
    to.textOut(text)
    c.drawText(to)
    c.restoreState()


def draw_horizontal(c, text, bbox, page_h):
    if not text:
        return
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bh, bw = max(1, y1 - y0), max(1, x1 - x0)
    size = max(4, bh * 0.9)
    to = c.beginText()
    to.setTextRenderMode(3)
    to.setFont(FONT_NAME, size)
    to.setTextOrigin(x0, page_h - y1 + bh * 0.1)   # PIL座標(左上原点)→PDF座標(左下原点)
    tw = c.stringWidth(text, FONT_NAME, size)
    if tw > 0:
        to.setHorizScale(100.0 * bw / tw)
    to.textOut(text)
    c.drawText(to)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.src, "page_*.png")))[a.start - 1:]
    if a.limit:
        files = files[:a.limit]
    print(f"{len(files)} pages", flush=True)

    bocr = BatchMangaOcr()
    ereader = None
    c = canvas.Canvas(a.out)
    t0 = time.time()

    for idx, f in enumerate(files, a.start):
        img = Image.open(f).convert("RGB")
        w, h = img.size
        c.setPageSize((w, h))
        c.drawImage(ImageReader(img), 0, 0, width=w, height=h)   # 元画像は無加工で貼る

        if is_blank(f):
            mode = "blank (skipped)"
        else:
            boxes = V.detect_columns(f)
            if is_vertical(boxes):
                chs = chunks_for(f, boxes)
                crops = [img.crop((b[0] - 3, b[1] - 2, b[2] + 3, b[3] + 2)) for b in chs]
                for b, t in zip(chs, bocr.run(crops)):
                    draw_vertical(c, t, b, h)
                mode = f"vertical {len(boxes)}cols/{len(chs)}chunks"
            else:
                if ereader is None:
                    import easyocr
                    ereader = easyocr.Reader(["ja", "en"], gpu=False)
                res = ereader.readtext(f)
                for bbox, text, _ in res:
                    draw_horizontal(c, text.strip(), bbox, h)
                mode = f"horizontal {len(res)}boxes"

        c.showPage()
        print(f"[{idx}] {os.path.basename(f)} {mode} elapsed={(time.time()-t0)/60:.1f}min",
              flush=True)

    c.save()
    print(f"Saved: {a.out}", flush=True)


if __name__ == "__main__":
    main()
