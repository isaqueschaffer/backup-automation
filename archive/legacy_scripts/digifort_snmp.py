"""
Módulo Legado: Receptor de Traps SNMP do Digifort (Porta 162 UDP)
==================================================================
NOTA HISTÓRICA:
Este método foi utilizado nas primeiras versões da automação para monitorar
o status online/offline das câmeras do Digifort recebendo traps SNMP enviadas
pelo próprio software Digifort na porta UDP 162.

OIDs conhecidos do Digifort:
- .1.3.6.1.4.1.33655.1.1.100.2.4 (...\\x64\\x02\\x04): Falha de Comunicação da Câmera (Offline)
- .1.3.6.1.4.1.33655.1.1.100.2.5 (...\\x64\\x02\\x05): Câmera Restaurada (Online)

MOTIVO DA SUBSTITUIÇÃO:
O método baseado em SNMP exigia configuração de traps no Digifort, dependia
da abertura da porta 162 UDP (frequentemente em conflito com o serviço SNMP
Trap nativo do Windows ou outros utilitários) e não garantia checagem ativa
quando o serviço era reiniciado.
Foi substituído pela verificação ativa via Ping ICMP concorrente executado
diretamente pelo Agente Windows em 'agent/src/application/webhook_digifort.py'.
"""

import logging
import datetime
import csv
import io
import os
import socket
import re
import threading

PORTA_SNMP = 162
ARQUIVO_CSV = r"C:\Relatorios_Digifort\quedas_cameras.csv"
ARQUIVO_EXPORT_CAMERAS = ""
DICIONARIO_CAMERAS_NOME = {}
DICIONARIO_CAMERAS_IP = {}
LISTA_CAMERAS_UNICAS = []
ULTIMO_CAMINHO_EXPORT = ""

def normalizar_texto(texto):
    if not texto:
        return ""
    t = re.sub(r'[^a-zA-Z0-9]', ' ', str(texto).lower())
    return ' '.join(t.split())

