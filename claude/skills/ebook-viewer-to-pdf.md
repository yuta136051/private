---
name: ebook-viewer-to-pdf
description: Google Chromeで開いている電子書籍/PDFビューワー（PDF書き出し・印刷・右クリック保存ができないがスクリーンショットは可能なタイプ、いわゆるDRM的な閲覧専用ビューワー）を自動でスクリーンショットし、1ページずつきれいに切り出して1つのPDFファイルに結合する。「電子書籍をPDF化したい」「スクリーンショットで本を保存したい」「このビューワー、PDFにできないんだけど」のような相談が来たら、このスキルの手順をそのまま使う。過去に同じ試行錯誤（DPI問題、ページ間の映り込み、中央寄せズレなど）を解決済みなので、ゼロから考え直さずこのスキルの手順通りに進めること。
trigger: /ebook-to-pdf
---

# 電子書籍ビューワー → PDF化 自動化スキル

Chrome上の「スクリーンショットはできるがPDF書き出し・印刷ができない」電子書籍/文書ビューワーを、OSレベルのキー操作とスクリーンショットで全自動撮影し、画像処理で1ページずつきれいに切り出してPDFに結合する。過去のセッションで何度も同じ落とし穴にはまって修正した経緯があるので、以下の手順・注意点を守れば初回から高品質な結果になる。

## 全体方針

1ページごとにClaudeがツール呼び出しでスクリーンショット→次ページ、を繰り返すのは低速・高コストなので**絶対にやらない**。PowerShellスクリプト1本がループ全体（スクリーンショット→比較→保存→次ページキー送信→待機）を内部で完結させ、Claudeはセットアップ・キャリブレーション・検証だけを担当する。

## Step 0: 事前確認

- 対象のビューワーがどのChromeタブで開いているか確認する（`Get-Process chrome` はアクティブなタブのタイトルしか分からないので、後述のフォーカス確認を徹底する）。
- ページ送りの操作方法（多くの場合キーボードの→キー、まれにクリックやスクロール）。
- 依存パッケージの確認・インストール:
  ```
  pip install img2pdf Pillow numpy pypdf --quiet
  ```

## Step 1: DPI対応のセットアップ（最重要・絶対に飛ばさない）

Windowsで表示スケーリング（125%/150%など）が有効な場合、非DPI対応のPowerShellプロセスは画面を**縮小された解像度**（例: 物理1920x1200なのに1280x800）としてしか認識せず、`CopyFromScreen`で撮ったスクリーンショットがエラーも出ずに低画質になる。これは一度やらかして気づきにくいバグなので、**スクリーンショットや座標操作をする全スクリプトの先頭で必ず**以下を実行する。

`dpi_aware.ps1` として保存し、他のスクリプトから `. "パス\dpi_aware.ps1"` でドットソースする:

```powershell
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DpiHelper {
    [DllImport("user32.dll")]
    public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    public static readonly IntPtr DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = new IntPtr(-4);
}
"@
[DpiHelper]::SetProcessDpiAwarenessContext([DpiHelper]::DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) | Out-Null
```

真の解像度になっているか必ず確認する:
```powershell
Get-CimInstance Win32_VideoController | Select-Object CurrentHorizontalResolution, CurrentVerticalResolution
# DPI対応後のスクリプト内で:
[System.Windows.Forms.Screen]::PrimaryScreen.Bounds  # ↑と一致するはず
```
一致しなければ、DPI対応が効いていない＝低画質になる。

## Step 2: 対象タブへのフォーカスとF11全画面化

複数タブがある場合、`Get-Process chrome | Where MainWindowTitle -ne ''` は**現在アクティブなタブ**のタイトルしか返さない。ユーザーが後から別タブ（生成したPDFを確認する等）を開くと、次の操作が意図しないタブに送られる。**毎回、キー送信の直前にスクリーンショットでタブバーとURLを目視確認し**、違うタブがアクティブなら該当タブをクリックして戻す。

フォーカス確認スクリプト（`focus_chrome_only.ps1`）:
```powershell
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32b {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
}
"@
$proc = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -First 1
if (-not $proc) { Write-Output "ERROR: Chrome window not found"; exit 1 }
[Win32b]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500
$fg = [Win32b]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[Win32b]::GetWindowText($fg, $sb, 256) | Out-Null
Write-Output "Foreground window now: $($sb.ToString())"
```

