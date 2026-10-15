"""Apurações sintéticas do 2º turno, geradas seção a seção a partir do 1º turno.

Cada cenário sorteia:
  - transferência de votos de cada categoria do 1º turno (F1, L1, cada outro candidato,
    brancos/nulos, abstenção) para F e L no 2º;
  - desvios na fatia de F (escala logit) por região, UF, município e seção, com tamanhos
    entre os medidos em 2022 (uniforme) e 2018 (heterogêneo);
  - desvios na taxa de válidos por eleitor (comparecimento) por UF e município;
  - um deslocamento global que leva a margem nacional exatamente ao valor pedido;
  - a hora de chegada de cada seção: a distribuição de horários do 2º turno de 2022 em cada
    município, ordenada por uma mistura da ordem do 1º turno (correlação rho) com sorteio,
    mais ritmo e atraso aleatórios por UF.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize, special, stats

from dados_eleicao import ELEICOES
from modelo import REGIAO


@dataclass
class Cenario:
    margem: float                 # margem final pedida (pp, F - L)
    sd_reg: float = 0.04          # logit da fatia de F
    sd_uf: float = 0.04
    sd_mun: float = 0.05
    sd_sec: float = 0.03
    sd_val_uf: float = 0.02       # log dos válidos por eleitor
    sd_val_mun: float = 0.03
    grad_ordem: float = 0.0       # swing logit da 1ª para a última seção a chegar no município
    rho_ordem: float = 0.45       # correlação (normal) da ordem 1T x 2T dentro do município
    ritmo_uf: float = 0.10        # dp do log do fator de ritmo por UF
    desloc_uf: float = 5.0        # dp do atraso por UF (min)
    desloc_mun: float = 3.0       # dp do atraso por município (min)
    molde_1t: bool = False        # horários por município: False = 2º turno de 2022;
                                  # True = 1º turno do próprio ano levado ao ritmo do 2T de 2022


def sortear_cenario(margem: float, rng: np.random.Generator) -> Cenario:
    """Heterogeneidade entre a de 2022 (0) e a de 2018 (1), sorteada por cenário."""
    h = rng.uniform(0, 1)
    lerp = lambda a, b: a + h * (b - a)  # noqa: E731
    return Cenario(margem=margem, sd_reg=lerp(0.02, 0.07), sd_uf=lerp(0.02, 0.06),
                   sd_mun=lerp(0.03, 0.07), sd_sec=lerp(0.0, 0.06),
                   sd_val_uf=rng.uniform(0.01, 0.03), sd_val_mun=rng.uniform(0.02, 0.04),
                   grad_ordem=rng.normal(0, 0.03), rho_ordem=rng.uniform(0.3, 0.6),
                   ritmo_uf=rng.uniform(0.05, 0.15), desloc_uf=rng.uniform(2, 8),
                   desloc_mun=rng.uniform(2, 8), molde_1t=bool(rng.random() < 0.5))


def categorias(sec1: pd.DataFrame, ano: int) -> tuple[np.ndarray, list[str]]:
    """Votos do 1º turno por seção nas categorias usadas na transferência."""
    e = ELEICOES[ano]
    vcols = [c for c in sec1.columns if c.startswith("v") and c[1:].isdigit()]
    tot = sec1[vcols].sum()
    validos = sec1["V"].sum()
    outros = [c for c in vcols if int(c[1:]) not in (e["F"], e["L"], 95, 96) and tot[c] / validos > 0.01]
    cols = [sec1["F"], sec1["L"]] + [sec1[c] for c in outros] + \
           [sec1["O"] - sec1[outros].sum(axis=1), sec1["BN"], np.maximum(sec1["aptos"] - sec1["C"], 0)]
    return np.column_stack([np.asarray(c, float) for c in cols]), ["F1", "L1"] + outros + ["Orest", "BN1", "ABS1"]


def sortear_transferencia(nomes: list[str], rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Probabilidade de cada categoria do 1º turno votar F e L no 2º."""
    pF, pL = [], []
    for n in nomes:
        if n == "F1":
            f, l_ = rng.uniform(0.93, 0.98), rng.uniform(0.005, 0.02)
        elif n == "L1":
            f, l_ = rng.uniform(0.005, 0.02), rng.uniform(0.93, 0.98)
        elif n == "BN1":
            f, l_ = rng.uniform(0.05, 0.25), rng.uniform(0.05, 0.25)
        elif n == "ABS1":
            f, l_ = rng.uniform(0.01, 0.06), rng.uniform(0.01, 0.06)
        else:  # outros candidatos: vão em parte para cada lado, parte anula/abstém
            tot = rng.uniform(0.75, 0.92)
            f = tot * rng.uniform(0.3, 0.8)
            l_ = tot - f
        pF.append(f)
        pL.append(l_)
    return np.array(pF), np.array(pL)


def _efeitos(chaves: np.ndarray, sd: float, rng: np.random.Generator) -> np.ndarray:
    u, inv = np.unique(chaves, return_inverse=True)
    return rng.normal(0, sd, len(u))[inv]