def ler_linhas_csv(caminho_arquivo):
    encodings_para_tentar = ['utf-8-sig', 'cp1252', 'latin1']
    for enc in encodings_para_tentar:
        try:
            with open(caminho_arquivo, mode='r', encoding=enc) as f:
                content = f.read()
                if '\ufffd' not in content:
                    f_io = io.StringIO(content)
                    reader = csv.DictReader(f_io, delimiter=';')
                    if reader.fieldnames:
                        return list(reader), reader.fieldnames
        except UnicodeDecodeError:
            continue
        except Exception:
            break
            
    with open(caminho_arquivo, mode='r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f, delimiter=';')
        return list(reader), reader.fieldnames or []

def obter_valor_coluna(row, *nomes_possiveis):
    for chave, valor in row.items():
        if not chave:
            continue
        chave_limpa = chave.strip().lstrip('\ufeff').lower()
        for np in nomes_possiveis:
            if np.lower() == chave_limpa:
                return valor.strip() if valor else ''
    for chave, valor in row.items():
        if not chave:
            continue
        chave_limpa = chave.strip().lstrip('\ufeff').lower()
        for np in nomes_possiveis:
            if np.lower() in chave_limpa:
                return valor.strip() if valor else ''
    return ''

def carregar_dicionario_cameras(caminho_arquivo):
    dicionario_nome = {}
    dicionario_ip = {}
    lista_unicas = []
    
    if os.path.isfile(caminho_arquivo):
        try:
            linhas, colunas = ler_linhas_csv(caminho_arquivo)
            is_novo_formato = any(k in [c.lower() for c in colunas] for k in ['endereço', 'endereco', 'nome', 'ip'])
            
            for index, row in enumerate(linhas, start=1):
                if is_novo_formato:
                    ip = obter_valor_coluna(row, 'endereço', 'endereco', 'ip')
                    nome = obter_valor_coluna(row, 'nome')
                    descricao = obter_valor_coluna(row, 'descrição', 'descricao')
                else:
                    ip = ''
                    nome = f"{index:02d}"
                    descricao = obter_valor_coluna(row, 'descrição', 'descricao')
                
                if nome.isdigit() and descricao:
                    nome_exibicao = descricao
                elif descricao and len(descricao) > len(nome):
                    nome_exibicao = descricao
                else:
                    nome_exibicao = nome or descricao or f"Camera {index:02d}"
                    
                info = {
                    'Nome': nome_exibicao,
                    'NomeCurto': nome,
                    'Descricao': descricao,
                    'IP': ip
                }
                lista_unicas.append(info)
                
                if nome:
                    dicionario_nome[nome] = info
                    dicionario_nome[nome.lower()] = info
                    dicionario_nome[normalizar_texto(nome)] = info
                if descricao:
                    dicionario_nome[descricao] = info
                    dicionario_nome[descricao.lower()] = info
                    dicionario_nome[normalizar_texto(descricao)] = info
                    
                num_str = f"{index:02d}"
                dicionario_nome[num_str] = info
                dicionario_nome[str(index)] = info
                
                if ip:
                    dicionario_ip[ip] = info
                    
            logging.info(f"[OK] {len(lista_unicas)} cameras carregadas do arquivo {caminho_arquivo}")
        except Exception as e:
            logging.error(f"[ERRO] ao ler {caminho_arquivo}: {e}")
    else:
        logging.warning(f"[AVISO] Arquivo de exportacao '{caminho_arquivo}' nao encontrado.")
        
    return dicionario_nome, dicionario_ip, lista_unicas

def registrar_queda(nome_camera, nome_evento):
    agora = datetime.datetime.now()
    data = agora.strftime("%Y-%m-%d")
    hora = agora.strftime("%H:%M:%S")
    
    pasta = os.path.dirname(ARQUIVO_CSV)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
        
    arquivo_existe = os.path.isfile(ARQUIVO_CSV)
    
    with open(ARQUIVO_CSV, mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file, delimiter=';')
        if not arquivo_existe:
            writer.writerow(['Data', 'Hora', 'Camera', 'Evento'])
            
        writer.writerow([data, hora, nome_camera, nome_evento])

# =============== SNIFFER SNMP ===============
sniffer_socket = None

def extrair_textos_snmp(dados: bytes) -> list:
    """Extrai strings legíveis do payload SNMP via ASN.1 OCTET STRING (0x04) e varredura ampla (UTF-8/Latin1)."""
    textos = []
    i = 0
    n = len(dados)
    while i < n - 1:
        if dados[i] == 0x04:  # OCTET STRING tag
            comp = dados[i + 1]
            offset = i + 2
            if comp & 0x80:
                num_bytes = comp & 0x7F
                if offset + num_bytes <= n:
                    comp = int.from_bytes(dados[offset:offset + num_bytes], 'big')
                    offset += num_bytes
                else:
                    i += 1
                    continue
            if offset + comp <= n and comp > 0:
                pedaco = dados[offset:offset + comp]
                for enc in ('utf-8', 'latin1', 'cp1252'):
                    try:
                        dec = pedaco.decode(enc).strip()
                        if dec and any(c.isalnum() for c in dec) and dec not in textos:
                            textos.append(dec)
                        break
                    except Exception:
                        continue
                i = offset + comp
                continue
        i += 1

    for pedaco in re.findall(b'[\x20-\x7e\xa0-\xff]{2,}', dados):
        for enc in ('utf-8', 'latin1', 'cp1252'):
            try:
                dec = pedaco.decode(enc).strip()
                if dec and any(c.isalnum() for c in dec) and dec not in textos:
                    textos.append(dec)
                break
            except Exception:
                continue

    return textos

def detectar_status_evento(dados: bytes, textos: list) -> str:
    """Detecta se o evento é Falha de Comunicação ou Retorno (Online), via OID ou palavras-chave."""
    if b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x04' in dados:
        return "Falha de Comunicacao"
    if b'\x06\x0d\x2b\x06\x01\x04\x01\x82\xf7\x04\x01\x01\x64\x02\x05' in dados:
        return "Camera Restaurada"

    texto_geral = " ".join(textos).lower()
    palavras_falha = ("falha", "failure", "perda", "loss", "offline", "desconectad", "down", "sem sinal", "queda")
    palavras_restaurada = ("restaurad", "restored", "online", "conectad", "up", "normal", "recuperad")

    for p in palavras_falha:
        if p in texto_geral:
            return "Falha de Comunicacao"
    for p in palavras_restaurada:
        if p in texto_geral:
            return "Camera Restaurada"

    return "Outro Evento"

def rodar_sniffer_snmp():
    global sniffer_socket
    sniffer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sniffer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        sniffer_socket.bind(('0.0.0.0', PORTA_SNMP))
        logging.info(f"[OK] Sniffer SNMP rodando na porta {PORTA_SNMP}...")
    except Exception as e:
        logging.error(
            f"[ERRO] ao iniciar Sniffer SNMP na porta {PORTA_SNMP}: {e}. "
            f"Verifique se a porta 162 UDP não está sendo usada por outro software."
        )
        return

    while True:
        try:
            dados, endereco = sniffer_socket.recvfrom(4096)
        except Exception:
            break

        logging.info(f"[SNMP] Pacote UDP de {len(dados)} bytes recebido de {endereco}")
        textos = extrair_textos_snmp(dados)
        status_encontrado = detectar_status_evento(dados, textos)

        camera_identificada_nome = None

        for texto_limpo in textos:
            if texto_limpo.endswith('0') and len(texto_limpo) > 1 and texto_limpo[:-1] in DICIONARIO_CAMERAS_NOME:
                texto_limpo = texto_limpo[:-1]

            ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', texto_limpo)
            if ip_match and ip_match.group(0) in DICIONARIO_CAMERAS_IP:
                camera_identificada_nome = DICIONARIO_CAMERAS_IP[ip_match.group(0)]['Nome']
                break

            texto_norm = normalizar_texto(texto_limpo)
            for nome, info in DICIONARIO_CAMERAS_NOME.items():
                if not str(nome).isdigit() and (nome.lower() == texto_limpo.lower() or normalizar_texto(nome) == texto_norm):
                    camera_identificada_nome = info['Nome']
                    break
            if camera_identificada_nome:
                break

        if not camera_identificada_nome:
            palavras_ignorar = {'public', 'falha de comunicacao', 'camera restaurada', 'outro evento', 'digifort', 'enterprise'}
            for t in textos:
                tl = t.lower()
                if len(t) >= 2 and tl not in palavras_ignorar and not any(k in tl for k in ('falha', 'restaurad', 'offline', 'online')):
                    camera_identificada_nome = t
                    break

        if camera_identificada_nome and status_encontrado != "Outro Evento":
            registrar_queda(camera_identificada_nome, status_encontrado)
            logging.info(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] SNMP TRAP REGISTRADA: {camera_identificada_nome} | {status_encontrado}")
        else:
            logging.warning(
                f"[SNMP] Trap recebida mas não gravada. Status: '{status_encontrado}', "
                f"Camera: '{camera_identificada_nome}'. Textos encontrados: {textos}"
            )

if __name__ == '__main__':
    print("="*60)
    print("  AGENTE DIGIFORT (SNMP LEGADO) - TRILAN NVR BACKUP")
    print("="*60)
    rodar_sniffer_snmp()
