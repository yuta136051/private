"""撮影した画像から実際のページ境界を検出して正確に切り出す。

固定ピクセルでの切り出しはページごとの微妙なズレを吸収できず、狭ければ本文が切れ、
広ければ隣ページや黒帯が残る。ここで1枚ずつ境界を検出するので、撮影側は広めでよい。

  python trim.py --src capture --out capture_trimmed
"""
import argparse
import glob
import os

import numpy as np
from PIL import Image

PAD = 14
BG_TOL = 18
MIN_GAP_RUN = 8


def largest_true_run(mask):
    best_start, best_len = 0, 0
    cur_start, cur_len = None, 0
    for i, v in enumerate(mask):
        if v:
            if cur_start is None:
                cur_start, cur_len = i, 1
            else:
                cur_len += 1
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
        else:
            cur_start, cur_len = None, 0
    return best_start, best_start + best_len


def process(path, out_path):
    arr = np.array(Image.open(path).convert("RGB"))
    h, w, _ = arr.shape

    # 背景色は画像の縁から毎回サンプリングする（プレゼンモードは黒、通常表示は灰色など）
    border = np.concatenate([arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]])
    bg = np.median(border, axis=0)

    is_bg = np.abs(arr.astype(int) - bg.astype(int)).max(axis=2) <= BG_TOL

    # しきい値は0.995ではなく0.98。0.995だと「99.4%が背景」の細い区切り線を
    # content と誤判定してページ境界の検出が壊れる（実際にハマった）
    rows = is_bg.mean(axis=1) < 0.98
    i = 0
    while i < h:
        if not rows[i]:
            j = i
            while j < h and not rows[j]:
                j += 1
            if (j - i) < MIN_GAP_RUN and i > 0 and j < h:
                rows[i:j] = True  # ページ内部の細い余白でブロックが分断されるのを防ぐ
            i = j
        else:
            i += 1

    y0, y1 = largest_true_run(rows)
    if y1 - y0 < 50:
        y0, y1 = 0, h

    cols = is_bg[y0:y1, :].mean(axis=0) < 0.98
    x0, x1 = largest_true_run(cols)
    if x1 - x0 < 50:
        x0, x1 = 0, w

    box = (max(0, x0 - PAD), max(0, y0 - PAD), min(w, x1 + PAD), min(h, y1 + PAD))
    Image.open(path).convert("RGB").crop(box).save(out_path)
    return box[2] - box[0], box[3] - box[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    files = sorted(glob.glob(os.path.join(a.src, "page_*.png")))
    print(f"{len(files)} files")
    sizes = [(os.path.basename(f), process(f, os.path.join(a.out, os.path.basename(f))))
             for f in files]
    ws = [s[1][0] for s in sizes]
    hs = [s[1][1] for s in sizes]
    mw, mh = int(np.median(ws)), int(np.median(hs))
    print(f"median {mw}x{mh}  width {min(ws)}-{max(ws)}  height {min(hs)}-{max(hs)}")
    # サイズが飛び抜けているものは検出ミスの可能性が高いので必ず目視する
    for name, (sw, sh) in sizes:
        if abs(sw - mw) > mw * 0.15 or abs(sh - mh) > mh * 0.15:
            print(f"  OUTLIER: {name} -> {sw}x{sh}")
    print("done")


if __name__ == "__main__":
    main()
