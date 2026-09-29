; Inno Setup script: a standard "Next, Next, Install" setup.exe.
; Built by build_windows.bat after PyInstaller has created dist\STM32DeviceTool\.

#define AppName      "STM32 Device Tool"
#define AppVersion   "1.0.0"
#define AppPublisher "Divjaklab"
#define AppExeName   "STM32DeviceTool.exe"

[Setup]
; Fixed GUID so future versions upgrade in place. Never change it.
AppId={{A93AA8EE-2CD7-430B-AFB2-BA5BFD3B0E2D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=STM32DeviceTool-Setup-{#AppVersion}
SetupIconFile=resources\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\STM32DeviceTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Windows needs ST's USB driver (STSW-LINK009) for flashing and for the log port.
Filename: "https://www.st.com/en/development-tools/stsw-link009.html"; Description: "Open the ST-LINK USB driver download page (needed once per PC)"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{app}\{#AppExeName}"; Description: "Start {#AppName}"; Flags: postinstall nowait skipifsilent
