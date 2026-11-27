# Trilan Backups - prepara este Windows para o backup feito pelo agente no MikroTik (SSH / SFTP / SMB).
#
# O que faz (pode rodar de novo sem problema):
#   1. instala e liga o OpenSSH Server (servico sshd, inicio automatico);
#   2. libera a porta 22 no firewall do Windows;
#   3. cria (ou redefine a senha de) a conta local "trilan_backup" e a coloca no grupo Administradores.
#      O grupo e achado pelo identificador fixo do Windows (S-1-5-32-544), entao funciona em Windows
#      em portugues ("Administradores"), ingles ("Administrators") ou qualquer outro idioma.
#   4. mostra o IP e a impressao digital da chave SSH desta maquina, para conferir no painel.
#
# Como usar: abra o PowerShell como administrador nesta maquina e rode
#   powershell -ExecutionPolicy Bypass -File .\preparar_acesso_ssh.ps1
# No painel, no equipamento: usuario SSH = trilan_backup, senha = a que voce digitar aqui.
# Outro nome de conta: .\preparar_acesso_ssh.ps1 -Usuario outro_nome

param([string]$Usuario = "trilan_backup")

$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Rode este script num PowerShell aberto como administrador." -ForegroundColor Red
    exit 1
}

# 1. OpenSSH Server
Write-Host "[1/4] OpenSSH Server..."
$cap = Get-WindowsCapability -Online | Where-Object { $_.Name -like "OpenSSH.Server*" } | Select-Object -First 1
if (-not $cap) { Write-Host "Este Windows nao oferece o OpenSSH Server (Windows 10 1809 / Server 2019 ou mais novo)." -ForegroundColor Red; exit 1 }
if ($cap.State -ne "Installed") { Add-WindowsCapability -Online -Name $cap.Name | Out-Null }
Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd
Write-Host "      sshd: $((Get-Service sshd).Status)"

# 2. Firewall (porta 22)
Write-Host "[2/4] Firewall, porta 22..."
$regra = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
if ($regra) { Enable-NetFirewallRule -Name "OpenSSH-Server-In-TCP" }
else {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True `
        -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}

# 3. Conta trilan_backup no grupo Administradores
Write-Host "[3/4] Conta '$Usuario'..."
while ($true) {
    $s1 = Read-Host "      Senha para '$Usuario' (anote: ela vai no painel)" -AsSecureString
    $s2 = Read-Host "      Repita a senha" -AsSecureString
    $t1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
    $t2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s2))
    if (-not $t1) { Write-Host "      A senha nao pode ficar vazia." -ForegroundColor Yellow; continue }
    if ($t1 -ne $t2) { Write-Host "      As senhas nao conferem, tente de novo." -ForegroundColor Yellow; continue }
    break
}
$t1 = $null; $t2 = $null
if (Get-LocalUser -Name $Usuario -ErrorAction SilentlyContinue) {
    Set-LocalUser -Name $Usuario -Password $s1 -PasswordNeverExpires $true
    Enable-LocalUser -Name $Usuario
    Write-Host "      conta ja existia: senha redefinida."
} else {
    New-LocalUser -Name $Usuario -Password $s1 -PasswordNeverExpires -AccountNeverExpires -UserMayNotChangePassword `
        -Description "Trilan Backups - acesso do agente" | Out-Null
    Write-Host "      conta criada."
}
$grupo = Get-LocalGroup -SID "S-1-5-32-544"
$membro = Get-LocalGroupMember -Group $grupo.Name -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*\$Usuario" }
if (-not $membro) { Add-LocalGroupMember -Group $grupo.Name -Member $Usuario }
Write-Host "      no grupo '$($grupo.Name)'."

# 4. Dados para o painel
Write-Host "[4/4] Dados para conferir no painel:"
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }
foreach ($ip in $ips) { Write-Host "      IP: $($ip.IPAddress) ($($ip.InterfaceAlias))" }
$chave = "$env:ProgramData\ssh\ssh_host_ed25519_key.pub"
if (Test-Path $chave) {
    $fp = & "$env:WINDIR\System32\OpenSSH\ssh-keygen.exe" -lf $chave
    Write-Host "      Impressao digital da chave SSH: $fp"
}
Write-Host ""
Write-Host "Pronto. No painel, no equipamento: usuario SSH '$Usuario' e a senha que voce digitou." -ForegroundColor Green
Write-Host "Teste de outra maquina da rede: ssh $Usuario@<IP acima>"
