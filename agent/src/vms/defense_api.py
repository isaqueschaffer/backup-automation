import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class DefenseIAClient:
    """
    Cliente HTTP para a API do Intelbras Defense IA.
    """
    def __init__(self, ip: str, username: str, password: str, port: int = 443):
        # A maioria das APIs do Defense usa HTTPS na porta 443
        protocol = "https" if port == 443 else "http"
        self.base_url = f"{protocol}://{ip}:{port}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        
        # Ignorando avisos de certificado SSL auto-assinado (comum em VMS locais)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session.verify = False

    def login(self) -> bool:
        """
        Realiza a autenticação na API do Defense IA e armazena o token na sessão.
        """
        # TODO: Substituir pelo endpoint correto da documentação da Intelbras
        login_url = f"{self.base_url}/api/system/login" 
        
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = self.session.post(login_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            # TODO: Extrair o token da resposta, ex: data.get("token")
            # self.session.headers.update({"Authorization": f"Bearer {token}"})
            
            logger.info("Login no Defense IA realizado com sucesso.")
            return True
        except Exception as e:
            logger.error(f"Falha ao realizar login no Defense IA: {e}")
            return False

    def get_cameras_status(self) -> List[Dict]:
        """
        Consulta o status de gravação e conexão das câmeras/canais no Defense IA.
        """
        # TODO: Substituir pelo endpoint correto da documentação da Intelbras
        status_url = f"{self.base_url}/api/v2/devices/channels/status"
        
        try:
            response = self.session.get(status_url, timeout=15)
            response.raise_for_status()
            
            # Exemplo de formatação de retorno esperado:
            # [
            #     {"id": "1", "nome": "Cam Estacionamento", "status": "online", "gravando": True},
            #     {"id": "2", "nome": "Cam Recepção", "status": "offline", "gravando": False}
            # ]
            data = response.json()
            
            # TODO: Mapear o JSON de resposta da Intelbras para o nosso formato
            cameras = []
            for item in data.get("channels", []):
                cameras.append({
                    "id": item.get("id"),
                    "nome": item.get("name"),
                    "status": "online" if item.get("isOnline") else "offline",
                    "gravando": item.get("isRecording", False)
                })
            
            return cameras
            
        except Exception as e:
            logger.error(f"Erro ao buscar status das câmeras no Defense IA: {e}")
            return []

    def verificar_integridade(self) -> Dict:
        """
        Fluxo completo para ser chamado pelo Agente.
        """
        if not self.login():
            return {"status": "ERRO", "mensagem": "Falha na autenticação com a API do Defense"}
            
        cameras = self.get_cameras_status()
        
        # Lógica simples: se tem câmeras e alguma está offline ou não gravando
        total = len(cameras)
        com_falha = sum(1 for c in cameras if not c["gravando"] or c["status"] == "offline")
        
        return {
            "status": "ATENCAO" if com_falha > 0 else "OK",
            "total_cameras": total,
            "cameras_com_falha": com_falha,
            "detalhes_cameras": cameras
        }

if __name__ == "__main__":
    # Teste rápido do esqueleto
    client = DefenseIAClient(ip="192.168.1.100", username="admin", password="password")
    print("Tentando login...")
    print(client.verificar_integridade())
