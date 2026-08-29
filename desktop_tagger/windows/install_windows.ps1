# 安裝「中文人名標示」到這台 Windows 電腦：
#   1. 把打包好的 ChineseNameTagger（含 Python/torch/模型）複製到
#      %LOCALAPPDATA%\ChineseNameTagger\
#   2. 在「啟動」資料夾建立捷徑，開機登入時自動執行（系統匣常駐）
#   3. 立刻啟動一次
#
# 用法：在這個資料夾（解壓縮後的 ChineseNameTaggerWindows 資料夾）用
# PowerShell 執行：
#   powershell -ExecutionPolicy Bypass -File install_windows.ps1

$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Join-Path $Here "ChineseNameTagger"
$InstallDir = Join-Path $env:LOCALAPPDATA "ChineseNameTagger"
$ExePath = Join-Path $InstallDir "ChineseNameTagger.exe"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "ChineseNameTagger.lnk"

if (-not (Test-Path $SourceDir)) {
    Write-Error "找不到 $SourceDir，請確認這個腳本跟 ChineseNameTagger 資料夾放在一起（GitHub Actions 產出的 zip 解壓縮後的樣子）。"
    exit 1
}

Write-Host "==> 停止舊的服務（如果有在跑）"
Get-Process -Name "ChineseNameTagger" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "==> 安裝程式到 $InstallDir"
if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}
Copy-Item -Recurse -Force $SourceDir $InstallDir

Write-Host "==> 設定開機登入自動啟動（在「啟動」資料夾建立捷徑）"
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "中文人名標示 - 系統匣常駐工具"
$Shortcut.Save()

Write-Host "==> 立刻啟動一次"
Start-Process -FilePath $ExePath -WorkingDirectory $InstallDir

Write-Host ""
Write-Host "安裝完成。工作列右下角（系統匣）會出現一個圖示（橘色＝啟動中、綠色＝就緒）。"
Write-Host "使用方式：在任何程式（記事本、Word、瀏覽器…）選取一段中文文字，按 Ctrl+Alt+N，"
Write-Host "會跳出一個訊息框顯示標出的人名。第一次啟動如果模型還在載入，最多可能要等 30-40 秒。"
Write-Host ""
Write-Host "注意：如果按 Ctrl+Alt+N 沒有反應，可能是快捷鍵套件需要系統管理員權限才能監聽"
Write-Host "全域按鍵——請試著以「系統管理員身分執行」ChineseNameTagger.exe 看看。"
