"""Lote de apurações sintéticas do 2º turno: erro e incerteza do modelo minuto a minuto.

    python eleicao/rodar_simulacoes.py --ano 2022 --n 40 --saida resultados/sim_2022.parquet

Para cada simulação: sorteia margem final, cenário (heterogeneidade, ordem de chegada) e
horários; roda o modelo a cada 2 minutos e guarda (t, apurado, margem prevista, dp, final).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apuracao import apurar  # noqa: E402
from backtest import GRADE, rodar  # noqa: E402
from dados_eleicao import base_turno, municipios, secoes  # noqa: E402
from modelo import Ordem1T, Params  # noqa: E402
from simulacao import gerar_apuracao, sortear_cenario  # noqa: E402


def lote(ano: int, n: int, semente: int, margens: tuple[float, float], params: Params,
         passos=range(0, 241, 2)) -> pd.DataFrame:
    sec1 = secoes(ano, 1, "bu")
    ref2 = secoes(2022, 2, "bu")       # horários do 2º turno de referência
    b = base_turno(ano, 1)
    o = Ordem1T(sec1, b)
    rng = np.random.default_rng(semente)
    saidas = []
    for i in range(n):
        t0 = time.time()
        cen = sortear_cenario(float(rng.uniform(*margens)), rng)
        s2 = gerar_apuracao(sec1, ano, ref2, cen, rng)
        m2 = municipios(s2)
        munis = b.index.intersection(m2.index)
        ap = apurar(s2[s2["cd_mun"].isin(munis)], munis, GRADE)
        aptos = m2.loc[munis, "aptos"].to_numpy(float)
        df = rodar(b.loc[munis], aptos, ap, params, passos=passos, ordem=o)
        for k, v in vars(cen).items():
            df[k] = v
        df["sim"] = i
        saidas.append(df)
        z = (df["mu"] - df["final"]) / df["sd"]
        print(f"  sim {i}: margem {cen.margem:+.2f}, |z|>2 em {np.mean(np.abs(z) > 2) * 100:.0f}% dos passos, "
              f"{time.time() - t0:.0f}s", flush=True)
    return pd.concat(saidas, ignore_index=True)


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--ano", type=int, default=2022)
    ap_.add_argument("--n", type=int, default=40)
    ap_.add_argument("--semente", type=int, default=7)
    ap_.add_argument("--min", type=float, default=-2.0)
    ap_.add_argument("--max", type=float, default=10.0)
    ap_.add_argument("--saida", required=True)
    a = ap_.parse_args()
    df = lote(a.ano, a.n, a.semente, (a.min, a.max), Params())
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(a.saida, index=False)
    print("salvo", a.saida)
