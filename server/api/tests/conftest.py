"""Configuração comum dos testes da API (API-16, auditoria de 25/11/2026).

Põe `server/api` no caminho de importação e define as variáveis mínimas com `setdefault`, ANTES de qualquer teste
importar `config`: o `Settings` é criado uma vez, no primeiro import, e falharia sem elas. `setdefault` não
sobrescreve o que o ambiente já define (o teste de isolamento roda no container contra o PostgreSQL local e usa o
`DATABASE_URL` de lá). Os arquivos de teste antigos ainda repetem esse preparo; podem ir perdendo-o aos poucos.
"""
import os
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

os.environ.setdefault("SECRET_KEY", "test_secret_key_1234567890123456789012")
os.environ.setdefault("FERNET_KEY", "dHJpbGFuLWNoYXZlLWRlLXRlc3RlLTMyLWJ5dGVzISE=")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ADMIN_PASSWORD", "senha_de_teste")

# No Windows a pasta temporária pode vir no nome curto 8.3 (C:\Users\USURIO~2\...), enquanto o código resolve o
# caminho para o nome longo (C:\Users\Usuário\...): os testes de armazenamento comparavam os dois e falhavam só ali.
import tempfile  # noqa: E402

tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())
