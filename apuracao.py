"""Reconstrói a apuração: o que o TSE mostraria, por município, a cada minuto.

Uma "apuração" é um dicionário com:
  t      grade de tempos (minutos após as 17h de Brasília)
  F, L, C, aptos, nsec   arrays (T, M): acumulado de cada município até cada tempo
  tot    os mesmos totais no fim da apuração, arrays (M)
A ordem das colunas é a de `munis` (Index de cd_mun).

Horários: reais (DT_BU_RECEBIDO, 2022 e 2026) ou sorteados a partir de uma apuração de
referência (tempos_sorteados), para eleições sem hora no BU e para simulações.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COLS = ["F", "L", "C", "aptos"]


def apurar(sec: pd.DataFrame, munis: pd.Index, tempos: np.ndarray, t: np.ndarray | None = None) -> dict:
    """Acumula as seções por município na grade `tempos`; `t` sobrescreve sec['t']."""
    t = sec["t"].to_numpy(float) if t is None else np.asarray(t, float)
    j = munis.get_indexer(sec["cd_mun"])
    if (j < 0).any():
        raise ValueError(f"{(j < 0).sum()} seções de municípios fora de `munis`")
    T, M = len(tempos), len(munis)
    k = np.searchsorted(tempos, t, side="left")  # entra no primeiro tempo >= t
    idx = k * M + j
    out = {"t": np.asarray(tempos, float)}
    for c in COLS + ["nsec"]:
        w = np.ones(len(sec)) if c == "nsec" else sec[c].to_numpy(float)
        a = np.bincount(idx, weights=w, minlength=(T + 1) * M).reshape(T + 1, M)
        out[c] = np.cumsum(a, axis=0)[:T]
    out["tot"] = {c: np.bincount(j, weights=(np.ones(len(sec)) if c == "nsec" else sec[c].to_numpy(float)),
                                 minlength=M) for c in COLS + ["nsec"]}
    return out


def foto(ap: dict, k: int) -> dict:
    """Retrato da apuração no índice de tempo k (o que o TSE mostraria)."""
    return {c: ap[c][k] for c in COLS + ["nsec"]} | {"t": ap["t"][k]}


def tempos_sorteados(alvo: pd.DataFrame, ref: pd.DataFrame, rng: np.random.Generator,
                     dp_uf: float = 0.0, dp_mun: float = 0.0, escala_uf: float = 0.0) -> np.ndarray:
    """Sorteia a hora de chegada de cada seção de `alvo` copiando a apuração `ref`.

    Para cada seção do alvo, sorteia uma hora entre as seções de `ref` da mesma zona do
    mesmo município; sem zona, do município; sem município, da UF. Ruídos opcionais:
    deslocamento por UF (dp_uf minutos) e por município (dp_mun), e um fator de ritmo por UF
    (t * exp(N(0, escala_uf))), para gerar ordens diferentes da referência.
    """
    ref = ref[["uf", "cd_mun", "zona", "t"]].dropna(subset=["t"])
    t = np.full(len(alvo), np.nan)
    pendente = np.ones(len(alvo), bool)
    for chave in (["cd_mun", "zona"], ["cd_mun"], ["uf"]):
        if not pendente.any():
            break
        r = ref.sort_values(chave)
        grupos = r.groupby(chave, sort=False)
        ini = grupos.cumcount().to_numpy() == 0
        pos = np.flatnonzero(ini)
        chaves = pd.MultiIndex.from_frame(r.loc[ini, chave]) if len(chave) > 1 else pd.Index(r.loc[ini, chave[0]])
        tam = np.diff(np.append(pos, len(r)))
        a = alvo.loc[pendente, chave]
        ka = pd.MultiIndex.from_frame(a) if len(chave) > 1 else pd.Index(a[chave[0]])
        g = chaves.get_indexer(ka)
        ok = g >= 0
        u = rng.random(ok.sum())
        sorteio = pos[g[ok]] + np.floor(u * tam[g[ok]]).astype(int)
        idx_pend = np.flatnonzero(pendente)
        t[idx_pend[ok]] = r["t"].to_numpy()[sorteio]
        pendente[idx_pend[ok]] = False
    t[pendente] = np.nanmedian(ref["t"])
    if dp_uf or escala_uf:
        ufs = pd.Index(sorted(alvo["uf"].unique()))
        iu = ufs.get_indexer(alvo["uf"])
        t = t * np.exp(rng.normal(0, escala_uf, len(ufs)))[iu] + rng.normal(0, dp_uf, len(ufs))[iu]
    if dp_mun:
        mus = pd.Index(alvo["cd_mun"].unique())
        t = t + rng.normal(0, dp_mun, len(mus))[mus.get_indexer(alvo["cd_mun"])]
    return t
