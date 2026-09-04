#define MyAppName "Amazon Music RPC"
#define MyAppVersion "5.0.3"
#define MyAppPublisher "PumpgunStudios"
#define MyAppExeName "AmazonMusicRPC.exe"

[Setup]
AppId={{8F2B3A1E-4C5D-6E7F-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=AmazonMusicRPC_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=2
LZMABlockSize=32768
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startupentry"; Description: "Start with &Windows"; GroupDescription: "Startup:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion; BeforeInstall: KillRunningApp
Source: "icon.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AmazonMusicRPC"; ValueData: """{app}\{#MyAppExeName}"" --startup"; Flags: uninsdeletevalue; Tasks: startupentry

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--uninstall-cleanup"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveCredentialsAndIntegrations"
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: files; Name: "{userprograms}\{#MyAppName}\Amazon Music Metadata.lnk"
Type: files; Name: "{userprograms}\{#MyAppName}\Amazon Music Beta Metadata.lnk"
Type: files; Name: "{commonprograms}\{#MyAppName}\Amazon Music Metadata.lnk"
Type: files; Name: "{commonprograms}\{#MyAppName}\Amazon Music Beta Metadata.lnk"
Type: files; Name: "{userappdata}\AmazonMusicRPC\*"
Type: dirifempty; Name: "{userappdata}\AmazonMusicRPC"
Type: dirifempty; Name: "{userprograms}\{#MyAppName}"
Type: dirifempty; Name: "{commonprograms}\{#MyAppName}"

[Code]
procedure KillRunningApp;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "{#MyAppExeName}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(800);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RegKey: string;
begin
  if CurUninstallStep = usUninstall then
  begin
    RegKey := 'Software\Microsoft\Windows\CurrentVersion\Run';
    RegDeleteValue(HKEY_CURRENT_USER, RegKey, 'AmazonMusicRPC');
  end;
end;
