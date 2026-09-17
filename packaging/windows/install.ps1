# Installs Claude Content Studio for the current Windows user - no admin rights needed.
# Run from the folder that contains this script alongside ClaudeContentStudio.exe and _internal\.
param(
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExeSource = Join-Path $ScriptDir "ClaudeContentStudio.exe"
if (-not (Test-Path $ExeSource)) {
    Write-Error "ClaudeContentStudio.exe not found next to install.ps1 - run this from the unzipped package folder."
    exit 1
}

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\ClaudeContentStudio"
Write-Host "Installing to $InstallDir ..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path (Join-Path $ScriptDir "*") -Destination $InstallDir -Recurse -Force -Exclude "install.ps1"

$TargetExe = Join-Path $InstallDir "ClaudeContentStudio.exe"

# --- Start Menu shortcut ---
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = Join-Path $StartMenuDir "Claude Content Studio.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetExe
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "Claude Content Studio"
$Shortcut.Save()

# --- Desktop shortcut (optional) ---
if (-not $NoDesktopShortcut) {
    $DesktopShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Claude Content Studio.lnk"
    $DesktopShortcut = $Shell.CreateShortcut($DesktopShortcutPath)
    $DesktopShortcut.TargetPath = $TargetExe
    $DesktopShortcut.WorkingDirectory = $InstallDir
    $DesktopShortcut.Description = "Claude Content Studio"
    $DesktopShortcut.Save()
}

# --- uninstall.ps1 (copied alongside the app so the registry entry can find it) ---
# (this file must stay ASCII-only: Windows PowerShell 5.1 parses .ps1 files without a BOM
# using the system ANSI codepage, and a stray non-ASCII byte can corrupt the whole script)
$UninstallScript = Join-Path $ScriptDir "uninstall.ps1"
Copy-Item -Path $UninstallScript -Destination (Join-Path $InstallDir "uninstall.ps1") -Force

# --- "Add or Remove Programs" entry (per-user, no admin required) ---
$UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ClaudeContentStudio"
New-Item -Path $UninstallKey -Force | Out-Null
$SizeKb = [math]::Round((Get-ChildItem $InstallDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1KB)
Set-ItemProperty -Path $UninstallKey -Name "DisplayName" -Value "Claude Content Studio"
Set-ItemProperty -Path $UninstallKey -Name "DisplayVersion" -Value "1.0.0"
Set-ItemProperty -Path $UninstallKey -Name "Publisher" -Value "Claude Content Studio"
Set-ItemProperty -Path $UninstallKey -Name "InstallLocation" -Value $InstallDir
Set-ItemProperty -Path $UninstallKey -Name "DisplayIcon" -Value $TargetExe
Set-ItemProperty -Path $UninstallKey -Name "UninstallString" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\uninstall.ps1`""
Set-ItemProperty -Path $UninstallKey -Name "EstimatedSize" -Value $SizeKb -Type DWord
Set-ItemProperty -Path $UninstallKey -Name "NoModify" -Value 1 -Type DWord
Set-ItemProperty -Path $UninstallKey -Name "NoRepair" -Value 1 -Type DWord

Write-Host ""
Write-Host "Installed. Launch from the Start Menu (Claude Content Studio), or run:"
Write-Host "  $TargetExe"
Write-Host "To uninstall later: Settings > Apps, or run $InstallDir\uninstall.ps1"
