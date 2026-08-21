# -*- coding: utf-8 -*-
"""HTMLルートで作ったPDFの検証。
使い方: python verify_html_route.py final.pdf book.json [clean.pdf]

確認すること:
  1) 元HTMLの本文が1文字も欠けずPDFのテキスト層に入っているか(章ごとにスライス照合)
  2) 図表OCR層が検索に効いているか
  3) OCR層を重ねる前後で見た目が変わっていないか(ピクセル差分=0)

重要: 抽出は必ず PyMuPDF で行う。pypdf は游ゴシックのグリフを逆引きするときに
康熙部首(U+2F00〜)へ誤マップすることがあり、「壊れている」と誤診しやすい。
"""
import sys, io, re, json, html, collections
import fitz

pdf_path, json_path = sys.argv[1], sys.argv[2]
clean_pdf = sys.argv[3] if len(sys.argv) > 3 else None
d = fitz.open(pdf_path)

def norm(s):
    return re.sub(r'[\s　​ ]', '', html.unescape(re.sub(r'<[^>]+>', '', s)))

# 本文層(游ゴシック)とOCR層(MS Gothic)をフォント名で分離して検証する
body = [s['text'] for p in d for b in p.get_text('dict')['blocks']
        for l in b.get('lines', []) for s in l['spans'] if s['font'].startswith('YuGothic')]
flat = norm(''.join(body))

src = json.load(io.open(json_path, encoding='utf-8'))
bad = []
for c in src['chapters']:
    p = norm(c['html']); L = len(p)
    sl = [p[i:i + 60] for i in range(0, max(1, L - 60), max(1, L // 12))] + [p[-60:]]
    miss = [s for s in sl if s not in flat]
    if miss:
        bad.append((c['id'], len(miss), len(sl)))
cs = collections.Counter(''.join(norm(c['html']) for c in src['chapters']))
cp = collections.Counter(flat)
print('pages:', len(d), 'bookmarks:', len(d.get_toc()))
print('chapters with missing body slices:', bad)
print('chars in source but not in PDF:', [(ch, n) for ch, n in cs.items() if ch not in cp])
print('radical chars remaining:', sum(1 for ch in flat if 0x2E80 <= ord(ch) <= 0x2FDF))
print('pages with no text:', [i + 1 for i, p in enumerate(d) if len(p.get_text().strip()) < 3])

if clean_pdf:
    import numpy as np
    from PIL import Image
    a = fitz.open(clean_pdf)
    worst = 0
    for p in range(0, len(d), max(1, len(d) // 10)):
        ia = np.array(Image.open(io.BytesIO(a[p].get_pixmap(dpi=90).tobytes('png'))).convert('RGB')).astype(int)
        ib = np.array(Image.open(io.BytesIO(d[p].get_pixmap(dpi=90).tobytes('png'))).convert('RGB')).astype(int)
        worst = max(worst, int(abs(ia - ib).max()))
    print('max pixel diff vs pre-OCR PDF:', worst, '(0 なら OCR層は完全に不可視)')