**マウスクリックする前は必ずこれでフォーカス済みか確認してから**行う。フォーカスを確認せずに座標クリックすると、全く別のアプリ（Claudeの画面自体など）を誤操作する事故が起きる（実際に起きた）。

その後 `F11` を送ってフルスクリーン化（タブバー・アドレスバー・ブックマークバーを消す）。**F11は新しいタブが開く等で勝手に解除されることがある**ので、本撮影の直前には毎回スクリーンショットでフルスクリーン状態を再確認する。

## Step 3: ズームとクロップ範囲のキャリブレーション（毎回サイト固有・使い回し禁止）

1. ビューワー自体のズーム+/-ボタンは当たり判定が小さく、クリックが当たらないことが多い。**キーボードショートカットを優先する**: `Ctrl+-` / `Ctrl+0` / Ctrl+Plusを送る場合は SendKeysで `^{+}` と書く（`^=` だとCtrl+Plus扱いにならない）。多くのビューワーはこれを**ブラウザのページズームではなく自前のズーム**として横取りするので、画面上のズーム%表示を見てどちらが反応しているか確認する。
2. ちょうど良いズーム%を探す: 1ページの縦幅が画面に収まりきる（下が見切れない）が、小さくなりすぎて文字が潰れない値。フルスクリーン+高DPI補正後なら、多くの場合70%前後で収まる（が、これは前回の値であり**毎回実測すること**、使い回さない）。
3. ページのコンテナが画面中央にあるとは限らない（見開き表示の片方のスロットだけ描画されて右寄り/左寄りになっている等）。ズームを変えても中央寄せのオフセットは単純にスケールしないことがあるので、**採用したズームで実測**してcrop範囲を決める。
4. → キーでページ送りが1ページずつ正確に進むか、ページ番号表示（例:「12 / 165」）で確認する。
5. `Home`キーで先頭ページに戻れることが多い（本番実行前のリセットに使う）。

**キャリブレーションの鉄則**: いきなり全ページ撮らない。まず5〜6ページだけ試し撮りして目視確認 → 良ければ本番実行、に必ずする。

## Step 4: 本撮影（1本のスクリプトで完結させる）

`capture_pages.ps1`（テンプレート。`$CropRect` はStep3で実測した値に毎回差し替える。crop範囲は**キツすぎず、現在ページ全体+隣ページの端が少し映り込むくらい余裕を持たせる**——正確な切り出しはStep5の後処理でやるので、ここでは「絶対に本文を欠かさない」ことを優先する):

```powershell
param(
    [int]$MaxPages = 300,
    [int]$DelayMs = 800,
    [int]$DupThreshold = 2,
    [string]$OutDir = "..."
)

. "パス\dpi_aware.ps1"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32c {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Get-ChildItem -Path $OutDir -Filter "page_*.png" -ErrorAction SilentlyContinue | Remove-Item -Force

$proc = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -First 1
if (-not $proc) { Write-Output "ERROR: Chrome window not found"; exit 1 }
[Win32c]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 500

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$md5 = [System.Security.Cryptography.MD5]::Create()
$prevHash = $null
$dupCount = 0
$saved = 0

# ↓ Step3で実測した値に差し替える (x, y, width, height)
$CropRect = New-Object System.Drawing.Rectangle 0, 0, $bounds.Width, $bounds.Height

function Get-ScreenHash {
    param($bounds, $md5, $cropRect)
    $full = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $g = [System.Drawing.Graphics]::FromImage($full)
    $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $g.Dispose()
    $bmp = $full.Clone($cropRect, $full.PixelFormat)
    $full.Dispose()
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $ms.ToArray()
    $ms.Dispose()
    $hash = [System.BitConverter]::ToString($md5.ComputeHash($bytes))
    return @{ Bmp = $bmp; Bytes = $bytes; Hash = $hash }
}

for ($i = 1; $i -le $MaxPages; $i++) {
    $cap = Get-ScreenHash -bounds $bounds -md5 $md5 -cropRect $CropRect
    if ($cap.Hash -eq $prevHash) {
        $dupCount++
        $cap.Bmp.Dispose()
        Write-Output "[$i] duplicate detected (count=$dupCount)"
        if ($dupCount -ge $DupThreshold) {
            Write-Output "Reached end of book. Total saved pages: $saved"
            break
        }
    } else {
        $dupCount = 0
        $saved++
        $fname = Join-Path $OutDir ("page_{0:D4}.png" -f $saved)
        [System.IO.File]::WriteAllBytes($fname, $cap.Bytes)
        $cap.Bmp.Dispose()
        Write-Output "[$i] saved $fname"
        $prevHash = $cap.Hash
    }
    [System.Windows.Forms.SendKeys]::SendWait("{RIGHT}")
    Start-Sleep -Milliseconds $DelayMs
}
Write-Output "DONE. Saved $saved pages to $OutDir"
```

