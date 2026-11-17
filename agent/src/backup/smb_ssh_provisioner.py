"""
Provisiona, por SSH, um usuário Windows SOMENTE LEITURA na máquina do cliente (UNM2000 / Digifort) e
compartilha cada pasta cadastrada como share oculto de leitura. Depois disso o agente (inclusive o do
MikroTik) acessa as pastas por SMB com esse usuário, sem usar a conta de administrador no dia a dia.

Fluxo:
  1. Entra por SSH com a conta administradora (usada só aqui) e roda um script PowerShell que
       - cria (ou redefine a senha de) o usuário `trilan_leitura`;
       - concede a ele só leitura (RX) na pasta, via NTFS (icacls);
       - cria um share oculto `trilan_ro_<hash>$` com acesso de leitura só para esse usuário.
  2. Guarda usuário, senha e share em `data/smb_leitura.json` (por host) para as próximas execuções.
O processo é idempotente: rodar de novo só refaz a senha e os shares.
"""
import base64
import hashlib
import json
import logging
import re
import secrets
import string
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.backup.smb_storage import SmbTarget, parse_smb_target

USUARIO_LEITURA = "trilan_leitura"
_LOCK = threading.Lock()


class ProvisionamentoErro(Exception):
    pass


def _arquivo_cache() -> Path:
    from src.core.config import DIR_AGENT
    pasta = DIR_AGENT / "data"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / "smb_leitura.json"


