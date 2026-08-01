"""できたPDFを検証する。抽出テキストは必ずUTF-8ファイルに書き出してから読むこと。

コンソールに直接出すと文字コード変換で化けて、実際は正しいのに「壊れている」と誤判断する。

  python verify.py --pdf out.pdf --expect 168 --words 漢方 コロナ
"""
import argparse
import os

from pypdf import PdfReader

ap = argparse.ArgumentParser()
ap.add_argument("--pdf", required=True)
ap.add_argument("--expect", type=int, default=0)
ap.add_argument("--words", nargs="*", default=[])
ap.add_argument("--dump", default="extracted_text.txt")
a = ap.parse_args()

r = PdfReader(a.pdf)
pages = [p.extract_text() for p in r.pages]
text = "\n=== PAGE ===\n".join(pages)
with open(a.dump, "w", encoding="utf-8") as f:
    f.write(text)

print(f"pages: {len(pages)}" + (f" (expected {a.expect})" if a.expect else ""))
if a.expect and len(pages) != a.expect:
    print("  !! ページ数が一致しない")
print(f"size: {os.path.getsize(a.pdf) / 1024 / 1024:.1f} MB")
print(f"total chars: {len(text)}")

poor = [i + 1 for i, p in enumerate(pages) if len(p.strip()) < 20]
print(f"text-poor pages: {poor}  (元が白紙・扉ページなら正常)")
for wd in a.words:
    print(f"  {wd}: {sum(1 for p in pages if wd in p)} pages")
print(f"抽出テキストを {a.dump} に書き出した。必ず中身を目視すること。")
