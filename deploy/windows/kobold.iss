; The Klever Kobold -- the Windows installer. Built by
; .github/workflows/windows-installer.yml on a Windows runner:
;
;   ISCC.exe /DAppVersion=1.2.3 deploy\windows\kobold.iss
;       -> dist\KleverKoboldSetup.exe (~15 MB; downloads OllamaSetup.exe while installing)
;   ISCC.exe /DAppVersion=1.2.3 /DBundleOllama deploy\windows\kobold.iss
;       -> the same with OllamaSetup.exe embedded (~1.6 GB), for an offline install
;
; Expects the frozen program in dist\kobold (see kobold.spec) and, with
; BundleOllama, OllamaSetup.exe beside this script.
;
; Everything is per-user, like Ollama's own installer: no UAC prompt, the
; program under %LOCALAPPDATA%\Programs\KleverKobold, the index under
; %LOCALAPPDATA%\kleverkobold, the models under %USERPROFILE%\.ollama.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Dist
  #define Dist "..\..\dist\kobold"
#endif
#define OllamaURL "https://ollama.com/download/OllamaSetup.exe"

[Setup]
AppId={{7D1F4C0B-2E6A-4B8E-9C3D-5A1E0F6B2C41}
AppName=The Klever Kobold
AppVersion={#AppVersion}
AppPublisher=Richard Polzin
AppPublisherURL=https://github.com/DeastinY/klever-kobold
AppSupportURL=https://github.com/DeastinY/klever-kobold/issues
DefaultDirName={localappdata}\Programs\KleverKobold
DefaultGroupName=The Klever Kobold
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=KleverKoboldSetup
SetupIconFile=..\icon\kobold.ico
UninstallDisplayIcon={app}\kobold.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
LicenseFile=..\..\LICENSE

[Tasks]
Name: "path"; Description: "Add kobold to the PATH (for a terminal, or Claude Desktop's MCP config)"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#Dist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef BundleOllama
Source: "OllamaSetup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not OllamaInstalled
#endif

[Icons]
Name: "{group}\The Klever Kobold"; Filename: "{app}\kobold.exe"; Parameters: "serve"; Comment: "Opens the kobold at http://localhost:8765"
Name: "{group}\Kobold setup (models and index)"; Filename: "{app}\kobold.exe"; Parameters: "setup"; Comment: "Pulls the models and fetches the index; safe to re-run"
Name: "{group}\Kobold doctor"; Filename: "{cmd}"; Parameters: "/k """"{app}\kobold.exe"" doctor"""; IconFilename: "{app}\kobold.exe"; Comment: "Checks Ollama, the models and the index"
Name: "{autodesktop}\The Klever Kobold"; Filename: "{app}\kobold.exe"; Parameters: "serve"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: path; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Ollama's own installer, silently. It is Inno Setup too, so the usual switches apply.
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; StatusMsg: "Installing Ollama..."; Check: not OllamaInstalled; Flags: waituntilterminated
; Offered on the last page. `setup` runs to completion before `serve` starts.
Filename: "{app}\kobold.exe"; Parameters: "setup"; Description: "Fetch the models and the index now (about 4.3 GB)"; Flags: postinstall skipifsilent
Filename: "{app}\kobold.exe"; Parameters: "serve"; Description: "Open the kobold"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  DownloadPage: TDownloadWizardPage;

function OllamaInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
    or (FileSearch('ollama.exe', GetEnv('PATH')) <> '');
end;

function NeedsAddPath(Param: string): Boolean;
var
  Current: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Current) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(Current) + ';') = 0;
end;

var
  LastLogged: Int64;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if (Progress = ProgressMax) or (Progress - LastLogged > 100000000) then
  begin
    Log(Format('%s: %d of %d MB', [FileName, Progress div 1000000, ProgressMax div 1000000]));
    LastLogged := Progress;
  end;
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then
    Result := Result + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo + NewLine + NewLine;
  if OllamaInstalled then
    Result := Result + 'Ollama:' + NewLine + Space + 'already installed, left as it is'
  else
  #ifdef BundleOllama
    Result := Result + 'Ollama:' + NewLine + Space + 'installed alongside (per user, no administrator rights)';
  #else
    Result := Result + 'Ollama:' + NewLine + Space + 'downloaded from ollama.com (about 1.5 GB) and installed alongside';
  #endif
  Result := Result + NewLine + NewLine + 'Afterwards:' + NewLine + Space
    + 'the two models (about 4 GB) and the rules index (270 MB), if you let it';
end;

// The download happens here rather than in NextButtonClick, because
// PrepareToInstall also runs for a silent install (/VERYSILENT): the CI job
// that installs the result on a Windows runner, or an admin rolling it out.
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  #ifndef BundleOllama
  if OllamaInstalled then
    exit;
  if WizardSilent then
  begin
    // No wizard to show a page on: the plain call, which logs its progress.
    try
      DownloadTemporaryFile('{#OllamaURL}', 'OllamaSetup.exe', '', @OnDownloadProgress);
    except
      Result := 'Could not download Ollama: ' + AddPeriod(GetExceptionMessage);
    end;
    exit;
  end;
  DownloadPage.Clear;
  DownloadPage.Add('{#OllamaURL}', 'OllamaSetup.exe', '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      if DownloadPage.AbortedByUser then
        Result := 'The Ollama download was cancelled.'
      else
        Result := 'Could not download Ollama: ' + AddPeriod(GetExceptionMessage)
          + ' Install it from https://ollama.com/download and run this installer again.';
    end;
  finally
    DownloadPage.Hide;
  end;
  #endif
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Current, App: string;
  P: Integer;
begin
  // Take {app} back out of the user's PATH; models and the index are left alone.
  if CurUninstallStep = usPostUninstall then
  begin
    App := ExpandConstant('{app}');
    if RegQueryStringValue(HKCU, 'Environment', 'Path', Current) then
    begin
      P := Pos(';' + Uppercase(App), Uppercase(Current));
      if P > 0 then
      begin
        Delete(Current, P, Length(App) + 1);
        RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Current);
      end;
    end;
  end;
end;