**重要**: これは `run_in_background: true` で1回だけ実行し、完了通知が来るまで待つ。実行中はユーザーにもマウス/キーボード操作をしないよう伝える（フォーカスがChromeから外れると矢印キーが届かない）。ページ数が分かっていればそれ+バッファを`MaxPages`に、分からなければ大きめ（200〜500）にして重複検出に任せる。

## Step 5: 自動トリミング（次ページの映り込み・見切れ・中央ズレを解消する要）

**ここが一番のポイント**: 固定ピクセルでの切り出しは「ページごとの微妙な位置ズレ」を吸収できず、狭すぎれば本文が切れ、広すぎれば次ページの端が映り込む（両方ともユーザーから指摘されやすい）。**Step4では余裕を持って広めに撮り、この後処理で画像ごとに実際のページ境界を自動検出して正確にトリミングする。**

`trim_pages.py`:
```python
import glob, os
import numpy as np
from PIL import Image

SRC_DIR = "..."   # Step4のOutDir
OUT_DIR = "..."   # トリム後の出力先
PAD = 14
BG_TOL = 18
MIN_GAP_RUN = 8

os.makedirs(OUT_DIR, exist_ok=True)

def largest_true_run(mask):
    best_start, best_len = 0, 0
    cur_start, cur_len = None, 0
    for i, v in enumerate(mask):
        if v:
            if cur_start is None:
                cur_start = i; cur_len = 1
            else:
                cur_len += 1
            if cur_len > best_len:
                best_len = cur_len; best_start = cur_start
        else:
            cur_start = None; cur_len = 0
    return best_start, best_start + best_len

def process(path, out_path):
    img = Image.open(path).convert("RGB")
    arr = np.array(img)
    h, w, _ = arr.shape

    # 背景色は画像の縁のピクセルから毎回サンプリングする（アプリ・テーマによって違うのでハードコードしない）
    border_pixels = np.concatenate([arr[0,:,:], arr[-1,:,:], arr[:,0,:], arr[:,-1,:]])
    bg = np.median(border_pixels, axis=0)

    diff = np.abs(arr.astype(int) - bg.astype(int)).max(axis=2)
    is_bg_pixel = diff <= BG_TOL

    row_bg_frac = is_bg_pixel.mean(axis=1)
    # しきい値は0.995ではなく0.98にする。0.995だと「99.4%背景」な行(細い区切り線など)を
    # 誤ってcontent判定してしまい、ページ境界の検出が壊れる(実際にハマったバグ)
    row_is_content = row_bg_frac < 0.98

    content_rows = row_is_content.copy()
    i = 0
    while i < h:
        if not content_rows[i]:
            j = i
            while j < h and not content_rows[j]:
                j += 1
            if (j - i) < MIN_GAP_RUN and i > 0 and j < h:
                content_rows[i:j] = True  # ページ内部の細い区切り線でブロックが分断されるのを防ぐ
            i = j
        else:
            i += 1

    y0, y1 = largest_true_run(content_rows)  # 最大の連続ブロック=現在のページ本体
    if y1 - y0 < 50:
        y0, y1 = 0, h

    col_bg_frac = is_bg_pixel[y0:y1, :].mean(axis=0)
    col_is_content = col_bg_frac < 0.98
    x0, x1 = largest_true_run(col_is_content)
    if x1 - x0 < 50:
        x0, x1 = 0, w

    y0p, y1p = max(0, y0 - PAD), min(h, y1 + PAD)
    x0p, x1p = max(0, x0 - PAD), min(w, x1 + PAD)
    Image.open(path).convert("RGB").crop((x0p, y0p, x1p, y1p)).save(out_path)

files = sorted(glob.glob(os.path.join(SRC_DIR, "page_*.png")))
print(f"{len(files)} files")
for f in files:
    process(f, os.path.join(OUT_DIR, os.path.basename(f)))
print("done")
```

