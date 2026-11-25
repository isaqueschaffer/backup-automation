"""Verificações da auditoria de merge (CLAUDE.md) sobre as linhas ADICIONADAS entre dois commits.

Uso: python tools/verificar_regras.py <commit_base> [<commit_final>=HEAD]

- ERRO (falha o CI): segredo nas linhas adicionadas (chave `sk_trilan_`, chave privada, token do GitHub/AWS) ou
  arquivo de credencial/binário grande adicionado ao repositório (ele é espelhado em um público).
- AVISO (não falha; quem faz o merge confere): REGRA-001 (data com fuso no servidor), REGRA-010 (rota sem filtro de
  conta), `verify=False` novo no agente e a senha padrão de câmera em lugar novo.

Saída no formato de anotações do GitHub Actions (`::error file=...,line=...::msg`), legível também no terminal.
"""
import re
import subprocess
import sys

SEGREDOS = [
    (re.compile(r"sk_trilan_[A-Za-z0-9_\-]{20,}"), "chave de API do agente (sk_trilan_...)"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "chave privada"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}"), "token do GitHub"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "chave de acesso AWS"),
]
ARQUIVO_PROIBIDO = re.compile(
    r"(^|/)(CLAUDE\.local\.md|[^/]*\.local\.md|acesso[^/]*\.md|chave api[^/]*\.md|agent\.conf|\.env(\.[^/]*)?|"
    r"id_rsa[^/]*|id_ed25519[^/]*|[^/]*\.pem|[^/]*\.key|[^/]*\.pfx)$", re.IGNORECASE)
EXEMPLOS_PERMITIDOS = re.compile(r"\.example$|agent\.conf\.example$", re.IGNORECASE)
LIMITE_BINARIO = 5 * 1024 * 1024

AVISOS = [
    (re.compile(r"datetime\.now\(|timezone\.utc|DateTime\(timezone=True\)"),
     lambda f: f.startswith("server/api/") and "/tests/" not in f and not f.endswith("services/datas.py"),
     "REGRA-001: datas no servidor são naive em UTC (datetime.utcnow / services.datas.para_utc_naive)"),
    (re.compile(r"verify_admin_token|db\.query\((Customer|Machine|NVR|Backup)\)"),
     lambda f: f.startswith("server/api/routers/"),
     "REGRA-010: rota tem de receber ctx (get_contexto) e filtrar por conta (obter_*/filtrar_por_conta)"),
    (re.compile(r"verify\s*=\s*False"),
     lambda f: f.startswith("agent/") and "/tests/" not in f,
     "verify=False novo: só é aceitável para equipamentos da rede local, nunca para o servidor da Trilan"),
    (re.compile(r"navarro@123"),
     lambda f: "/tests/" not in f and f.endswith(CODIGO) and not f.endswith("verificar_regras.py"),
     "senha padrão de câmera em lugar novo (o repositório é público)"),
]
CODIGO = (".py", ".ts", ".tsx", ".js", ".jsx", ".ps1", ".iss")


def eh_comentario(texto):
    return texto.lstrip().startswith(("#", "//", "*", "/*", "<#"))


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def linhas_adicionadas(base, fim):
    arquivo, linha = None, 0
    for txt in git("diff", "-U0", "--no-color", "--diff-filter=AM", base, fim).splitlines():
        if txt.startswith("+++ "):
            arquivo = txt[6:] if txt.startswith("+++ b/") else None
        elif txt.startswith("@@"):
            m = re.search(r"\+(\d+)", txt)
            linha = int(m.group(1)) if m else 0
        elif txt.startswith("+") and arquivo:
            yield arquivo, linha, txt[1:]
            linha += 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    base = sys.argv[1] if len(sys.argv) > 1 else "HEAD~1"
    fim = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    erros = avisos = 0

    for status_arquivo in git("diff", "--name-status", "--no-renames", "--diff-filter=A", base, fim).splitlines():
        caminho = status_arquivo.split("\t", 1)[-1]
        if ARQUIVO_PROIBIDO.search(caminho) and not EXEMPLOS_PERMITIDOS.search(caminho):
            print(f"::error file={caminho}::arquivo de credencial adicionado ao repositório (espelhado em público)")
            erros += 1
        tamanho = git("cat-file", "-s", f"{fim}:{caminho}").strip()
        if tamanho.isdigit() and int(tamanho) > LIMITE_BINARIO:
            print(f"::error file={caminho}::arquivo de {int(tamanho) // (1024 * 1024)} MB adicionado "
                  f"(binários vão na release, não no git: ADR-008)")
            erros += 1

    for arquivo, n, texto in linhas_adicionadas(base, fim):
        for padrao, nome in SEGREDOS:
            if padrao.search(texto):
                print(f"::error file={arquivo},line={n}::possível segredo ({nome}) em linha adicionada")
                erros += 1
        if eh_comentario(texto):
            continue  # segredos já foram checados acima; regras de código não valem para comentário
        for padrao, aplica, msg in AVISOS:
            if aplica(arquivo) and padrao.search(texto):
                print(f"::warning file={arquivo},line={n}::{msg}")
                avisos += 1

    print(f"Verificação das regras ({base[:12]}..{fim[:12]}): {erros} erro(s), {avisos} aviso(s).")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
