; audio_separator 安装包（2026-08-27，评估文档 A 级第 3 项）
; 核心包：Tkinter GUI + 批量/Web 脚本 + 首次运行 bootstrap（venv + torch CPU + demucs + bs-roformer-infer）。
; 重依赖（约 1GB）与模型不随包：首次运行自动引导安装（需联网），模型由 demucs 首次分离自动下载。
; 编译：ISCC.exe audio-separator.iss → installer\audio-separator-setup-1.0.0.exe
#define MyAppName "音频分离工具（Demucs）"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "siwpan"

[Setup]
AppId={{C4E1D2B0-9A51-4F8E-A3D7-AUDIOSEPR01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\audio-separator
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=audio-separator-setup-1.0.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\main.py
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
Name: "{app}\models"

[Files]
Source: "_installer-src\stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[UninstallDelete]
; venv 为安装后由 bootstrap 生成的依赖目录，卸载时一并清除
Type: filesandordirs; Name: "{app}\venv"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\run.bat"; WorkingDir: "{app}"
Name: "{group}\批量分离"; Filename: "{app}\RUN_BATCH.bat"; WorkingDir: "{app}"
Name: "{group}\引导安装依赖"; Filename: "{app}\bootstrap.bat"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\run.bat"; WorkingDir: "{app}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
