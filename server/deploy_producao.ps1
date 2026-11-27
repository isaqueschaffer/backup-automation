# Leva o ramo `isaque` para a producao (desde 25/11/2026).
#
# O Dokploy le o codigo do ramo `producao` do repositorio publico isaqueschaffer/backup-automation (fonte Git, sem
# credencial) e NAO tem webhook: depois do push, este script dispara o deploy do Backend e/ou do Frontend pela API.
# As credenciais do Dokploy vem do arquivo local `.credenciais/dokploy-painel.md` (fora do git) e nunca sao
# exibidas. So o administrador do repositorio publico consegue atualizar `producao` (ruleset producao-somente-admin).
#
# Uso (na raiz do repositorio):
#   ./server/deploy_producao.ps1                      # push isaque -> producao, deploy de Backend e Frontend e espera
#   ./server/deploy_producao.ps1 -Apenas Backend      # so um dos dois
#   ./server/deploy_producao.ps1 -SemPush -SemEsperar # so dispara o deploy do que ja esta em producao
param(
    [ValidateSet("Ambos", "Backend", "Frontend")] [string]$Apenas = "Ambos",
    [switch]$SemPush,
    [switch]$SemEsperar,
    [int]$LimiteMin = 30
)
$ErrorActionPreference = "Stop"
$raiz = (git rev-parse --show-toplevel).Trim()
$painel = "https://dokploy.suportetrilan.com.br/api"

if (-not $SemPush) {
    $ramo = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($ramo -ne "isaque") { throw "Rode a partir do ramo isaque (atual: $ramo)." }
    git fetch -q origin isaque
    if ((git rev-parse HEAD) -ne (git rev-parse origin/isaque)) { throw "O isaque local difere de origin/isaque: faca o push para origin isaque antes." }
    git push isaque_repo isaque:producao
    if ($LASTEXITCODE -ne 0) { throw "Falha no push para producao." }
}
$commit = (git rev-parse --short isaque).Trim()

$arq = Join-Path $raiz ".credenciais/dokploy-painel.md"
if (-not (Test-Path $arq)) { throw "Arquivo local '$arq' nao encontrado (credenciais do Dokploy)." }
$txt = Get-Content $arq -Raw -Encoding UTF8
$email = [regex]::Match($txt, '\*\*E-mail / Usu[^|]*\|\s*`([^`]+)`').Groups[1].Value
$senha = [regex]::Match($txt, '\*\*Senha\*\*\s*\|\s*`([^`]+)`').Groups[1].Value
if (-not $email -or -not $senha) { throw "Nao achei e-mail/senha do painel em '$arq'." }

$sessao = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod -Method Post -Uri "$painel/auth/sign-in/email" -WebSession $sessao -ContentType "application/json" `
    -Body (@{ email = $email; password = $senha } | ConvertTo-Json) -TimeoutSec 60 | Out-Null
Remove-Variable senha

$apps = @{}
foreach ($p in (Invoke-RestMethod -Uri "$painel/project.all" -WebSession $sessao -TimeoutSec 60)) {
    foreach ($env in $p.environments) { foreach ($a in $env.applications) { $apps[$a.name] = $a.applicationId } }
}
$alvos = if ($Apenas -eq "Ambos") { @("Backend", "Frontend") } else { @($Apenas) }

function Get-UltimoDeploy($id) {
    # O painel do Dokploy às vezes responde 502/timeout com a VM ocupada pelo build: tenta de novo antes de desistir
    for ($t = 1; $t -le 6; $t++) {
        try {
            $app = Invoke-RestMethod -Uri "$painel/application.one?applicationId=$id" -WebSession $sessao -TimeoutSec 60
            return ($app.deployments | Sort-Object createdAt | Select-Object -Last 1)
        } catch {
            if ($t -eq 6) { throw }
            Start-Sleep -Seconds 20
        }
    }
}

foreach ($nome in $alvos) {
    if (-not $apps.ContainsKey($nome)) { throw "Application '$nome' nao encontrado no Dokploy." }
    $antes = (Get-UltimoDeploy $apps[$nome]).createdAt
    Invoke-RestMethod -Method Post -Uri "$painel/application.deploy" -WebSession $sessao -ContentType "application/json" `
        -Body (@{ applicationId = $apps[$nome] } | ConvertTo-Json) -TimeoutSec 60 | Out-Null
    Write-Host "Deploy de $nome disparado ($commit)."
    if ($SemEsperar) { continue }
    # Um de cada vez: o build do Railpack pesa na VM e dois juntos ja travaram a fila (24/11/2026)
    $fim = (Get-Date).AddMinutes($LimiteMin)
    do {
        Start-Sleep -Seconds 30
        $d = Get-UltimoDeploy $apps[$nome]
    } while ((($d.createdAt -eq $antes) -or ($d.status -eq "running")) -and (Get-Date) -lt $fim)
    Write-Host "  $nome -> $($d.status)"
    if ($d.status -ne "done") {
        throw "Deploy de $nome terminou como '$($d.status)'. Log na VM: /etc/dokploy/logs/<appName>/ (ver CLAUDE.md)."
    }
}
Write-Host "Producao atualizada com $commit."
