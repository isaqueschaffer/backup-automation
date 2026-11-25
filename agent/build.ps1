# Build do agente Windows (Service, Tray) e do pacote do agente Linux.
# Aborta na primeira falha (AGT-10, auditoria de 25/11/2026): versões divergentes, pip, testes, PyInstaller ou o pacote Linux.
# Salvo em UTF-8 COM BOM: o PowerShell 5.1 lê sem BOM como ANSI e quebra os acentos.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$Python = '.\venv\Scripts\python.exe'

function Invoke-Nativo {
    # Programas externos não respeitam $ErrorActionPreference: o que vale é o código de saída.
    # Durante a execução a preferência fica em Continue porque pip e PyInstaller escrevem avisos no stderr, e o
    # PowerShell 5.1 transforma isso em erro quando a saída está redirecionada.
    param([string]$Etapa, [string]$Exe, [string[]]$Argumentos)
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Argumentos
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $anterior
    }
    if ($codigo -ne 0) {
        throw "FALHOU: $Etapa (código de saída $codigo). Build abortado."
    }
}

Write-Host "Conferindo a versão nos três lugares..."
$updater = Get-Content -Raw -Encoding UTF8 'src\application\updater.py'
$iss = Get-Content -Raw -Encoding UTF8 'installer.iss'
$pacote = Get-Content -Raw -Encoding UTF8 '..\server\dashboard\package.json' | ConvertFrom-Json
$vUpdater = if ($updater -match 'CURRENT_VERSION\s*=\s*"([^"]+)"') { $Matches[1] } else { $null }
$vIss = if ($iss -match '(?m)^\s*AppVersion\s*=\s*(\S+)\s*$') { $Matches[1] } else { $null }
$vPainel = $pacote.version
if (-not $vUpdater -or -not $vIss -or -not $vPainel -or $vUpdater -ne $vIss -or $vUpdater -ne $vPainel) {
    throw ("Versões divergentes: updater.py (CURRENT_VERSION)='$vUpdater', installer.iss (AppVersion)='$vIss', " +
           "server/dashboard/package.json (version)='$vPainel'. Iguale as três antes do build.")
}
Write-Host "Versão $vUpdater (updater.py, installer.iss e package.json iguais)."

if (Test-Path $Python) {
    Write-Host "Ambiente virtual já existe; reaproveitando."
} else {
    Write-Host "Criando ambiente virtual..."
    # Python fixo (o build atual usa o 3.14.8), não o que estiver no PATH
    Invoke-Nativo 'criar o venv (py -3.14)' 'py' @('-3.14', '-m', 'venv', 'venv')
}
$vPython = (& $Python -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ($LASTEXITCODE -ne 0 -or $vPython -ne '3.14') {
    throw "O venv usa o Python '$vPython', e o build exige o 3.14. Apague a pasta venv e rode o build de novo."
}

Write-Host "Instalando dependências..."
Invoke-Nativo 'pip install -r requirements.txt' $Python @('-m', 'pip', 'install', '-r', 'requirements.txt')
Invoke-Nativo 'pip install pyinstaller/pywin32' $Python @('-m', 'pip', 'install', 'pyinstaller==6.22.3', 'pywin32==312')

Write-Host "Rodando a suíte de testes do agente..."
Invoke-Nativo 'testes do agente (unittest)' $Python @('-m', 'unittest', 'discover', '-s', 'tests')

Write-Host "Compilando serviço em background (service.exe)..."
# O serviço Windows no PyInstaller precisa ser Console (não windowed) para o pywin32 funcionar
Invoke-Nativo 'PyInstaller do TrilanAgentService' '.\venv\Scripts\pyinstaller.exe' @(
    '--noconfirm', '--onefile',
    '--hidden-import', 'win32timezone',
    '--hidden-import', 'win32serviceutil',
    '--hidden-import', 'win32service',
    '--hidden-import', 'servicemanager',
    '--hidden-import', 'agent',
    '--hidden-import', 'src.application.updater',
    '--hidden-import', 'src.application.backup_job',
    '--hidden-import', 'src.application.webhook_digifort',
    '--hidden-import', 'src.application.webhook_defense',
    '--hidden-import', 'src.olt.huawei_active',
    '--hidden-import', 'psutil',
    '--hidden-import', 'GPUtil',
    '--collect-all', 'imageio_ffmpeg',
    '--collect-all', 'pysnmp',
    '--collect-all', 'pyasn1',
    '--name', 'TrilanAgentService',
    'service.py'
)

Write-Host "Compilando aplicativo da bandeja (tray.exe)..."
Invoke-Nativo 'PyInstaller do TrilanAgentTray' '.\venv\Scripts\pyinstaller.exe' @(
    '--noconfirm', '--onefile', '--windowed',
    '--collect-all', 'pystray',
    '--collect-all', 'PIL',
    '--hidden-import', 'pystray',
    '--hidden-import', 'pystray._win32',
    '--name', 'TrilanAgentTray',
    'tray.py'
)

Write-Host "Gerando o pacote de código do agente Linux (Mikrotik, OTA)..."
Invoke-Nativo 'pacote do agente Linux (pacote_linux.py)' $Python @('pacote_linux.py')

Write-Host "Limpando arquivos temporários..."
foreach ($item in @('build', 'TrilanAgentService.spec', 'TrilanAgentTray.spec')) {
    if (Test-Path $item) { Remove-Item -Recurse -Force $item }
}

Write-Host "======================================"
Write-Host "Build $vUpdater concluído! Executáveis na pasta 'dist'"
Write-Host "======================================"
