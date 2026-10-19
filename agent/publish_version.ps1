# =============================================================
# Trilan Agent — Helper para publicar nova versão OTA
# Autenticacao: variavel de ambiente TRILAN_PUBLISH_TOKEN (token so de publicacao) ou -AdminPassword.
# Uso: .\publish_version.ps1 -Version "2.0.0" -ServerUrl "https://seudominio.com" -AdminToken "seu-token" -Notes "Correção de bug X"
# =============================================================

param(
    [Parameter(Mandatory=$true)]  [string]$Version,
    [Parameter(Mandatory=$true)]  [string]$ServerUrl,
    [Parameter(Mandatory=$false)] [string]$AdminPassword = "",
    [Parameter(Mandatory=$false)] [string]$Notes = "",
    [Parameter(Mandatory=$false)] [string]$UrlService = "",
    [Parameter(Mandatory=$false)] [string]$UrlTray = ""
)

$ServiceExe = ".\dist\TrilanAgentService.exe"
$TrayExe    = ".\dist\TrilanAgentTray.exe"

# Verifica se os executáveis existem
if (-not (Test-Path $ServiceExe)) {
    Write-Error "Arquivo não encontrado: $ServiceExe. Execute .\build.ps1 primeiro."
    exit 1
}

# Calcula SHA256
Write-Host "Calculando SHA256 dos executáveis..."
$HashService = (Get-FileHash $ServiceExe -Algorithm SHA256).Hash.ToLower()
Write-Host "  TrilanAgentService.exe: $HashService"

$HashTray = $null
if (Test-Path $TrayExe) {
    $HashTray = (Get-FileHash $TrayExe -Algorithm SHA256).Hash.ToLower()
    Write-Host "  TrilanAgentTray.exe:    $HashTray"
}

Write-Host ""
Write-Host "============================="
Write-Host "SHA256 calculados:"
Write-Host "  Service: $HashService"
if ($HashTray) { Write-Host "  Tray:    $HashTray" }
Write-Host "============================="
Write-Host ""

# Se URLs não foram fornecidas, exibe instruções
if (-not $UrlService) {
    Write-Host "INSTRUÇÃO:" -ForegroundColor Yellow
    Write-Host "1. Crie uma Release no GitHub (tag: $Version, título: v$Version)" -ForegroundColor Yellow
    Write-Host "2. Faça upload de TrilanAgentService.exe e TrilanAgentTray.exe como assets" -ForegroundColor Yellow
    Write-Host "3. Copie as URLs dos assets e re-execute com -UrlService e -UrlTray" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Exemplo de URL de asset GitHub:" -ForegroundColor Cyan
    Write-Host "  https://github.com/isaqueschaffer/backup-automation/releases/download/$Version/TrilanAgentService.exe" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Hashes para usar no próximo comando:" -ForegroundColor Green
    Write-Host "  -UrlService 'URL_DO_SERVICE_EXE' -UrlTray 'URL_DO_TRAY_EXE'" -ForegroundColor Green
    Write-Host "  SHA256 Service: $HashService"
    if ($HashTray) { Write-Host "  SHA256 Tray:    $HashTray" }
    exit 0
}

if ($env:TRILAN_PUBLISH_TOKEN) {
    # Token só de publicação: registra versões, não dá acesso ao painel
    $AuthHeaders = @{ "X-Publish-Token" = $env:TRILAN_PUBLISH_TOKEN; "Content-Type" = "application/json" }
} elseif ($AdminPassword) {
    Write-Host "Fazendo login na API..."
    $LoginBody = @{ password = $AdminPassword } | ConvertTo-Json
    try {
        $LoginResp = Invoke-RestMethod -Uri "$ServerUrl/api/v1/auth/login" -Method POST -Body $LoginBody -Headers @{"Content-Type"="application/json"}
        $AuthHeaders = @{ "Authorization" = "Bearer $($LoginResp.access_token)"; "Content-Type" = "application/json" }
    } catch {
        Write-Error "Falha no login. Verifique a senha do painel e a URL."
        exit 1
    }
} else {
    Write-Error "Defina a variavel TRILAN_PUBLISH_TOKEN ou informe -AdminPassword."
    exit 1
}

Write-Host "Registrando versão $Version na API do servidor..."
$Body = @{
    version       = $Version
    notes         = $Notes
    url_service   = $UrlService
    sha256_service = $HashService
}

if ($UrlTray)  { $Body.url_tray    = $UrlTray }
if ($HashTray) { $Body.sha256_tray = $HashTray }

$Headers = $AuthHeaders
$Headers["Content-Type"] = "application/json; charset=utf-8"

try {
    $Response = Invoke-RestMethod `
        -Uri "$ServerUrl/api/v1/admin/agent-version" `
        -Method POST `
        -Headers $Headers `
        -Body ([System.Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 5)))

    Write-Host "" 
    Write-Host "✅ Versão $Version registrada com sucesso!" -ForegroundColor Green
    Write-Host "   ID: $($Response.id)"
    Write-Host "   Os agentes serão notificados na próxima verificação (até 1h)."
} catch {
    Write-Error "Falha ao registrar versão: $_"
    Write-Host "Verifique o AdminToken e ServerUrl."
    exit 1
}
