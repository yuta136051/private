# 電子書籍ビューワー撮影用の共通ヘルパー
# 使い方: . "$PSScriptRoot\lib.ps1"

# --- DPI対応（これを最初にやらないと画面が縮小解像度になり画質が落ちる） ---
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DpiHelper {
    [DllImport("user32.dll")]
    public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    public static readonly IntPtr PER_MONITOR_AWARE_V2 = new IntPtr(-4);
}
"@
[DpiHelper]::SetProcessDpiAwarenessContext([DpiHelper]::PER_MONITOR_AWARE_V2) | Out-Null

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinCtl {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int c);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();

    public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
    public static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
    public const uint SWP_NOMOVE = 0x0002, SWP_NOSIZE = 0x0001, SWP_SHOWWINDOW = 0x0040;
    public const uint LEFTDOWN = 0x0002, LEFTUP = 0x0004;

    public static string TitleOf(IntPtr h) {
        StringBuilder sb = new StringBuilder(256);
        GetWindowText(h, sb, 256);
        return sb.ToString();
    }

    // 通常 SetForegroundWindow はバックグラウンドプロセスからは効かない。
    // AttachThreadInput でフォアグラウンドスレッドに紐付けてから呼ぶと確実に前面化できる。
    public static bool ForceForeground(IntPtr h) {
        if (IsIconic(h)) ShowWindow(h, 9);
        uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
        uint me = GetCurrentThreadId();
        uint tg = GetWindowThreadProcessId(h, IntPtr.Zero);
        AttachThreadInput(me, fg, true);
        AttachThreadInput(me, tg, true);
        BringWindowToTop(h);
        bool ok = SetForegroundWindow(h);
        AttachThreadInput(me, tg, false);
        AttachThreadInput(me, fg, false);
        return ok;
    }
}
"@

function Get-ChromeWindow {
    $p = Get-Process chrome -ErrorAction SilentlyContinue |
         Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -First 1
    if (-not $p) { throw "Chrome window not found" }
    return $p.MainWindowHandle
}

# Claude Code などのウィンドウが常に最前面のことがあるので、撮影中は Chrome を最前面に固定する。
# 終わったら必ず Set-ChromeTopmost -On $false で解除する。
function Set-ChromeTopmost {
    param([bool]$On = $true)
    $h = Get-ChromeWindow
    $after = if ($On) { [WinCtl]::HWND_TOPMOST } else { [WinCtl]::HWND_NOTOPMOST }
    [WinCtl]::SetWindowPos($h, $after, 0, 0, 0, 0,
        ([WinCtl]::SWP_NOMOVE -bor [WinCtl]::SWP_NOSIZE -bor [WinCtl]::SWP_SHOWWINDOW)) | Out-Null
    Start-Sleep -Milliseconds 300
}

function Focus-Chrome {
    [WinCtl]::ForceForeground((Get-ChromeWindow)) | Out-Null
    Start-Sleep -Milliseconds 600
    return [WinCtl]::TitleOf([WinCtl]::GetForegroundWindow())
}

function Send-Keys {
    param([string[]]$Keys, [int]$GapMs = 400)
    foreach ($k in $Keys) {
        [System.Windows.Forms.SendKeys]::SendWait($k)
        Start-Sleep -Milliseconds $GapMs
    }
}

function Click-At {
    param([int]$X, [int]$Y)
    [WinCtl]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 200
    [WinCtl]::mouse_event([WinCtl]::LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [WinCtl]::mouse_event([WinCtl]::LEFTUP, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 300
}

function Get-ScreenBounds { [System.Windows.Forms.Screen]::PrimaryScreen.Bounds }

function Save-Screenshot {
    param([string]$Path, [System.Drawing.Rectangle]$Crop)
    $b = Get-ScreenBounds
    $full = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($full)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $g.Dispose()
    if ($Crop -and $Crop.Width -gt 0) {
        $bmp = $full.Clone($Crop, $full.PixelFormat)
        $full.Dispose()
    } else { $bmp = $full }
    $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

# プレゼンテーションモードに入る（PDF.js系ビューワー: ビュー内をクリックしてから Ctrl+Alt+P）
function Enter-PresentationMode {
    param([int]$ClickX = 300, [int]$ClickY = 600, [int]$WaitMs = 3000)
    Set-ChromeTopmost -On $true
    Focus-Chrome | Out-Null
    Click-At -X $ClickX -Y $ClickY
    Send-Keys -Keys @("^%p")
    Start-Sleep -Milliseconds $WaitMs
}
