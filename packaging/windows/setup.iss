; Inno Setup script: builds a real Setup.exe wizard for Claude Content Studio.
; Requires the PyInstaller bundle at dist\ClaudeContentStudio (run tools\package_windows.py
; or `pyinstaller --windowed --name ClaudeContentStudio run.py` first).
; Compile: "C:\...\Inno Setup 6\ISCC.exe" packaging\windows\setup.iss
; (tools\package_windows_installer.py runs this step automatically.)

#define MyAppName "Claude Content Studio"
#define MyAppVersion "1.0.0"
#define MyAppExeName "ClaudeContentStudio.exe"

[Setup]
AppId={{6C6E9B2A-6C3B-4E2B-9F7B-3A2E7E9B7C41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\..\dist
OutputBaseFilename=ClaudeContentStudioSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
DisableWelcomePage=no
SetupIconFile=
ChangesAssociations=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\..\dist\ClaudeContentStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; User data (config/history/generated media, and API keys in Credential Manager) lives outside
; {app} — same policy as install.ps1/uninstall.ps1 — so a normal uninstall never touches it.