def gerar_votos(sec1: pd.DataFrame, ano: int, cen: Cenario, rng: np.random.Generator,
                rank2: np.ndarray | None = None) -> pd.DataFrame:
    """Votos sintéticos do 2º turno por seção (F, L, C, aptos), com margem = cen.margem."""
    X, nomes = categorias(sec1, ano)
    pF, pL = sortear_transferencia(nomes, rng)
    Fe, Le = X @ pF, X @ pL
    Ve = Fe + Le
    uf = sec1["uf"].to_numpy()
    reg = np.array([REGIAO[u] for u in uf])
    mun = sec1["cd_mun"].to_numpy()
    d = (_efeitos(reg, cen.sd_reg, rng) + _efeitos(uf, cen.sd_uf, rng) + _efeitos(mun, cen.sd_mun, rng)
         + rng.normal(0, cen.sd_sec, len(sec1)))
    if rank2 is not None:
        d = d + cen.grad_ordem * (rank2 - 0.5)
    lv = _efeitos(uf, cen.sd_val_uf, rng) + _efeitos(mun, cen.sd_val_mun, rng)
    V = np.minimum(Ve * np.exp(lv), sec1["aptos"].to_numpy(float))
    base_logit = special.logit(np.clip(Fe / np.maximum(Ve, 1e-9), 1e-4, 1 - 1e-4)) + d
    alvo = cen.margem / 100

    def erro(g):
        s = special.expit(base_logit + g)
        return (np.sum(V * s) - np.sum(V * (1 - s))) / np.sum(V) - alvo

    g = optimize.brentq(erro, -5, 5)
    s = special.expit(base_logit + g)
    Vi = np.round(V).astype(np.int64)
    F = rng.binomial(Vi, s)
    L = Vi - F
    BN = rng.binomial(np.maximum(sec1["aptos"].to_numpy(np.int64) - Vi, 0), 0.05)
    out = sec1[["uf", "cd_mun", "zona", "secao", "nm_mun", "aptos"]].copy()
    out["F"], out["L"], out["BN"] = F, L, BN
    out["V"] = F + L
    out["O"] = 0
    out["C"] = out["V"] + BN
    return out


def tempos_2t(sec1: pd.DataFrame, ref2t: pd.DataFrame, cen: Cenario, rng: np.random.Generator
              ) -> tuple[np.ndarray, np.ndarray]:
    """Hora de chegada no 2º turno de cada seção de `sec1` e sua ordem dentro do município.

    Distribuição de horários de cada município: a do 2º turno de referência (2022) ou, com
    cen.molde_1t, a do 1º turno do próprio ano no ritmo do 2º de referência. A ordem das seções
    dentro do município mistura a ordem do 1º turno (rho) com sorteio.
    """
    mun = sec1["cd_mun"].to_numpy()
    t1 = sec1["t"].to_numpy(float)
    t1 = np.where(np.isnan(t1), np.nanmedian(t1), t1)
    df = pd.DataFrame({"mun": mun, "t1": t1 + rng.uniform(0, 1e-3, len(t1))})
    r1 = df.groupby("mun")["t1"].rank(pct=True).to_numpy()
    n_m = df.groupby("mun")["t1"].transform("size").to_numpy()
    z1 = stats.norm.ppf(np.clip(r1 - 0.5 / n_m, 1e-6, 1 - 1e-6))
    z2 = cen.rho_ordem * z1 + np.sqrt(1 - cen.rho_ordem ** 2) * rng.normal(size=len(z1))
    df["z2"] = z2
    q = ((df.groupby("mun")["z2"].rank(method="first").to_numpy() - 0.5) / n_m)
    ref = ref2t[["uf", "cd_mun", "t"]].dropna()
    if cen.molde_1t:
        # molde = horários do 1º turno do próprio ano, levados (por quantil nacional) ao ritmo
        # do 2º turno de referência; a ordem dentro do município sai da cópula (q)
        qn = pd.Series(t1).rank(pct=True).to_numpy()
        molde = np.quantile(ref["t"].to_numpy(), np.clip(qn, 0, 1))
        dfm = pd.DataFrame({"mun": mun, "molde": molde}).sort_values(["mun", "molde"])
        nomes, ini, tam = np.unique(dfm["mun"].to_numpy(), return_index=True, return_counts=True)
        idx = pd.Index(nomes).get_indexer(mun)
        pos = ini[idx] + np.minimum((q * tam[idx]).astype(int), tam[idx] - 1)
        t2 = dfm["molde"].to_numpy()[pos]
    else:
        # distribuição de horários do 2º turno de referência por município (fallback: UF)
        t2 = np.full(len(sec1), np.nan)
        for chave_ref, chave_alvo in (("cd_mun", mun), ("uf", sec1["uf"].to_numpy())):
            pend = np.isnan(t2)
            if not pend.any():
                break
            r = ref.sort_values([chave_ref, "t"])
            nomes, ini, tam = np.unique(r[chave_ref].to_numpy(), return_index=True, return_counts=True)
            idx = pd.Index(nomes).get_indexer(chave_alvo[pend])
            ok = idx >= 0
            pos = ini[idx[ok]] + np.minimum((q[pend][ok] * tam[idx[ok]]).astype(int), tam[idx[ok]] - 1)
            sub = np.flatnonzero(pend)[ok]
            t2[sub] = r["t"].to_numpy()[pos]
        t2 = np.where(np.isnan(t2), np.nanmedian(ref["t"]), t2)
    uf = sec1["uf"].to_numpy()
    fator = np.exp(_efeitos(uf, cen.ritmo_uf, rng))
    t2 = np.maximum(t2, 0) * fator + _efeitos(uf, cen.desloc_uf, rng) + _efeitos(mun, cen.desloc_mun, rng)
    return t2, q


def gerar_apuracao(sec1: pd.DataFrame, ano: int, ref2t: pd.DataFrame, cen: Cenario,
                   rng: np.random.Generator) -> pd.DataFrame:
    """Seções sintéticas do 2º turno com hora de chegada (coluna t)."""
    t2, rank2 = tempos_2t(sec1, ref2t, cen, rng)
    out = gerar_votos(sec1, ano, cen, rng, rank2=rank2)
    out["t"] = t2
    return out
