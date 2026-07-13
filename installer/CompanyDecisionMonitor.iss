#define AppName "Company Decision Monitor"
#define AppVersion "0.1.3"
#define AppVersionName "v0.1.3"
#define AppPublisher "CompanyDecisionMonitor"
#define AppExeName "CompanyDecisionMonitor.exe"
#define AppDistDir "..\dist\CompanyDecisionMonitor"
#define AppIcon "..\src\cdm_desktop\resources\app.ico"

[Setup]
AppId={{B5C3EE9C-9E13-4E5F-93BF-6F2A7E3BB7C2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersionName}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Company Decision Monitor
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=CompanyDecisionMonitor_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
#ifexist AppIcon
SetupIconFile={#AppIcon}
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#AppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
