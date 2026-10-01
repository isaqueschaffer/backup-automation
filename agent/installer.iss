; Trilan NVR Backup Agent - Installer Script

[Setup]
AppName=Trilan NVR Backup Agent
AppVersion=1.0
DefaultDirName={pf}\Trilan NVR Backup Agent
DefaultGroupName=Trilan NVR
OutputBaseFilename=TrilanAgentSetup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
OutputDir=dist

[Files]
Source: "dist\TrilanAgentService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\TrilanAgentTray.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Trilan Agent Tray"; Filename: "{app}\TrilanAgentTray.exe"
Name: "{commonstartup}\Trilan Agent Tray"; Filename: "{app}\TrilanAgentTray.exe"

[Run]
Filename: "{app}\TrilanAgentService.exe"; Parameters: "install"; Flags: runhidden
Filename: "{app}\TrilanAgentService.exe"; Parameters: "start"; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""Trilan Agent Tray FTP"" dir=in action=allow program=""{app}\TrilanAgentTray.exe"" enable=yes protocol=TCP localport=21"; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""Trilan Agent Service FTP"" dir=in action=allow program=""{app}\TrilanAgentService.exe"" enable=yes protocol=TCP localport=21"; Flags: runhidden
Filename: "{app}\TrilanAgentTray.exe"; Flags: nowait postinstall; Description: "Iniciar o Trilan Agent Tray agora"

[UninstallRun]
Filename: "{app}\TrilanAgentService.exe"; Parameters: "stop"; Flags: runhidden
Filename: "{app}\TrilanAgentService.exe"; Parameters: "remove"; Flags: runhidden
Filename: "taskkill"; Parameters: "/f /im TrilanAgentTray.exe"; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Trilan Agent Tray FTP"""; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Trilan Agent Service FTP"""; Flags: runhidden

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'Configuracao do Agente Trilan',
    'Insira os dados de conexao com o servidor na nuvem.',
    'Esses dados serao salvos no arquivo agent.conf.');

  ConfigPage.Add('URL do Servidor:', False);
  ConfigPage.Add('Client ID:', False);
  ConfigPage.Add('API Key:', False);

  ConfigPage.Values[0] := 'http://hd208ec5kxz.sn.mynetname.net:7001';
  ConfigPage.Values[1] := '';
  ConfigPage.Values[2] := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then
  begin
    if Trim(ConfigPage.Values[0]) = '' then
    begin
      MsgBox('Por favor, informe a URL do Servidor.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Trim(ConfigPage.Values[1]) = '' then
    begin
      MsgBox('Por favor, informe o Client ID do cliente.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Trim(ConfigPage.Values[2]) = '' then
    begin
      MsgBox('Por favor, informe a API Key.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: String;
  FileContent: String;
  FileHandle: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigFile := ExpandConstant('{app}\agent.conf');

    // Constroi o conteudo do arquivo
    FileContent :=
      '[server]' + #13#10 +
      'url = ' + Trim(ConfigPage.Values[0]) + #13#10 +
      '' + #13#10 +
      '[auth]' + #13#10 +
      'client_id = ' + Trim(ConfigPage.Values[1]) + #13#10 +
      'api_key = ' + Trim(ConfigPage.Values[2]) + #13#10;

    // Salva o arquivo
    if not SaveStringToFile(ConfigFile, FileContent, False) then
    begin
      MsgBox('ERRO: Nao foi possivel criar o arquivo agent.conf em:' + #13#10 +
             ConfigFile + #13#10#13#10 +
             'Verifique as permissoes da pasta de instalacao.',
             mbError, MB_OK);
    end;
  end;
end;
