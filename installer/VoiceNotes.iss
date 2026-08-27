#define MyAppName "Voice Notes"
#define MyAppVersion "0.10.20"
#define MyAppPublisher "Voice Notes"
#define MyAppExeName "VoiceNotes.exe"

[Setup]
AppId={{B6E79191-B14A-49FD-B2D8-5A4642EC418C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Voice Notes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=VoiceNotes-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
UninstallDisplayName={#MyAppName}
SetupIconFile=..\assets\voice-notes.ico

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "startup"; Description: "Iniciar automaticamente com o Windows (na bandeja do sistema)"; GroupDescription: "Inicialização:"
Name: "providers"; Description: "Instalar automaticamente Codex CLI e Claude Code (requer internet)"; GroupDescription: "Resumos por IA:"

[Files]
Source: "..\dist\VoiceNotes\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\record_transcript_resume\resources\install_providers.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\Voice Notes"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Voice Notes"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\Voice Notes"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--start-hidden"; Tasks: startup

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{tmp}\install_providers.ps1"" -ToolsRoot ""{localappdata}\Voice Notes\tools"""; StatusMsg: "Preparando providers de resumo..."; Tasks: providers; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o widget Voice Notes"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Parameters: "--start-hidden"; Flags: nowait runhidden skipifnotsilent
