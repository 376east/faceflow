[Setup]
AppId={{1F453AAA-ED50-4CB7-82F4-43BE924C64DC}
AppName=FaceFlow
AppPublisher=37.6 East
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\FaceFlow
DefaultGroupName=FaceFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#BuildOutput}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=FaceFlow

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FaceFlow"; Filename: "{app}\runtime\python.exe"; Parameters: "-X utf8 ""{app}\app\launch.py"""; WorkingDir: "{app}\app"

[Run]
Filename: "{app}\runtime\python.exe"; Parameters: "-X utf8 ""{app}\app\launch.py"""; WorkingDir: "{app}\app"; Description: "{cm:LaunchProgram,FaceFlow}"; Flags: nowait postinstall skipifsilent
