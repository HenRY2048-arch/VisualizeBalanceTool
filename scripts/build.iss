; VisualizeBalance Installer - Inno Setup 5
; Compile with Inno Setup 5 (iscc.exe scripts\build.iss)

[Setup]
AppName=VisualizeBalance
AppVersion=1.7.0
AppPublisher=VisualizeBalance
DefaultDirName={pf}\VisualizeBalance
DefaultGroupName=VisualizeBalance
OutputDir=Output
OutputBaseFilename=VisualizeBalance-Setup
Compression=lzma
SolidCompression=yes
; Use modern wizard style (flat) if supported, otherwise classic
WizardImageFile=..\assets\wizard_image.bmp
SetupIconFile=..\assets\icon_normal.ico
UninstallDisplayIcon={app}\VisualizeBalance.exe
ArchitecturesAllowed=x86 x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startupicon"; Description: "Start with Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\VisualizeBalance.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VisualizeBalance"; Filename: "{app}\VisualizeBalance.exe"
Name: "{group}\Uninstall VisualizeBalance"; Filename: "{uninstallexe}"
Name: "{commondesktop}\VisualizeBalance"; Filename: "{app}\VisualizeBalance.exe"; Tasks: desktopicon
Name: "{userstartup}\VisualizeBalance"; Filename: "{app}\VisualizeBalance.exe"; Tasks: startupicon

[Run]
Filename: "{app}\VisualizeBalance.exe"; Description: "Launch VisualizeBalance"; Flags: nowait postinstall skipifsilent
