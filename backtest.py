"""Backtest dos estimadores em apurações reais (com hora do BU) e sorteadas.

    python eleicao/backtest.py            # roda o painel padrão e salva resultados/
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apuracao import apurar, tempos_sorteados  # noqa: E402
from dados_eleicao import DADOS, base_turno, margem, municipios, secoes  # noqa: E402
from modelo import Ordem1T, Params, Transferencia, ingenuo, prob_faixas  # noqa: E402

AQUI = Path(__file__).resolve().parent
RES = AQUI / "resultados"
GRADE = np.arange(0, 241, 1.0)  # 17:00 a 21:00, de minuto em minuto


def preparar(alvo: tuple[int, int] = (2022, 2), base: tuple[int, int] | None = None):
    """Base por município + seções da apuração-alvo, alinhadas por município.

    alvo/base = (ano, turno). Padrão: base = 1º turno do mesmo ano. Devolve também as
    seções da base com hora (BU), quando existem, para a composição ordenada (Ordem1T).
    """
    base = base or (alvo[0], 1)
    b = base_turno(*base)
    sec = secoes(*alvo, "bu")
    m2 = municipios(sec)
    munis = b.index.intersection(m2.index)
    sec = sec[sec["cd_mun"].isin(munis)]  # municípios sem base (raros) ficam de fora
    b = b.loc[munis]
    aptos = m2.loc[munis, "aptos"].to_numpy(float)
    sec_base = None
    if (DADOS / f"bu_{base[0]}_{base[1]}t.parquet").exists():
        sb = secoes(*base, "bu")
        if sb["t"].notna().mean() > 0.9:
            sec_base = sb
    return b, sec, munis, aptos, sec_base


def agregar_uf(base: pd.DataFrame, aptos: np.ndarray, ap: dict):
    """Mesma apuração vista só pelos totais de cada UF (o que se teria sem os municípios)."""
    ufs = pd.Index(sorted(base["uf"].unique()))
    iu = ufs.get_indexer(base["uf"])
    num = [c for c in base.columns if c != "uf" and c != "nm_mun"]
    b = base[num].groupby(base["uf"].to_numpy()).sum().loc[ufs]
    b.insert(0, "uf", ufs)
    b["nm_mun"] = ufs
    S = np.zeros((len(base), len(ufs)))
    S[np.arange(len(base)), iu] = 1
    ap2 = {k: (v @ S if isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[-1] == len(base) else v)
           for k, v in ap.items() if k != "tot"}
    ap2["tot"] = {k: v @ S for k, v in ap["tot"].items()}
    return b, aptos @ S, ap2


def rodar(base, aptos, ap, params: Params, passos=None, nivel="mun", ordem=None) -> pd.DataFrame:
    """Aplica o estimador a cada retrato da apuração `ap`."""
    if nivel == "uf":
        base, aptos, ap = agregar_uf(base, aptos, ap)
        params = replace(params, s0_D=params.tau_uf, s0_S=params.tau_uf * 0.7, tau_uf=1e-4)
    mod = Transferencia(base, aptos, params, ordem=ordem if nivel == "mun" else None)
    mod.reiniciar()
    final = margem(ap["tot"]["F"], ap["tot"]["L"])
    linhas = []
    passos = range(len(ap["t"])) if passos is None else passos
    for k in passos:
        F, L, A = ap["F"][k], ap["L"][k], ap["aptos"][k]
        if F.sum() + L.sum() == 0:
            continue
        r = mod.prever(F, L, A, t=ap["t"][k])
        linhas.append(dict(t=ap["t"][k], apurado=r["apurado"] * 100,
                           secoes=ap["nsec"][k].sum() / ap["tot"]["nsec"].sum() * 100,
                           ingenuo=ingenuo(F, L), mu=r["mu"], sd=r["sd"], sd_bruto=r["sd_bruto"],
                           phi_D=r["phi_D"], w=r["w_medio"], final=final))
    return pd.DataFrame(linhas)


def resumo(df: pd.DataFrame, nome: str) -> str:
    out = [f"== {nome}: final {df['final'].iloc[0]:+.2f}"]
    for t in [5, 10, 15, 20, 30, 45, 60, 75, 90, 105, 120, 150, 180]:
        r = df[df["t"] <= t]
        if r.empty:
            continue
        r = r.iloc[-1]
        z = (r["mu"] - r["final"]) / r["sd"]
        out.append(f"  +{int(t):3d}min apurado {r['apurado']:5.1f}%  ingênuo {r['ingenuo']:+6.2f}  "
                   f"modelo {r['mu']:+6.2f} ± {r['sd']:.2f}  erro {r['mu'] - r['final']:+5.2f}  z {z:+5.2f}"
                   f"  w {r['w']:.2f}  phiD {r['phi_D']:.1f}")
    return "\n".join(out)


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    p = Params()
    for alvo, base in (((2022, 2), (2022, 1)), ((2022, 1), (2022, 2))):
        b, sec, munis, aptos, sec_base = preparar(alvo, base)
        ap = apurar(sec, munis, GRADE)
        nome = f"{alvo[0]} {alvo[1]}T real (base {base[0]} {base[1]}T)"
        print(resumo(rodar(b, aptos, ap, p), nome + ", base média"))
        if sec_base is not None:
            o = Ordem1T(sec_base, b)
            print(resumo(rodar(b, aptos, ap, p, ordem=o), nome + ", base ordenada (w ao vivo)"))
