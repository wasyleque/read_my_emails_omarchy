; Instalator MailVoice dla Windows (Inno Setup 6).
; Budowanie:  ISCC.exe installer\MailVoice.iss
;   wersja:   ISCC.exe /DMyAppVersion=0.1.0-beta installer\MailVoice.iss
; Wejście: katalog dist\MailVoice\ z PyInstalera (zbuduj najpierw: pyinstaller MailVoice.spec --noconfirm).
; Wynik:   installer\out\MailVoice-Setup-<wersja>.exe
;
; Instalacja per-użytkownik (bez uprawnień administratora). Dane aplikacji (konta, baza, hasła)
; trzyma system w AppData i NIE są ruszane przy odinstalowaniu.

#define MyAppName "MailVoice"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-beta"
#endif
#define MyAppPublisher "MailVoice"
#define MyAppExeName "MailVoice.exe"

[Setup]
AppId={{5BDC83CA-82D5-474C-8835-C181A3DF7BE0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Instalacja bez administratora (do lokalnego Program Files użytkownika)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=out
OutputBaseFilename=MailVoice-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Cały katalog onedir z PyInstalera (.exe + biblioteki)
Source: "..\dist\MailVoice\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