## Step 6: PDF結合と検証

```python
import glob, img2pdf
files = sorted(glob.glob(r"トリム後フォルダ\page_*.png"))
with open(r"出力先.pdf", "wb") as f:
    f.write(img2pdf.convert(files))
```

検証:
```python
from pypdf import PdfReader
r = PdfReader(r"出力先.pdf")
print(len(r.pages))  # 撮影枚数と一致するか
```
そして**必ず**先頭・中間・終盤の複数ページをReadツールで開いて目視確認する（表紙のような特殊レイアウトのページ、最終ページ付近のオフバイワン、見切れ・映り込みが残っていないか）。「できました」で終わらせず、実際に画像を見て確認してから報告する。

## Step 7（オプション）: OCRでテキスト検索対応にする

Step6までで作るPDFは**画像のみでテキスト検索はできない**。検索可能にするには追加でOCR処理が必要。ユーザーが要望した場合のみ実施する（外部ソフトのインストールを伴うため、着手前に一言伝えてから進める）。完了時は「見た目は元のまま・裏にテキスト層を追加した」ことと、精度の限界を必ず伝える。

### Tesseract OCR + ocrmypdf を試す前に: 管理者権限の壁に注意

素直に考えると Tesseract OCR + `ocrmypdf` が定番（画像PDFに不可視テキスト層を追加する専用ツールで、無地の画像はそのまま・裏にテキストだけ足せる)。だが**Windows版Tesseractの公式インストーラーはUAC昇格を要求し**、管理者権限を対話的に承認できない自動化シェルからは `winget install` も、ダウンロード済みexeを直接 `/S /D=<user-writable-dir>` で叩いても **`The operation was canceled by the user` で失敗する**（実際に両方試して両方失敗した）。加えてWindowsのwingetコミュニティリポジトリには公式Ghostscript（ocrmypdfの必須依存）が見当たらないことが多い。管理者権限を対話的に得られる状況（ユーザーに直接インストールしてもらう等）でなければ、この経路は早々に見切りをつけて次に進んだほうが速い。

### 実際に機能した経路: EasyOCR（Pure Python）+ reportlabで自前合成

`pip install` だけで完結し管理者権限が不要。精度はTesseractに劣るが、**検索用途には十分**実用的。

```
pip install easyocr reportlab
```

コンソールが日本語コードページ(cp932)だと、EasyOCRのモデルダウンロード進捗バー（`█`などのUnicode文字）出力で `UnicodeEncodeError` が起きて丸ごとクラッシュする（実際に発生）。**必ず** `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` を付けて実行する。クラッシュ後に再実行する場合は `~/.EasyOCR/model/temp.zip` の壊れた途中ファイルを消してからやり直す。

