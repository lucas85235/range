"""Modelo × Polymarket na noite real do 1º turno de 2026 (4/10), minuto a minuto.

O modelo roda como se fosse ao vivo: só com o que existia naquela noite (base = 2º turno de 2022,
ordem das seções de 2022) e com a apuração reconstruída pela hora do BU. O mercado é o de margem
do 1º turno (faixas de 5 pontos), cuja margem é sobre todos os votos válidos (com os outros
candidatos); o modelo prevê a margem entre os dois, então ela é convertida pela fração
(F + L) / válidos já apurada naquele minuto.

Duas versões do modelo:
  "antes": parâmetros de antes de olhar esta apuração;
  "final": os de calibracao.json (escolhidos depois de ver esta noite: dentro da amostra).

    python eleicao/comparar_mercado.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apuracao import apurar  # noqa: E402
from backtest import GRADE, preparar, rodar  # noqa: E402
from dados_eleicao import DADOS  # noqa: E402
from modelo import Ordem1T, Params, prob_faixas  # noqa: E402

RES = Path(__file__).resolve().parent / "resultados"
CORTES = np.array([-15, -10, -5, 0, 5, 10], float)
FAIXAS = ["L 15%+", "L 10-15%", "L 5-10%", "L <5%", "F <5%", "F 5-10%", "F 10%+"]
NOME_PM = {"Lula da Silva 15%+": "L 15%+", "Lula da Silva 10-15%": "L 10-15%",
           "Lula da Silva 5-10%": "L 5-10%", "Lula da Silva <5%": "L <5%",
           "Flávio Bolsonaro <5%": "F <5%", "Flávio Bolsonaro 5-10%": "F 5-10%",
           "Flávio Bolsonaro 10%+": "F 10%+"}
PARAMS_ANTES = replace(Params(), ws=(0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5), w_dp=0.30,
                       tau_tam=0.0, sis_b=0.0)


def mercado() -> pd.DataFrame:
    """Preço do Sim de cada faixa por minuto (após as 17h = 0), normalizado para somar 1."""
    d = pd.read_parquet(DADOS / "polymarket_1t.parquet")
    m = d[(d["mercado"] == "margem") & d["faixa"].isin(NOME_PM)].copy()
    m["faixa"] = m["faixa"].map(NOME_PM)
    piv = m.pivot_table(index="min", columns="faixa", values="preco", aggfunc="last")
    piv = piv.reindex(range(int(piv.index.min()), int(piv.index.max()) + 1)).ffill()[FAIXAS]
    bruto = piv.copy()
    piv = piv.div(piv.sum(axis=1), axis=0)
    v = d[(d["mercado"] == "vencedor") & (d["faixa"] == "Flavio Bolsonaro")].set_index("min")["preco"]
    v = v.reindex(piv.index).ffill()
    out = piv.add_prefix("pm_")
    out[[f"bruto_{c}" for c in FAIXAS]] = bruto.to_numpy()
    out["pm_F_primeiro"] = v
    return out


def parcial_validos(sec: pd.DataFrame) -> pd.DataFrame:
    """Por minuto: fração (F + L) / válidos e margem F - L sobre todos os válidos, já apurados."""
    k = np.searchsorted(GRADE, sec["t"].to_numpy(float), side="left")
    acc = {}
    for c in ("F", "L", "V"):
        a = np.bincount(k, weights=sec[c].to_numpy(float), minlength=len(GRADE) + 1)
        acc[c] = np.cumsum(a)[: len(GRADE)]
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.DataFrame({"t": GRADE, "r": (acc["F"] + acc["L"]) / acc["V"],
                             "parcial_mercado": 100 * (acc["F"] - acc["L"]) / acc["V"]})


def modelo_noite(params: Params) -> pd.DataFrame:
    b, sec, munis, aptos, sb = preparar((2026, 1), (2022, 2))
    ap = apurar(sec, munis, GRADE)
    df = rodar(b, aptos, ap, params, passos=range(0, 241, 1), ordem=Ordem1T(sb, b))
    df = df.merge(parcial_validos(sec), on="t")
    r = df["r"].fillna(0.92).clip(0.5, 1.0)
    probs = np.vstack([prob_faixas(m, s, params.gl, cortes=CORTES / ri)
                       for m, s, ri in zip(df["mu"], df["sd"], r)])
    for i, f in enumerate(FAIXAS):
        df[f"mod_{f}"] = probs[:, i]
    df["mod_F_primeiro"] = 1 - np.array([prob_faixas(m, s, params.gl, cortes=(0,))[0]
                                         for m, s in zip(df["mu"], df["sd"])])
    df["mu_mercado"] = df["mu"] * r          # margem prevista na definição do mercado
    df["sd_mercado"] = df["sd"] * r
    return df


def pontuar(df: pd.DataFrame, certa: str, janelas) -> pd.DataFrame:
    linhas = []
    for a, b in janelas:
        s = df[(df["t"] >= a) & (df["t"] < b)]
        for quem in ("mod", "pm"):
            P = s[[f"{quem}_{f}" for f in FAIXAS]].to_numpy().clip(1e-4, 1)
            y = np.array([f == certa for f in FAIXAS], float)
            linhas.append({"janela": f"{17 + a // 60}:{a % 60:02d}–{17 + b // 60}:{b % 60:02d}", "quem": quem,
                           "P_certa_media": float(np.mean(P[:, FAIXAS.index(certa)])),
                           "log_score": float(np.mean(np.log(P[:, FAIXAS.index(certa)]))),
                           "brier": float(np.mean(np.sum((P - y) ** 2, axis=1)))})
    return pd.DataFrame(linhas)


def cruzamentos(df: pd.DataFrame, col: str, limiares=(0.5, 0.8, 0.9, 0.95)) -> dict:
    """Primeiro minuto a partir do qual `col` fica acima de cada limiar até o fim."""
    out = {}
    v = df[col].to_numpy()
    for lim in limiares:
        ok = v >= lim
        k = len(ok)
        while k > 0 and ok[k - 1]:
            k -= 1
        out[lim] = float(df["t"].iloc[k]) if k < len(ok) else np.nan
    return out


def hora(t: float) -> str:
    if np.isnan(t):
        return "—"
    m = int(round(17 * 60 + t))
    return f"{m // 60}:{m % 60:02d}"


def main() -> pd.DataFrame:
    pm = mercado()
    final = None
    tabelas = {}
    for nome, params in (("final", Params()), ("antes", PARAMS_ANTES)):
        df = modelo_noite(params).merge(pm, left_on="t", right_index=True, how="left")
        df.to_csv(RES / f"mercado_1t_modelo_{nome}.csv", index=False)
        tabelas[nome] = df
        if final is None:
            final = df
    df = final
    certa = "F <5%"
    _, sec, _, _, _ = preparar((2026, 1), (2022, 2))
    print("margem real (definição do mercado, todos os válidos):",
          round(float(100 * (sec["F"].sum() - sec["L"].sum()) / sec["V"].sum()), 2))
    for nome, d in tabelas.items():
        c_mod = cruzamentos(d, f"mod_{certa}")
        print(f"modelo {nome}: P({certa}) fica acima de 50/80/90/95% às", [hora(c_mod[x]) for x in c_mod])
    c_pm = cruzamentos(df, f"pm_{certa}")
    print("mercado: P(F <5%) fica acima de 50/80/90/95% às", [hora(c_pm[x]) for x in c_pm])
    print("\nminuto a minuto (modelo final | antes | mercado):")
    for t in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 90, 105, 120]:
        if not (df["t"] == t).any():
            continue
        r = df[df["t"] == t].iloc[0]
        ra = tabelas["antes"][tabelas["antes"]["t"] == t].iloc[0]
        print(f"  {hora(t)} apurado {r['apurado']:5.1f}% | parcial {r['parcial_mercado']:+6.2f} | "
              f"modelo {r['mu_mercado']:+5.2f}±{r['sd_mercado']:.2f} | "
              f"P(F<5): mod {r['mod_F <5%'] * 100:4.0f}% antes {ra['mod_F <5%'] * 100:4.0f}% mercado {r['pm_F <5%'] * 100:4.0f}% | "
              f"P(L<5): mod {r['mod_L <5%'] * 100:4.0f}% mercado {r['pm_L <5%'] * 100:4.0f}% | "
              f"P(F 1º): mod {r['mod_F_primeiro'] * 100:4.0f}% mercado {r['pm_F_primeiro'] * 100:4.0f}%")
    janelas = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 90), (90, 150)]
    for nome, d in tabelas.items():
        sc = pontuar(d, certa, janelas)
        sc.to_csv(RES / f"mercado_1t_pontuacao_{nome}.csv", index=False)
        print(f"\npontuação (modelo {nome} × mercado):")
        print(sc.pivot(index="janela", columns="quem", values=["P_certa_media", "log_score", "brier"]).round(3)
              .reindex([f"{17 + a // 60}:{a % 60:02d}–{17 + b // 60}:{b % 60:02d}" for a, b in janelas]).to_string())
    return df


if __name__ == "__main__":
    main()
