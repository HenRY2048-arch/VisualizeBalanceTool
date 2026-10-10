# Create desktop shortcut for VisualizeBalance
$ExePath = Join-Path $PSScriptRoot "..\dist\VisualizeBalance.exe"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "VisualizeBalance.lnk"

if (-not (Test-Path $ExePath)) {
    Write-Host "Not found: $ExePath - please build first"
    exit 1
}

$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = (Resolve-Path $ExePath).Path
$Shortcut.WorkingDirectory = (Split-Path (Resolve-Path $ExePath).Path)
$Shortcut.Description = "DeepSeek API Balance Monitor"
$Shortcut.IconLocation = "$($Shortcut.TargetPath),0"
$Shortcut.Save()

Write-Host "Done: $ShortcutPath"
