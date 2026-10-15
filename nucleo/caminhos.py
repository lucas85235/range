"""Pastas do projeto: todo script acha dados/, resultados/ e a calibração daqui, de onde for chamado."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "dados"
RES = RAIZ / "resultados"
CALIBRACAO = RAIZ / "calibracao.json"