`make_ocr_pdf.py`（トリム済み画像フォルダを読み、画像はそのまま貼り付け、その上に検出したテキストボックスぶんだけ不可視テキストを重ねる）:
```python
import glob, os, sys
import easyocr
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

SRC_DIR = "..."  # Step5のトリム後フォルダ
FONT_NAME = "HeiseiMin-W3"  # reportlab内蔵のCID日本語フォント。外部フォントファイル不要
pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

def build_pdf(out_path, limit=None):
    reader = easyocr.Reader(["ja", "en"], gpu=False)
    files = sorted(glob.glob(os.path.join(SRC_DIR, "page_*.png")))
    if limit:
        files = files[:limit]
    c = canvas.Canvas(out_path)
    for idx, f in enumerate(files, 1):
        img = Image.open(f).convert("RGB")
        w, h = img.size
        c.setPageSize((w, h))
        c.drawImage(ImageReader(img), 0, 0, width=w, height=h)  # 元画像をそのまま貼る

        results = reader.readtext(f)
        c.setFillColorRGB(0, 0, 0)
        for bbox, text, conf in results:
            text = text.strip()
            if not text:
                continue
            xs = [p[0] for p in bbox]; ys = [p[1] for p in bbox]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            box_h, box_w = max(1, y1 - y0), max(1, x1 - x0)
            font_size = max(4, box_h * 0.9)
            pdf_x, pdf_y = x0, h - y1 + box_h * 0.1  # PIL座標(左上原点)→PDF座標(左下原点)変換

            text_width = c.stringWidth(text, FONT_NAME, font_size)
            to = c.beginText()
            to.setTextRenderMode(3)  # 3=不可視。Canvas自体にはsetTextRenderModeが無いのでbeginText()経由で呼ぶ
            to.setFont(FONT_NAME, font_size)
            to.setTextOrigin(pdf_x, pdf_y)
            if text_width > 0:
                to.setHorizScale(100.0 * box_w / text_width)  # 検出ボックス幅に文字列をフィットさせる
            to.textOut(text)
            c.drawText(to)
        c.showPage()
    c.save()

if __name__ == "__main__":
    build_pdf(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
```

実行例（まず数ページで試す→良ければ全ページを`run_in_background`で）:
```
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python make_ocr_pdf.py test.pdf 3   # まず試す
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python make_ocr_pdf.py out.pdf     # 本番(バックグラウンド)
```

**所要時間の目安**: CPUのみ（GPUなし）だと165ページで約35〜45分かかった。実行前にユーザーへ「CPUのみのOCRなのでそれなりに時間がかかる」旨を伝えておく。また `print()` の出力はファイルにリダイレクトすると**バッファリングされて進捗が見えない**（プロセスは動いているのに`[N/165]`のログが全く増えないように見える）。進捗を聞かれたら `Get-Process python` のCPU時間・経過時間から生存確認する（止まっていないことは分かるが、正確な残りページ数までは分からない、と正直に伝える）。

**検証**: `pypdf`で`extract_text()`し、**必ずUTF-8ファイルに書き出してからReadツールで読む**（Bashツールの標準出力はコンソールの文字コード変換を経由するため、実際には正しく抽出できていても文字化けして見え、誤って「壊れている」と判断しがちなので注意）。キーワードが本文中でヒットするか（`"生成" in text`など）で検索可能性を確認する。装飾ロゴ・タイトルの凝ったフォント部分はOCR精度が落ちやすい（本文中の同じ単語は拾えているか、で判断するとよい）。

**精度についての注意**: EasyOCR(CPU)は完璧ではなく、文中に誤字（類似文字への誤認識）が一定量出る。見た目（画像）は無劣化のまま、検索用途には十分だが、**テキストをコピーしてそのまま文章として使うのには向かない**、とユーザーに伝えること。

## よくある落とし穴まとめ（再発防止チェックリスト）

- [ ] DPI対応を全スクリプトの先頭でやったか（真の解像度になっているか確認したか）
- [ ] キー送信・クリック直前に対象タブがアクティブか毎回確認したか
- [ ] F11が本撮影直前も維持されているか確認したか
- [ ] ズーム・crop範囲は今回のサイト/解像度で実測したか（前回の数値を使い回していないか）
- [ ] 5〜6ページの試し撮りで目視確認してから本番に進んだか
- [ ] 本撮影は1本のバックグラウンドスクリプトで完結させたか（1ページずつClaudeが操作していないか）
- [ ] トリミング後処理をかけたか（固定cropのまま結合していないか）
- [ ] 先頭・中間・終盤を目視確認したか
- [ ] 画像のみPDFであること（OCR未対応であること）をユーザーに伝えたか
- [ ] OCRを頼まれたら、いきなりTesseractのインストーラーに時間をかけず（管理者権限で失敗しがち）、先にEasyOCR+reportlab経路を検討したか
- [ ] OCR結果のテキスト確認はUTF-8ファイル経由で行い、コンソールの文字化けと実際の抽出失敗を混同していないか
