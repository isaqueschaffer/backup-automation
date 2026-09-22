# -*- coding: utf-8 -*-

import os
import glob
import datetime
import re

# ============================================================
# CONFIGURACAO
# ============================================================

# Caminho padrão onde os logs do Digifort costumam ficar.
# Você deve ajustar este caminho para o caminho real no servidor do cliente.
PASTA_LOGS_DIGIFORT = r"C:\Program Files\Digifort\Digifort Server\Logs"

# Se quiser salvar um relatório diário de status, defina a pasta aqui.
# Exemplo: pasta do OneDrive do cliente para relatórios
PASTA_RELATORIOS = r"C:\Users\Helena\OneDrive - Trilan\Relatorios_Digifort"

# Palavras que indicam que uma câmera caiu ou parou de gravar
PALAVRAS_CRITICAS = [
    "desconectada", 
    "perdido", 
    "sinal de vídeo perdido",
    "falha", 
    "erro",
    "offline"
]

# Códigos de log do Digifort que são NORMAIS e devemos ignorar
# COD:1008 = Limpeza normal de disco (apagando vídeos antigos)
CODIGOS_IGNORAR = ["cod:1008"]

# ============================================================
# FUNCOES DE LEITURA E ALERTA
# ============================================================

def obter_log_do_dia():
    """Busca o arquivo de log do dia atual na pasta do Digifort."""
    if not os.path.isdir(PASTA_LOGS_DIGIFORT):
        return None

    # Procura todos os arquivos .txt ou .log na pasta
    arquivos = glob.glob(os.path.join(PASTA_LOGS_DIGIFORT, "*.txt"))
    arquivos.extend(glob.glob(os.path.join(PASTA_LOGS_DIGIFORT, "*.log")))
    
    if not arquivos:
        return None
    
    # Retorna o arquivo modificado mais recentemente (o log de hoje)
    arquivo_mais_recente = max(arquivos, key=os.path.getmtime)
    return arquivo_mais_recente

def extrair_nome_camera(linha):
    """
    Tenta extrair o nome da câmera da linha de log.
    Exemplo de linha: ... da câmera PORTARIA foi desconectada.
    """
    match = re.search(r'(câmera|camera)\s+(.*?)\s+(foi|apagado|desconectada|perdido)', linha, re.IGNORECASE)
    if match:
        return match.group(2).strip()
    return "Câmera Desconhecida"

def analisar_logs():
    """Lê o log do dia e procura por falhas nas câmeras."""
    arquivo_log = obter_log_do_dia()
    
    if not arquivo_log:
        print(f"[!] Não foi possível encontrar a pasta ou os arquivos de log do Digifort em: {PASTA_LOGS_DIGIFORT}")
        print("Por favor, verifique se o caminho da PASTA_LOGS_DIGIFORT está correto no script.")
        return

    print(f"[*] Analisando o log de hoje: {os.path.basename(arquivo_log)}\n")

    alertas_encontrados = []
    cameras_com_problema = set()

    try:
        # Lê o log com tratamento de erros de codificação de caracteres
        with open(arquivo_log, 'r', encoding='utf-8', errors='ignore') as f:
            for linha in f:
                linha_lower = linha.lower()
                
                # Pula linhas de operação normal (ex: limpeza de disco COD:1008)
                if any(cod in linha_lower for cod in CODIGOS_IGNORAR):
                    continue
                    
                # Checa se alguma palavra crítica está na linha
                if any(palavra in linha_lower for palavra in PALAVRAS_CRITICAS):
                    # Confirma se a linha se refere a uma câmera (e não a um erro de e-mail, por exemplo)
                    if "câmera" in linha_lower or "camera" in linha_lower or "vídeo" in linha_lower:
                        linha_limpa = linha.strip()
                        alertas_encontrados.append(linha_limpa)
                        
                        nome_cam = extrair_nome_camera(linha_limpa)
                        cameras_com_problema.add(nome_cam)

    except Exception as e:
        print(f"[Erro] Falha ao ler o arquivo de log: {e}")
        return

    gerar_relatorio(alertas_encontrados, cameras_com_problema)


def gerar_relatorio(alertas, cameras):
    """Gera um pequeno relatório de texto ou imprime na tela."""
    agora = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    
    print("==================================================")
    print(f"RELATÓRIO DE STATUS DAS CÂMERAS - {agora}")
    print("==================================================\n")

    if not alertas:
        resultado = "✅ STATUS OK: Todas as câmeras parecem estar gravando normalmente e sem quedas registradas hoje."
        print(resultado)
    else:
        resultado = "🚨 ALERTA: Foram detectadas quedas ou erros de gravação em algumas câmeras!\n\n"
        resultado += f"Câmeras afetadas detectadas: {', '.join(cameras)}\n\n"
        resultado += "Últimos registros de erro no log:\n"
        
        # Mostra os 10 últimos erros para não poluir muito
        for alerta in alertas[-10:]:
            resultado += f"- {alerta}\n"
            
        print(resultado)

    # Opcional: Salvar esse resultado num arquivo .txt dentro do OneDrive do cliente
    # para que a matriz possa ver o status remotamente
    try:
        if not os.path.exists(PASTA_RELATORIOS):
            os.makedirs(PASTA_RELATORIOS)
            
        arquivo_saida = os.path.join(PASTA_RELATORIOS, f"Status_Digifort_{datetime.datetime.now().strftime('%Y%m%d')}.txt")
        with open(arquivo_saida, 'w', encoding='utf-8') as f_out:
            f_out.write(resultado)
        print(f"\n[Info] Relatório salvo em: {arquivo_saida}")
    except Exception as e:
        # Se a pasta do OneDrive não existir ou falhar, ignora e segue a vida
        pass

if __name__ == "__main__":
    analisar_logs()
