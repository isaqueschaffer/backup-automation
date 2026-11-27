from dataclasses import dataclass
from typing import Any, Callable, Dict, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class TipoWidget:
    tipo: str
    rotulo: str
    descricao: str
    config_model: Type[BaseModel]
    largura_padrao: int
    altura_padrao: int
    # construir(contexto, config_validada) -> dict serializável em JSON
    construir: Callable[[Any, BaseModel], Dict[str, Any]]


REGISTRO: Dict[str, TipoWidget] = {}


def registrar(tipo_widget: TipoWidget) -> None:
    REGISTRO[tipo_widget.tipo] = tipo_widget
