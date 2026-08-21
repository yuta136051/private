# -*- coding: utf-8 -*-
"""図表画像をOCRし、PDF上の該当画像位置に不可視テキスト層を重ねる。見た目は一切変わらない。
本文がすでにネイティブのテキスト層を持つPDF(build_book.py + Chrome印刷)専用。

使い方: python ocr_overlay.py in.pdf out.pdf [figures_dir] [cache.json]
必ず PYTHONUTF8=1 PYTHONIOENCODING=utf-8 を付ける(cp932でEasyOCRの進捗表示がクラッシュする)。
OCRは1枚あたりCPUで5〜15秒。100枚超なら run_in_background で流す。
"""
import os, io, json, glob, time, hashlib, sys
import fitz  # PyMuPDF

SRC_PDF = sys.argv[1]
OUT_PDF = sys.argv[2]
FIG_DIR = sys.argv[3] if len(sys.argv) > 3 else 'figures'
CACHE = sys.argv[4] if len(sys.argv) > 4 else 'ocr_all.json'
FONTFILE = r'C:\Windows\Fonts\msgothic.ttc'   # 不可視なので見た目に影響しない

def run_ocr():
    data = json.load(io.open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    files = sorted(glob.glob(os.path.join(FIG_DIR, '*.*')))
    todo = [f for f in files if os.path.basename(f) not in data]
    if todo:
        import easyocr
        reader = easyocr.Reader(['ja', 'en'], gpu=False, verbose=False)
        for i, f in enumerate(todo, 1):
            t0 = time.time()
            try:
                res = reader.readtext(f)
            except Exception as e:
                print('OCR FAIL', f, e, flush=True); res = []
            data[os.path.basename(f)] = [
                {'box': [[float(x), float(y)] for x, y in bbox], 'text': txt, 'conf': float(conf)}
                for bbox, txt, conf in res]
            json.dump(data, io.open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)  # 逐次保存
            print('[%d/%d] %s boxes=%d %.1fs' % (i, len(todo), os.path.basename(f),
                                                 len(res), time.time() - t0), flush=True)
    print('OCR done: %d figures, %d boxes' % (len(data), sum(len(v) for v in data.values())),
          flush=True)
    return data

def md5(b): return hashlib.md5(b).hexdigest()

def overlay(ocr):
    # 画像とPDF内の配置矩形は、埋め込み画像バイト列のMD5で突き合わせる(ファイル名は残らないため)
    local = {md5(io.open(f, 'rb').read()): os.path.basename(f)
             for f in glob.glob(os.path.join(FIG_DIR, '*.*'))}
    doc = fitz.open(SRC_PDF)
    placed, matched, unmatched = 0, set(), 0
    for pno in range(len(doc)):
        page = doc[pno]
        for info in page.get_images(full=True):
            xref = info[0]
            try:
                img = doc.extract_image(xref)
            except Exception:
                continue
            name = local.get(md5(img['image']))
            if not name:
                unmatched += 1; continue
            boxes = ocr.get(name) or []
            rects = page.get_image_rects(xref) if boxes else []
            if not rects:
                continue
            iw, ih = img['width'], img['height']
            for r in rects:
                sx, sy = r.width / iw, r.height / ih
                for b in boxes:
                    txt = (b['text'] or '').strip()
                    if not txt or b['conf'] < 0.15:
                        continue
                    xs = [p[0] for p in b['box']]; ys = [p[1] for p in b['box']]
                    x0 = min(xs) * sx + r.x0
                    y0, y1 = min(ys) * sy + r.y0, max(ys) * sy + r.y0
                    bh = max(1.0, y1 - y0)
                    try:
                        page.insert_text(fitz.Point(x0, y1 - bh * 0.18), txt,
                                         fontsize=max(3.0, min(bh * 0.85, 40.0)),
                                         fontfile=FONTFILE, fontname='ocrjp',
                                         render_mode=3,          # 3 = 不可視
                                         overlay=True)
                        placed += 1
                    except Exception:
                        pass
                matched.add(name)
    doc.save(OUT_PDF, garbage=3, deflate=True); doc.close()
    print('overlay: %d boxes on %d figures (unmatched xrefs: %d)'
          % (placed, len(matched), unmatched), flush=True)
    miss = sorted(set(local.values()) - matched)
    print('figures not placed:', miss, flush=True)

if __name__ == '__main__':
    overlay(run_ocr())
    print('WROTE', OUT_PDF, os.path.getsize(OUT_PDF), flush=True)
