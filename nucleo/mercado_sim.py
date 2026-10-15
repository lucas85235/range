"""Mercado simulado: o preço de cada faixa durante uma noite sintética.

Nas simulações não existe preço de mercado. O preço é modelado como uma mistura entre o preço
de hoje (antes da apuração) e a chance que o modelo dá naquele minuto:
  preço = (1 - λ) * preço de hoje + λ * chance do modelo,  λ = 1 - exp(-(t - t0) / τ) depois de t0.
Três ritmos de mercado:
  "como em 4/10": t0 = 30 min, τ = 30 min (na noite real do 1º turno o mercado tinha andado
                  ~60% do caminho às 17h45 e ~90% às 19h);
  "mais esperto":  t0 = 10 min, τ = 15 min;
  "igual ao modelo": λ = 1 sempre (aí o modelo não tem vantagem nenhuma sobre o mercado).
O relógio do mercado anda ATRASO minutos à frente dos dados do modelo (publicação, download e
reação). Venda (bid) e compra (ask) ficam 1¢ abaixo e acima do preço.

Usado por estudos/banca.py, estudos/trade.py e pela simulação do painel.
"""
from __future__ import annotations

import numpy as np

from nucleo.modelo import NOMES_FAIXAS

ATRASO = 5
RITMOS = {"como em 4/10": (30.0, 30.0), "mais esperto": (10.0, 15.0), "igual ao modelo": None}
# preços de hoje (15/10/2026, meio entre bid e ask) = preço do mercado antes da apuração
PRECO_HOJE = {"L 12%+": 0.0025, "L 8-12%": 0.0035, "L 4-8%": 0.02, "L <4%": 0.185,
              "F <4%": 0.405, "F 4-8%": 0.325, "F 8-12%": 0.0865, "F 12%+": 0.02}


def peso_modelo(t, ritmo: str) -> np.ndarray:
    """λ no minuto t dos dados (escalar ou vetor): quanto do caminho até a chance do modelo o
    mercado já andou."""
    relogio = np.asarray(t, float) + ATRASO
    par = RITMOS[ritmo]
    if par is None:
        return np.ones_like(relogio)
    t0, tau = par
    return np.where(relogio > t0, 1 - np.exp(-(relogio - t0) / tau), 0.0)


def precos(probs, t: float, ritmo: str) -> tuple[np.ndarray, np.ndarray]:
    """(bid, ask) de cada faixa, na ordem de NOMES_FAIXAS. probs None = o modelo ainda não rodou."""
    hoje = np.array([PRECO_HOJE[f] for f in NOMES_FAIXAS])
    lam = float(peso_modelo(t, ritmo))
    p = hoje if probs is None else (1 - lam) * hoje + lam * np.asarray(probs, float)
    return np.maximum(p - 0.01, 0.0), np.minimum(p + 0.01, 1.0)


def mercado_sim(probs: dict | None, t: float, ritmo: str) -> dict[str, list[float]]:
    """{faixa: [bid, ask]} de um ciclo, como o painel mostra (probs = {faixa: chance} do ciclo)."""
    bid, ask = precos([probs[f] for f in NOMES_FAIXAS] if probs else None, t, ritmo)
    return {f: [round(float(b), 4), round(float(a), 4)] for f, b, a in zip(NOMES_FAIXAS, bid, ask)}


def chance_grupo(lo: float, hi: float) -> float:
    """Chance de a margem final cair em [lo, hi) pelos preços de hoje: margem uniforme dentro de
    cada faixa de 4 pontos; as faixas abertas (12+) contam como se a margem fosse 14."""
    tot = sum(PRECO_HOJE.values())
    p = 0.0
    for f, q in PRECO_HOJE.items():
        if f == "L 12%+":
            p += q * (lo <= -14 < hi)
        elif f == "F 12%+":
            p += q * (lo <= 14 < hi)
        else:
            a = {"L 8-12%": -12, "L 4-8%": -8, "L <4%": -4, "F <4%": 0, "F 4-8%": 4, "F 8-12%": 8}[f]
            p += q * max(0.0, min(hi, a + 4) - max(lo, a)) / 4
    return p / tot


def sortear_margem(rng: np.random.Generator) -> float:
    """Margem final pelas chances que o mercado dá hoje (uniforme dentro da faixa sorteada)."""
    p = np.array([PRECO_HOJE[f] for f in NOMES_FAIXAS])
    i = int(rng.choice(len(p), p=p / p.sum()))
    a = (-16, -12, -8, -4, 0, 4, 8, 12)[i]
    return float(rng.uniform(a, a + 4))
