# -*- coding: utf-8 -*-
"""見出しのフォントサイズから章・節を検出してPDFにしおり(アウトライン)を付ける。
使い方: python add_bookmarks.py in.pdf out.pdf [detect.pdf]

detect.pdf を渡すとそちらで見出しを検出する。**OCR層を重ねた後のPDFで検出すると、
図表内のOCR文字を見出しと誤検出する**ので、必ずOCR前のPDFを detect.pdf に指定すること。
(ページ数は変わらないので位置はそのまま使える)

CHAP_SIZE / SEC_SIZE は build_book.py のCSSに対応する実測値。CSSを変えたら
  page.get_text('dict') の span['size'] を数えて付け直す。
"""
import sys, re, os
import fitz

src, dst = sys.argv[1], sys.argv[2]
detect_src = sys.argv[3] if len(sys.argv) > 3 else src
doc, det = fitz.open(src), fitz.open(detect_src)
assert len(det) == len(doc), 'page count mismatch'

CHAP_SIZE, SEC_SIZE, LABEL_SIZE = 17.1, 12.6, 9.0

def spans(page):
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['text'].strip():
                    yield s

chapters, sections = [], []
for pno in range(len(det)):
    buf_chap, buf_sec, label = [], {}, None
    for s in spans(det[pno]):
        sz, t = round(s['size'], 1), s['text'].strip()
        if abs(sz - CHAP_SIZE) < 0.4:
            buf_chap.append(t)
        elif abs(sz - LABEL_SIZE) < 0.25 and re.match(r'^第\d+章', t):
            label = t
        elif abs(sz - SEC_SIZE) < 0.4:
            buf_sec.setdefault(round(s['bbox'][1]), []).append(t)   # 同じy=同じ見出し行
    if buf_chap:
        chapters.append((pno + 1, label, ''.join(buf_chap).strip()))
    for y in sorted(buf_sec):
        sections.append((pno + 1, ''.join(buf_sec[y]).strip()))

print('detected chapters: %d, sections: %d' % (len(chapters), len(sections)))

toc, cur = [], None
for i, (p, label, title) in enumerate(chapters):
    if label and label != cur:
        cur = label
        toc.append([1, label, p])
    lvl = 2 if label else 1
    toc.append([lvl, title, p])
    nxt = chapters[i + 1][0] if i + 1 < len(chapters) else len(doc) + 1
    toc += [[lvl + 1, st, sp] for sp, st in sections if p <= sp < nxt]

doc.set_toc(toc)
doc.save(dst, garbage=3, deflate=True)
print('bookmarks written: %d -> %s (%.1f MB)' % (len(toc), dst, os.path.getsize(dst) / 1e6))
