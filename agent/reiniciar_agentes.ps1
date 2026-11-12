# Pede o reinicio do agente em TODAS as maquinas online, de todas as contas (passo que vem logo depois do
# publish_version.ps1). O endpoint /machines/restart-agent-all age so na conta do contexto: o super admin sem
# X-Conta-ID enxerga so a conta da plataforma, por isso o script percorre cada conta listada, sempre com X-Conta-ID
# (a conta da plataforma tambem esta na lista; chamar sem o cabecalho contaria a mesma conta duas vezes).
#
# O reinicio e pedido a maquinas online (offline ficam de fora e pegam a versao nova pela OTA quando voltarem) e
# acontece no proximo ping (ate ~15 s); quem esta em backup espera ele terminar (ou 2 h, se travado).
# A senha nao e gravada em lugar nenhum: so e usada no login.
param(
    [Parameter(Mandatory = $true)][string]$AdminPassword,
    [string]$ServerUrl = "https://server.suportetrilan.com.br"
)

$ErrorActionPreference = "Stop"
$ServerUrl = $ServerUrl.TrimEnd("/")

$token = (Invoke-RestMethod -Method Post "$ServerUrl/api/v1/auth/login" -ContentType "application/json" `
    -Body (@{ password = $AdminPassword } | ConvertTo-Json)).access_token
$h = @{ Authorization = "Bearer $token" }

# O PowerShell 5.1 entrega a lista JSON como um unico array: o pipeline com $_ a desfaz em um item por conta
$contas = @(Invoke-RestMethod "$ServerUrl/api/v1/admin/contas" -Headers $h | ForEach-Object { $_ })
Write-Host "Contas encontradas: $($contas.Count)"

$totalFila = 0
$totalOffline = 0

foreach ($c in $contas) {
    $hc = @{ Authorization = "Bearer $token"; "X-Conta-ID" = [string]$c.id }
    try {
        $r = Invoke-RestMethod -Method Post "$ServerUrl/api/v1/machines/restart-agent-all" -Headers $hc
        Write-Host ("  [{0}] reinicio pedido: {1} online, {2} offline (ignoradas)" -f $c.nome, $r.queued, $r.skipped_offline)
        $totalFila += $r.queued; $totalOffline += $r.skipped_offline
    } catch {
        Write-Host ("  [{0}] FALHOU: {1}" -f $c.nome, $_.Exception.Message) -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Reinicio pedido em $totalFila maquina(s) online; $totalOffline offline/ignorada(s)."
Write-Host "Elas reiniciam no proximo ping (ate ~15 s); quem esta em backup espera terminar."
