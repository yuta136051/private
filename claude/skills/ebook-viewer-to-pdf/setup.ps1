<#
撮影前の準備とスクリーンショット確認。

例:
  powershell -File setup.ps1 -Shot                      # 今の画面を撮って確認
  powershell -File setup.ps1 -GoToPage 1 -Present -Shot # 1ページ目へ移動してプレゼンモードへ
  powershell -File setup.ps1 -Keys "{ESC}" -Release     # プレゼン解除+最前面固定の解除（後片付け）

-GoToPage は PDF.js のツールバーのページ番号欄をクリックして入力する。
座標(-PageBoxX/-PageBoxY)は -Shot で撮った画像から実測して渡すこと（毎回同じとは限らない）。
#>
param(
    [int]$GoToPage = 0,
    [int]$PageBoxX = 268,
    [int]$PageBoxY = 206,
    [int]$ViewerX = 300,
    [int]$ViewerY = 600,
    [switch]$Present,
    [switch]$Shot,
    [switch]$Release,
    [string]$Keys = "",
    [string]$Out = "$env:TEMP\ebook_shot.png"
)

. "$PSScriptRoot\lib.ps1"

Set-ChromeTopmost -On $true
Write-Output "Foreground: $(Focus-Chrome)"

if ($GoToPage -gt 0) {
    Click-At -X $PageBoxX -Y $PageBoxY
    Send-Keys -Keys @("^a", "$GoToPage", "{ENTER}")
    Start-Sleep -Milliseconds 1500
}

if ($Keys -ne "") { Send-Keys -Keys $Keys.Split("|") }

if ($Present) { Enter-PresentationMode -ClickX $ViewerX -ClickY $ViewerY }

if ($Shot) {
    Start-Sleep -Milliseconds 500
    Save-Screenshot -Path $Out
    Write-Output "Saved $Out"
}

if ($Release) {
    Set-ChromeTopmost -On $false
    Write-Output "Chrome topmost released"
}
