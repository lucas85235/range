"""Tabelas padronizadas por seção e por município das eleições presidenciais.

Convenção: 'F' é o candidato de direita do 2º turno e 'L' o do PT.
  2014: Aécio (45) x Dilma (13)       2018: Bolsonaro (17) x Haddad (13)
  2022: Bolsonaro (22) x Lula (13)    2026: Flávio (22) x Lula (13)
Margem = (F - L) / (F + L) * 100: pontos percentuais dos votos válidos do 2º turno, positiva
quando F ganha (a regra da Polymarket usa o valor absoluto).

Fontes (ver baixar_bu.py e baixar_secao.py):
  bu_{ano}_{t}t.parquet     Boletim de Urna: tem aptos e, em 2022/2026, a hora de chegada.
  secao_{ano}_{t}t.parquet  Votação por seção (só votos).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DADOS = Path(__file__).resolve().parent / "dados"
ELEICOES = {
    2014: dict(F=45, L=13, dia1="2014-10-05", dia2="2014-10-26"),
    2018: dict(F=17, L=13, dia1="2018-10-07", dia2="2018-10-28"),
    2022: dict(F=22, L=13, dia1="2022-10-02", dia2="2022-10-30"),
    2026: dict(F=22, L=13, dia1="2026-10-04", dia2="2026-10-25"),
}
BRANCO, NULO = 95, 96
CHAVE = ["uf", "cd_mun", "zona", "secao"]


def _numeros(df: pd.DataFrame) -> dict[int, str]:
    return {int(c[1:]): c for c in df.columns if c.startswith("v") and c[1:].isdigit()}


def secoes(ano: int, turno: int, fonte: str = "auto") -> pd.DataFrame:
    """Uma linha por seção, colunas padronizadas.

    F, L: votos dos dois candidatos do 2º turno. O: demais nominais. BN: brancos + nulos.
    V = F + L + O (válidos). C = comparecimento (todos os votos para Presidente).
    aptos: eleitores aptos (só no BU). t: minutos após as 17h de Brasília do dia da
    votação em que o BU chegou ao TSE (NaN sem hora). Colunas v<n> (votos por número) são
    mantidas para o 1º turno.
    """
    bu, sc = DADOS / f"bu_{ano}_{turno}t.parquet", DADOS / f"secao_{ano}_{turno}t.parquet"
    if fonte == "auto":
        fonte = "bu" if bu.exists() else "secao"
    df = pd.read_parquet(bu if fonte == "bu" else sc)
    e = ELEICOES[ano]
    nums = _numeros(df)
    nominais = [c for n, c in nums.items() if n not in (BRANCO, NULO)]
    out = df[CHAVE + ["nm_mun"]].copy()
    out["F"] = df[nums[e["F"]]]
    out["L"] = df[nums[e["L"]]]
    out["V"] = df[nominais].sum(axis=1)
    out["O"] = out["V"] - out["F"] - out["L"]
    out["BN"] = sum(df[nums[n]] for n in (BRANCO, NULO) if n in nums)
    out["C"] = out["V"] + out["BN"]
    out["aptos"] = df["aptos"] if "aptos" in df.columns else np.nan
    if "dt_bu" in df.columns and df["dt_bu"].notna().mean() > 0.9:
        dia = e["dia1"] if turno == 1 else e["dia2"]
        out["t"] = (df["dt_bu"] - pd.Timestamp(f"{dia} 17:00")).dt.total_seconds() / 60
    else:
        out["t"] = np.nan
    if turno == 1:
        for n, c in nums.items():
            out[c] = df[c]
    return out


def municipios(sec: pd.DataFrame) -> pd.DataFrame:
    """Soma as seções por município (cd_mun é único no país; ZZ = exterior)."""
    num = [c for c in sec.columns if c in ("F", "L", "V", "O", "BN", "C", "aptos")
           or (c.startswith("v") and c[1:].isdigit())]
    g = sec.groupby("cd_mun")
    m = g[num].sum(min_count=1)
    m["uf"] = g["uf"].first()
    m["nm_mun"] = g["nm_mun"].first()
    m["nsec"] = g.size()
    return m


def margem(F, L) -> float:
    return float((np.sum(F) - np.sum(L)) / (np.sum(F) + np.sum(L)) * 100)


def base_1t(ano: int) -> pd.DataFrame:
    """Linha de base por município a partir do 1º turno do mesmo ano."""
    return base_turno(ano, 1)


def base_turno(ano: int, turno: int, fonte: str = "auto") -> pd.DataFrame:
    """Linha de base por município a partir de um turno já apurado.

    Colunas: uf, F1, L1, O1, BN1, V1, C1 e a parte de cada outro candidato relevante
    (o<n> = votos do candidato n), além de aptos1 quando há BU. O sufixo 1 indica "base",
    mesmo quando a base é um 2º turno (testes no sentido inverso).
    """
    m = municipios(secoes(ano, turno, fonte))
    e = ELEICOES[ano]
    out = pd.DataFrame({"uf": m["uf"], "nm_mun": m["nm_mun"], "F1": m["F"], "L1": m["L"],
                        "O1": m["O"], "BN1": m["BN"], "V1": m["V"], "C1": m["C"],
                        "aptos1": m["aptos"]})
    tot = {c: m[c].sum() for c in m.columns if c.startswith("v") and c[1:].isdigit()}
    validos = m["V"].sum()
    for c, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        n = int(c[1:])
        if n in (e["F"], e["L"], BRANCO, NULO) or v / validos < 0.01:
            continue
        out[f"o{n}"] = m[c]  # outros com pelo menos 1% dos válidos
    return out
