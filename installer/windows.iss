; Inno Setup script for Time Tracker (PRD-02 §12.2).
; Per-user install (no elevation), Start Menu shortcut, optional Desktop shortcut,
; optional "start at login" (the same HKCU Run value the app manages itself).
; The data folder (%LOCALAPPDATA%\TimeTracker) is never touched by the uninstaller.
;
; Build:  ISCC.exe /DAppVersion=1.0.0 /DSourceDir=..\dist\release\windows\timetracker.dist installer\windows.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\release\windows\timetracker.dist"
#endif

[Setup]
AppId={{7C1E6C2A-5B1E-4E0B-9F8B-1D2E3F4A5B6C}
AppName=Time Tracker
AppVersion={#AppVersion}
AppVerName=Time Tracker {#AppVersion}
AppPublisher=Wouter
DefaultDirName={localappdata}\Programs\Time Tracker
DefaultGroupName=Time Tracker
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=TimeTracker-{#AppVersion}-setup
SetupIconFile=..\src\timetracker\resources\icon.ico
UninstallDisplayIcon={app}\timetracker.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start Time Tracker when I &log in"; GroupDescription: "Start-up:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Time Tracker"; Filename: "{app}\timetracker.exe"
Name: "{group}\Uninstall Time Tracker"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Time Tracker"; Filename: "{app}\timetracker.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TimeTracker"; ValueData: """{app}\timetracker.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\timetracker.exe"; Description: "Launch Time Tracker"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Nothing: the uninstaller never deletes %LOCALAPPDATA%\TimeTracker (the user's data).
