# -*- coding: utf-8 -*-
"""抽出JSON(章のHTML) + ローカル図表画像 → 1枚の自己完結HTML(書籍レイアウト)。
使い方: python build_book.py book.json book.html [figures_dir]
出力HTMLをChromeヘッドレスで --print-to-pdf すると、本文がネイティブのテキスト層になる。

見出しのフォントサイズは add_bookmarks.py の検出しきい値と対で決まっている。
CSSのpt値を変えたら add_bookmarks.py の CHAP_SIZE / SEC_SIZE も実測して合わせること
(Chromeの印刷はCSSのptをそのまま出さない。19pt→17.1pt のようにスケールされる)。
"""
import json, io, re, os, sys, html as H

src_json = sys.argv[1]
out_html = sys.argv[2]
fig_dir = sys.argv[3] if len(sys.argv) > 3 else 'figures'

d = json.load(io.open(src_json, encoding='utf-8'))
chapters = d['chapters']
book_title = d.get('book', '')
source_url = d.get('source', '')

_seq = [0]

def fix_html(h, cid):
    def repl(m):
        _seq[0] += 1
        name = m.group(1).rsplit('/', 1)[-1].split('?')[0]
        return ('<figure class="fig" id="fig-%s-%03d"><img src="%s/%s" alt="%s"></figure>'
                % (cid, _seq[0], fig_dir, name, name))
    h = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', repl, h)
    h = re.sub(r'<p class="textmain">(\s|&nbsp;|<br\s*/?>)*</p>', '', h)   # 空段落を落とす
    return h

def split_title(t):
    """'第N章 章名 節名' を (章ラベル, 節名) に割る。合わなければ (None, 全体)。"""
    m = re.match(r'^(第\d+章\s*\S+)\s+(.*)$', t)
    return (m.group(1), m.group(2)) if m else (None, t)

# ---- 目次 ----
toc, cur = [], None
for c in chapters:
    secs = [re.sub(r'<[^>]+>', '', s).replace('&nbsp;', ' ').strip()
            for s in re.findall(r'<h3[^>]*>(.*?)</h3>', c['html'], re.S)]
    label, rest = split_title(c['title'])
    if label and label != cur:
        cur = label
        toc.append('<div class="toc-chap">%s</div>' % H.escape(label))
    toc.append('<div class="toc-item"><a href="#c%s">%s</a></div>' % (c['id'], H.escape(rest)))
    toc += ['<div class="toc-sec">%s</div>' % H.escape(s) for s in secs]

# ---- 本文 ----
body = []
for c in chapters:
    label, title = split_title(c['title'])
    body.append('<section class="chapter" id="c%s">' % c['id'])
    if label:
        body.append('<div class="chap-label">%s</div>' % H.escape(label))
    body.append('<h1 class="chap-title">%s</h1>' % H.escape(title))
    body.append('<div class="content">%s</div>' % fix_html(c['html'], c['id']))
    body.append('</section>')

CSS = """
@page { size: A4; margin: 20mm 17mm 18mm 17mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Yu Gothic","Noto Sans JP","Meiryo","MS PGothic",sans-serif;
       font-size: 10.5pt; line-height: 1.75; color:#111; margin:0; }
.cover { height: 250mm; display:flex; flex-direction:column; justify-content:center;
         text-align:center; page-break-after: always; }
.cover .t { font-size: 26pt; font-weight:700; line-height:1.5; margin-bottom:14mm; }
.cover .s { font-size: 13pt; color:#333; margin-bottom:6mm; }
.cover .m { font-size: 9pt; color:#777; margin-top:24mm; line-height:1.9; }
.toc { page-break-after: always; }
.toc h2 { font-size: 18pt; border-bottom:2px solid #1a4a7a; padding-bottom:3mm; margin-bottom:8mm; }
.toc-chap { font-size: 12pt; font-weight:700; margin:6mm 0 2mm; color:#1a4a7a; }
.toc-item { font-size: 10.5pt; font-weight:600; margin:1.5mm 0 0 4mm; }
.toc-item a { color:#111; text-decoration:none; }
.toc-sec { font-size: 9pt; color:#555; margin:0.6mm 0 0 10mm; }
.chapter { page-break-before: always; }
.chap-label { font-size: 10pt; color:#1a4a7a; font-weight:700; letter-spacing:.05em; }
.chap-title { font-size: 19pt; font-weight:700; margin:2mm 0 8mm;
              border-bottom:2px solid #1a4a7a; padding-bottom:3mm; }
.content h3 { font-size: 14pt; font-weight:700; margin:9mm 0 4mm;
              background:#eef3f8; border-left:5px solid #1a4a7a; padding:2.5mm 3mm;
              page-break-after: avoid; }
.content h4 { font-size: 11.5pt; font-weight:700; margin:6mm 0 2.5mm; color:#1a4a7a;
              page-break-after: avoid; }
.content p { margin:0 0 3.2mm; text-align:justify; }
.content p.textsub2, .content p.job, .content p.doc1 { font-size:9pt; color:#555; }
figure.fig { margin:5mm 0; text-align:center; page-break-inside: avoid; }
figure.fig img { max-width:100%; height:auto; border:1px solid #ddd; }
a { color:#1a4a7a; }
"""

out = ['<!doctype html><html lang="ja"><head><meta charset="utf-8">',
       '<title>%s</title>' % H.escape(book_title),
       '<style>%s</style></head><body>' % CSS,
       '<div class="cover"><div class="t">%s</div>' % H.escape(book_title).replace('　', '<br>'),
       '<div class="s">全%d章</div>' % len(chapters),
       '<div class="m">出典: %s<br>個人利用のためのアーカイブ</div></div>' % H.escape(source_url),
       '<div class="toc"><h2>目次</h2>', ''.join(toc), '</div>',
       ''.join(body), '</body></html>']

io.open(out_html, 'w', encoding='utf-8').write(''.join(out))
print('wrote %s (%d bytes), figures placed: %d' % (out_html, os.path.getsize(out_html), _seq[0]))
