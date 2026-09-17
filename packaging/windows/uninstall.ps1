# Removes Claude Content Studio: shortcuts, the Add/Remove Programs entry, and the install
# folder. User data (config, SQLite history, generated images/videos, API keys in Windows
# Credential Manager) is kept - same policy as the Ubuntu uninstaller.
# (this file must stay ASCII-only: Windows PowerShell 5.1 parses .ps1 files without a BOM
# using the system ANSI codepage, and a stray non-ASCII byte can corrupt the whole script)
$ErrorActionPreference = "SilentlyContinue"

$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Claude Content Studio.lnk"
Remove-Item -Path $StartMenuShortcut -Force

$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Claude Content Studio.lnk"
Remove-Item -Path $DesktopShortcut -Force

Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ClaudeContentStudio" -Force -Recurse

Write-Host "Removed shortcuts and the Add/Remove Programs entry."
Write-Host "Your settings, API keys, history and generated files were kept."
Write-Host "Deleting program files in a moment (this window can close)..."

# This script is running from inside $InstallDir, so it cannot delete that folder itself -
# hand off to a detached cmd that waits for this process to exit, then removes it.
Start-Process -WindowStyle Hidden cmd.exe -ArgumentList "/c timeout /t 2 >nul & rmdir /s /q `"$InstallDir`""
