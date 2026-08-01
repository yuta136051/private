<#
プレゼンテーションモードのビューワーを1画面=1ページで全ページ撮影する。

例:
  powershell -File capture.ps1 -Pages 168 -OutDir C:\tmp\capture
  powershell -File capture.ps1 -StartIndex 54 -EndIndex 168 -OutDir C:\tmp\capture   # 途中から再開

前提: 対象タブがプレゼンテーションモード(Ctrl+Alt+P)で表示済みで、先頭ページにいること。
     setup.ps1 -GoToPage 1 -Present で用意できる。
#>
param(
    [int]$Pages = 0,
    [int]$StartIndex = 1,
    [int]$EndIndex = 0,
    [int]$DelayMs = 700,
    [int]$StartDelayMs = 4000,
    [int]$CropX = -1,
    [int]$CropY = 0,
    [int]$CropW = -1,
    [int]$CropH = -1,
    [Parameter(Mandatory = $true)][string]$OutDir
)

. "$PSScriptRoot\lib.ps1"

if ($EndIndex -le 0) { $EndIndex = if ($Pages -gt 0) { $Pages } else { 999 } }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Set-ChromeTopmost -On $true
Write-Output "Foreground: $(Focus-Chrome)"
Write-Output "Waiting $StartDelayMs ms (Chromeの「Escで全画面終了」通知が消えるのを待つ)"
Start-Sleep -Milliseconds $StartDelayMs

$b = Get-ScreenBounds
# 既定は画面中央60%を切り出す。黒帯を少し含めておき、正確な切り出しは trim.py に任せる。
if ($CropW -le 0) { $CropW = [int]($b.Width * 0.6) }
if ($CropH -le 0) { $CropH = $b.Height }
if ($CropX -lt 0) { $CropX = [int](($b.Width - $CropW) / 2) }
$rect = New-Object System.Drawing.Rectangle $CropX, $CropY, $CropW, $CropH
Write-Output "Screen $($b.Width)x$($b.Height)  Crop $CropX,$CropY $CropW x $CropH"

$md5 = [System.Security.Cryptography.MD5]::Create()

function Get-Frame {
    $full = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($full)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $g.Dispose()
    $bmp = $full.Clone($rect, $full.PixelFormat)
    $full.Dispose()
    # 左下すみの明るさ: プレゼンモードなら黒帯なので暗い。明るければ全画面が解除されている。
    $sum = 0; $n = 0
    for ($x = 5; $x -lt 45; $x += 5) {
        for ($y = $bmp.Height - 45; $y -lt $bmp.Height - 5; $y += 5) {
            $p = $bmp.GetPixel($x, $y); $sum += ($p.R + $p.G + $p.B) / 3; $n++
        }
    }
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $ms.ToArray()
    $ms.Dispose(); $bmp.Dispose()
    return @{ Bytes = $bytes; Hash = [System.BitConverter]::ToString($md5.ComputeHash($bytes)); Corner = $sum / $n }
}

$prevHash = $null
$dups = @()
$recoveries = 0
$saved = 0

for ($i = $StartIndex; $i -le $EndIndex; $i++) {
    $cap = Get-Frame

    # 全画面が外れたら自動復帰（放置すると残り全部が同じ画面になる。実際にやらかした）
    $try = 0
    while ($cap.Corner -gt 25 -and $try -lt 3) {
        $try++; $recoveries++
        Write-Output "[$i] presentation mode lost (corner=$([math]::Round($cap.Corner,1))) - recovering $try"
        Enter-PresentationMode
        $cap = Get-Frame
    }
    if ($cap.Corner -gt 25) {
        Write-Output "ABORT at $i : could not restore presentation mode. 再開は -StartIndex $i で。"
        break
    }

    # 描画途中を掴んだだけの可能性があるので、同じ画面なら少し待って撮り直す
    $retry = 0
    while ($cap.Hash -eq $prevHash -and $retry -lt 3) {
        $retry++
        Start-Sleep -Milliseconds 600
        $cap = Get-Frame
    }
    if ($cap.Hash -eq $prevHash) { $dups += $i }

    [System.IO.File]::WriteAllBytes((Join-Path $OutDir ("page_{0:D4}.png" -f $i)), $cap.Bytes)
    $prevHash = $cap.Hash
    $saved++
    if ($i % 20 -eq 0) { Write-Output "[$i/$EndIndex] saved" }

    if ($i -lt $EndIndex) {
        Send-Keys -Keys @("{RIGHT}") -GapMs 0
        Start-Sleep -Milliseconds $DelayMs
    }
}

if ($dups.Count -gt 0) { Write-Output "WARNING: 直前と同一の画面: $($dups -join ',') （白紙ページなら正常）" }
Write-Output "recoveries=$recoveries  saved=$saved"
Write-Output "DONE $StartIndex..$EndIndex -> $OutDir"
