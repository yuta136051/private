"""縦書きページから「列」と「1文字ごとの位置」を検出する。

縦書き日本語はOCRエンジンがそのままでは読めない。列単位に切り出し、さらに
文字の切れ目で数文字ずつに分割してから認識器に渡すことで実用精度になる。
"""
import numpy as np
from PIL import Image

DARK = 160           # これより暗ければ文字
EDGE_PAD = 16        # trim.py が付けた黒枠を除外する
TOP_MARGIN = 0.015   # 上下の余白（ページ番号・柱）を除外する割合
BOT_MARGIN = 0.055
COL_THR = 4          # 1列あたりの暗ピクセル数のしきい値
MIN_W = 12           # これ未満は振り仮名・ノイズとして捨てる
MAX_W = 40           # これを超えたら複数列がくっついているとみなして等分割
MIN_H = 40
ROW_GAP = 25         # 文字と文字の隙間はこの値まで同じ列として繋ぐ
CHAR_GAP = 2         # 文字の切れ目判定。文字間は3px以上空くので2px以下だけ繋ぐ


def _runs(mask, gap=0):
    runs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        if not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    if gap <= 0 or not runs:
        return runs
    merged = [list(runs[0])]
    for s, e in runs[1:]:
        if s - merged[-1][1] <= gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [tuple(m) for m in merged]


def detect_columns(path):
    """縦書きの読み順（右→左）で [(x0, y0, x1, y1), ...] を返す"""
    a = np.array(Image.open(path).convert("L"))
    h, w = a.shape
    y_lo, y_hi = int(h * TOP_MARGIN), int(h * (1 - BOT_MARGIN))
    x_lo, x_hi = EDGE_PAD, w - EDGE_PAD
    dark = a[y_lo:y_hi, x_lo:x_hi] < DARK

    col_runs = [r for r in _runs(dark.sum(axis=0) > COL_THR) if (r[1] - r[0]) >= MIN_W]
    if not col_runs:
        return []
    widths = [r[1] - r[0] for r in col_runs if (r[1] - r[0]) <= MAX_W]
    pitch = int(np.median(widths)) if widths else 21

    split = []
    for x0, x1 in col_runs:
        if (x1 - x0) > MAX_W:
            n = max(2, int(round((x1 - x0) / pitch)))
            step = (x1 - x0) / n
            split += [(int(x0 + k * step), int(x0 + (k + 1) * step)) for k in range(n)]
        else:
            split.append((x0, x1))

    boxes = []
    for x0, x1 in split:
        rows = dark[:, x0:x1].sum(axis=1) > 0
        for y0, y1 in _runs(rows, gap=ROW_GAP):
            if (y1 - y0) >= MIN_H:
                boxes.append((x0 + x_lo, y0 + y_lo, x1 + x_lo, y1 + y_lo))

    boxes.sort(key=lambda b: (-b[0], b[1]))
    return boxes


def char_runs(path, box):
    """列の中の1文字ごとの縦位置 [(y0, y1), ...]。チャンクを文字の切れ目で切るために使う。"""
    a = np.array(Image.open(path).convert("L"))
    x0, y0, x1, y1 = box
    rows = (a[y0:y1, x0:x1] < DARK).sum(axis=1) > 0
    return [(y0 + s, y0 + e) for s, e in _runs(rows, gap=CHAR_GAP)]


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        bs = detect_columns(p)
        print(f"{p}: {len(bs)} columns widths={[b[2] - b[0] for b in bs]}")