def _ler_cache() -> dict:
    try:
        return json.loads(_arquivo_cache().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_cache(dados: dict) -> None:
    arq = _arquivo_cache()
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(arq)


def gerar_senha(tamanho: int = 24) -> str:
    """Senha aleatória sem aspas nem caracteres especiais de shell, mas que cumpre a complexidade do Windows."""
    letras = string.ascii_letters + string.digits
    while True:
        s = "".join(secrets.choice(letras) for _ in range(tamanho))
        if any(c.islower() for c in s) and any(c.isupper() for c in s) and any(c.isdigit() for c in s):
            return s


def caminho_local_windows(pasta_origem: str, host: str) -> Optional[str]:
    """Converte `D:UNM2000/emsback`, `host:D:\\x` etc. em `D:\\UNM2000\\emsback`. None se não for pasta de drive."""
    t = parse_smb_target(pasta_origem, host=host)
    m = re.fullmatch(r"([A-Za-z])\$", t.share)
    if not m:
        return None
    return f"{m.group(1).upper()}:\\{t.subpath}".rstrip("\\") if t.subpath else f"{m.group(1).upper()}:\\"


def nome_share(caminho_local: str) -> str:
    h = hashlib.sha1(caminho_local.lower().rstrip("\\").encode("utf-8")).hexdigest()[:8]
    return f"trilan_ro_{h}$"


def _ps_str(valor: str) -> str:
    """Literal PowerShell entre aspas simples (aspas simples duplicadas); recusa caracteres de controle."""
    if any(ord(c) < 32 for c in valor):
        raise ProvisionamentoErro("Caminho com caracteres inválidos.")
    return "'" + valor.replace("'", "''") + "'"


def montar_script(usuario: str, senha: str, pastas: Dict[str, str]) -> str:
    """Script PowerShell idempotente. `pastas` = {caminho_local: nome_do_share}. Imprime `OK|share|caminho` ou `ERRO|caminho|msg`."""
    linhas = [
        "$ErrorActionPreference = 'Stop'",
        f"$u = {_ps_str(usuario)}",
        f"$p = ConvertTo-SecureString {_ps_str(senha)} -AsPlainText -Force",
        "if (Get-LocalUser -Name $u -ErrorAction SilentlyContinue) { Set-LocalUser -Name $u -Password $p }",
        "else { New-LocalUser -Name $u -Password $p -PasswordNeverExpires -UserMayNotChangePassword "
        "-AccountNeverExpires -Description 'Trilan - leitura de backups' | Out-Null }",
    ]
    for caminho, share in pastas.items():
        linhas += [
            "try {",
            f"  $c = {_ps_str(caminho)}; $s = {_ps_str(share)}",
            "  if (-not (Test-Path -LiteralPath $c -PathType Container)) { throw 'pasta nao existe' }",
            "  & icacls.exe $c /grant ($u + ':(OI)(CI)RX') | Out-Null",
            "  if ($LASTEXITCODE -ne 0) { throw 'icacls falhou' }",
            "  if (Get-SmbShare -Name $s -ErrorAction SilentlyContinue) { Remove-SmbShare -Name $s -Force }",
            "  New-SmbShare -Name $s -Path $c -ReadAccess $u -Description 'Trilan - leitura de backups' | Out-Null",
            "  Write-Output ('OK|' + $s + '|' + $c)",
            "} catch { Write-Output ('ERRO|' + $c + '|' + $_.Exception.Message) }",
        ]
    return "\n".join(linhas)


def _executar_ssh(host: str, porta: int, admin_user: str, admin_senha: str, script: str, timeout: int = 60) -> str:
    import paramiko
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(host, port=porta, username=admin_user, password=admin_senha, timeout=15,
                    banner_timeout=15, auth_timeout=15, look_for_keys=False, allow_agent=False)
        codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        _, out, err = cli.exec_command(f"powershell -NoProfile -NonInteractive -EncodedCommand {codificado}", timeout=timeout)
        saida = out.read().decode("utf-8", errors="ignore")
        codigo = out.channel.recv_exit_status()
        if codigo != 0 and "OK|" not in saida:
            raise ProvisionamentoErro(f"PowerShell terminou com código {codigo}: "
                                      f"{err.read().decode('utf-8', errors='ignore').strip()[:300]}")
        return saida
    except paramiko.AuthenticationException:
        raise ProvisionamentoErro("Usuário/senha de SSH do administrador recusados.")
    except (OSError, paramiko.SSHException) as e:
        raise ProvisionamentoErro(f"Falha de conexão SSH em {host}:{porta}: {e}")
    finally:
        cli.close()


def provisionar(host: str, pastas_origem: List[str], admin_user: str, admin_senha: str,
                ssh_porta: int = 22) -> dict:
    """Cria usuário + shares de leitura. Devolve o registro gravado no cache do host."""
    with _LOCK:
        locais: Dict[str, str] = {}
        for p in pastas_origem:
            local = caminho_local_windows(p, host)
            if local:
                locais[local] = nome_share(local)
        if not locais:
            raise ProvisionamentoErro("Nenhuma pasta de drive (ex.: D:\\pasta) para compartilhar.")

        cache = _ler_cache()
        reg = cache.get(host, {})
        senha = reg.get("senha") or gerar_senha()  # reaproveita a senha para não derrubar acessos em andamento
        saida = _executar_ssh(host, ssh_porta, admin_user, admin_senha,
                              montar_script(USUARIO_LEITURA, senha, locais))
        shares = dict(reg.get("shares", {}))
        erros = []
        for linha in saida.splitlines():
            partes = linha.strip().split("|", 2)
            if len(partes) == 3 and partes[0] == "OK":
                shares[partes[2].lower().rstrip("\\")] = partes[1]
            elif len(partes) == 3 and partes[0] == "ERRO":
                erros.append(f"{partes[1]}: {partes[2]}")
        if not any(c.lower().rstrip("\\") in shares for c in locais):
            raise ProvisionamentoErro("Nenhuma pasta compartilhada: " + "; ".join(erros or [saida.strip()[:200]]))
        for e in erros:
            logging.warning(f"  [SMB/SSH] {host}: {e}")
        novo = {"usuario": USUARIO_LEITURA, "senha": senha, "shares": shares}
        cache[host] = novo
        _gravar_cache(cache)
        logging.info(f"  [SMB/SSH] Usuário de leitura '{USUARIO_LEITURA}' provisionado em {host} ({len(shares)} share(s)).")
        return novo


def _alvo_do_cache(reg: dict, pasta_origem: str, host: str, porta: int) -> Optional[SmbTarget]:
    local = caminho_local_windows(pasta_origem, host)
    if not local:
        return None
    share = reg.get("shares", {}).get(local.lower().rstrip("\\"))
    if not share:
        return None
    t = parse_smb_target(f"\\\\{host}\\{share}", host=host, user=reg["usuario"], password=reg["senha"], port=porta)
    return t


def obter_alvo_leitura(pasta_origem: str, host: str, config_extra: dict, admin_user: Optional[str],
                       admin_senha: Optional[str], forcar: bool = False) -> Tuple[Optional[SmbTarget], str]:
    """
    Devolve (SmbTarget com o usuário de leitura, mensagem). Usa o cache; provisiona por SSH se faltar
    (ou se `forcar`, p.ex. depois de uma falha de autenticação). (None, motivo) se não for possível.
    """
    if not host:
        return None, "Host da máquina do cliente não informado."
    try:
        porta_smb = int(config_extra.get("smb_porta") or 445)
    except (ValueError, TypeError):
        porta_smb = 445
    try:
        porta_ssh = int(config_extra.get("ssh_porta") or 22)
    except (ValueError, TypeError):
        porta_ssh = 22
    try:
        if not forcar:
            alvo = _alvo_do_cache(_ler_cache().get(host, {}), pasta_origem, host, porta_smb)
            if alvo:
                return alvo, "usuário de leitura (cache)"
        if not (admin_user and admin_senha):
            return None, "Faltam usuário/senha de SSH do administrador para criar o usuário de leitura."
        reg = provisionar(host, [pasta_origem], admin_user, admin_senha, porta_ssh)
        alvo = _alvo_do_cache(reg, pasta_origem, host, porta_smb)
        return (alvo, "usuário de leitura criado por SSH") if alvo else (None, "Pasta não compartilhada.")
    except ProvisionamentoErro as e:
        return None, str(e)
    except Exception as e:
        return None, f"Erro ao provisionar acesso de leitura: {e}"


def usa_provisionamento_ssh(config_extra: dict) -> bool:
    """Ligado quando há conta SSH de administrador no cadastro e nenhum usuário SMB explícito."""
    cfg = config_extra or {}
    return bool(cfg.get("ssh_usuario")) and not cfg.get("smb_usuario")


def alvo_por_ssh(pasta_origem: str, host: str, config_extra: dict, forcar: bool = False):
    return obter_alvo_leitura(pasta_origem, host, config_extra, config_extra.get("ssh_usuario"),
                              config_extra.get("ssh_senha"), forcar=forcar)
