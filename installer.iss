; Inno Setup 6 script. Build with build.ps1 (or: ISCC.exe installer.iss) after PyInstaller finished.
#define AppName "Video Downloader"
#define AppVersion "1.0.0"
#define AppExe "MediaDownloader.exe"

[Setup]
AppId={{B7E2D4A1-5C3F-4E8A-9D61-2F0A7C9E1B34}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=MediaDownloader-Setup
SetupIconFile=assets\icons\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"; LicenseFile: "installer\license_tr.txt"
Name: "english"; MessagesFile: "compiler:Default.isl"; LicenseFile: "installer\license_en.txt"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"; LicenseFile: "installer\license_ru.txt"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"; LicenseFile: "installer\license_de.txt"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"; LicenseFile: "installer\license_it.txt"

[CustomMessages]
turkish.WebView2Missing=Bu uygulama Microsoft Edge WebView2 gerektirir ve bilgisayarınızda bulunamadı.%nİndirme sayfasını açmak ister misiniz? (Kurulum yine de devam eder.)
english.WebView2Missing=This app needs Microsoft Edge WebView2, which was not found on your computer.%nOpen the download page? (Setup will continue anyway.)
russian.WebView2Missing=Для приложения нужен Microsoft Edge WebView2, он не найден на этом компьютере.%nОткрыть страницу загрузки? (Установка всё равно продолжится.)
german.WebView2Missing=Diese App benötigt Microsoft Edge WebView2, das auf diesem Computer nicht gefunden wurde.%nDie Download-Seite öffnen? (Die Installation wird trotzdem fortgesetzt.)
italian.WebView2Missing=Questa app richiede Microsoft Edge WebView2, che non è stato trovato sul computer.%nAprire la pagina di download? (L'installazione proseguirà comunque.)

[Files]
Source: "dist\MediaDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Key = 'EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Installed(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\' + WebView2Key)
         or RegKeyExists(HKLM, 'SOFTWARE\Microsoft\' + WebView2Key)
         or RegKeyExists(HKCU, 'Software\Microsoft\' + WebView2Key);
end;

function InitializeSetup(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
  if not WebView2Installed() then
    if MsgBox(CustomMessage('WebView2Missing'), mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://go.microsoft.com/fwlink/p/?LinkId=2124703', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;
