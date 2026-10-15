"""Dados do guia "como ler a tela": uma noite simulada do 2º turno e a noite real do 1º.

Saída: resultados/guia_dados.json, lido pela página do guia.

    python eleicao/guia_dados.py --margem 4.4 --semente 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apuracao import apurar  # noqa: E402
from backtest import GRADE, rodar  # noqa: E402
from comparar_mercado import FAIXAS as FAIXAS_1T, PARAMS_ANTES, mercado, modelo_noite  # noqa: E402
from dados_eleicao import base_turno, municipios, secoes  # noqa: E402
from modelo import NOMES_FAIXAS, Ordem1T, Params, ingenuo, prob_faixas  # noqa: E402
from monitor import formatar_tela  # noqa: E402
from simulacao import gerar_apuracao, sortear_cenario  # noqa: E402

RES = Path(__file__).resolve().parent / "resultados"
ATRASO = 5  # min: publicação do TSE + download do monitor (o modelo "vê" os dados mais tarde)


def hora(t: float) -> str:
    m = int(round(17 * 60 + t))
    return f"{m // 60}:{m % 60:02d}"


def noite_simulada(margem: float, semente: int) -> dict:
    p = Params()
    sec1 = secoes(2026, 1, "bu")
    b = base_turno(2026, 1)
    rng = np.random.default_rng(semente)
    cen = sortear_cenario(margem, rng)
    s2 = gerar_apuracao(sec1, 2026, secoes(2022, 2, "bu"), cen, rng)
    m2 = municipios(s2)
    munis = b.index.intersection(m2.index)
    ap = apurar(s2[s2["cd_mun"].isin(munis)], munis, GRADE)
    aptos = m2.loc[munis, "aptos"].to_numpy(float)
    df = rodar(b.loc[munis], aptos, ap, p, passos=range(0, 241, 1), ordem=Ordem1T(sec1, b))
    df["t"] = df["t"] + ATRASO
    probs = np.vstack([prob_faixas(m, s, p.gl) for m, s in zip(df["mu"], df["sd"])])
    telas = []
    for t in [7, 12, 17, 22, 27, 32, 40, 50, 60, 75, 95, 115, 135]:
        r = df[df["t"] <= t]
        if r.empty:
            continue
        i = r.index[-1]
        k = df.index.get_loc(i)
        res = {"t": t, "gerado": f"25/10/2026 {hora(t)}:00", "secoes_pct": df.loc[i, "secoes"],
               "eleitorado_pct": df.loc[i, "apurado"], "baixados": 450,
               "parcial_tse": df.loc[i, "ingenuo"], "mu": df.loc[i, "mu"], "sd": df.loc[i, "sd"],
               "w": df.loc[i, "w"], "probs": dict(zip(NOMES_FAIXAS, probs[k].round(4).tolist()))}
        telas.append({"hora": hora(t), "t": t, "apurado": round(float(df.loc[i, "apurado"]), 1),
                      "mu": round(float(df.loc[i, "mu"]), 2), "sd": round(float(df.loc[i, "sd"]), 2),
                      "parcial": round(float(df.loc[i, "ingenuo"]), 2),
                      "p_menor4": round(float(probs[k][NOMES_FAIXAS.index("F <4%")]), 4),
                      "p_4a8": round(float(probs[k][NOMES_FAIXAS.index("F 4-8%")]), 4),
                      "tela": formatar_tela(res, "F <4%", "sim")[0]})
    return {"margem_final": round(float(df["final"].iloc[0]), 2), "cenario": {k: (round(v, 3) if isinstance(v, float) else v)
                                                                        for k, v in vars(cen).items()},
            "t": df["t"].round(1).tolist(), "apurado": df["apurado"].round(2).tolist(),
            "secoes": df["secoes"].round(2).tolist(), "w": df["w"].round(2).tolist(),
            "parcial": df["ingenuo"].round(3).tolist(), "mu": df["mu"].round(3).tolist(),
            "sd": df["sd"].round(3).tolist(),
            "probs": {f: probs[:, i].round(4).tolist() for i, f in enumerate(NOMES_FAIXAS)},
            "p_menor4": probs[:, NOMES_FAIXAS.index("F <4%")].round(4).tolist(),
            "p_4a8": probs[:, NOMES_FAIXAS.index("F 4-8%")].round(4).tolist(),
            "telas": telas}


def noite_real_1t() -> dict:
    pm = mercado()
    out = {"atraso_min": ATRASO}
    for nome, params in (("final", Params()), ("antes", PARAMS_ANTES)):
        df = modelo_noite(params)
        df["t"] = df["t"] + ATRASO
        out[f"modelo_{nome}"] = {
            "t": df["t"].tolist(), "apurado": df["apurado"].round(2).tolist(),
            "mu": df["mu_mercado"].round(3).tolist(), "sd": df["sd_mercado"].round(3).tolist(),
            "parcial": df["parcial_mercado"].round(3).tolist(),
            **{f: df[f"mod_{f}"].round(4).tolist() for f in FAIXAS_1T},
            "F_primeiro": df["mod_F_primeiro"].round(4).tolist()}
    pm = pm[(pm.index >= -60) & (pm.index <= 240)]
    out["mercado"] = {"t": pm.index.tolist(), **{f: pm[f"pm_{f}"].round(4).tolist() for f in FAIXAS_1T},
                      "F_primeiro": pm["pm_F_primeiro"].round(4).tolist(),
                      **{f"bruto_{f}": pm[f"bruto_{f}"].round(4).tolist() for f in FAIXAS_1T}}
    sec = secoes(2026, 1, "bu")
    out["margem_final"] = round(float(100 * (sec["F"].sum() - sec["L"].sum()) / sec["V"].sum()), 2)
    return out


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--noite-a", default="4.4:1", help="margem:semente da noite que dá certo cedo")
    a.add_argument("--noite-b", default="3.7:3", help="margem:semente da noite com alarme falso")
    args = a.parse_args()
    dados = {}
    for chave, txt in (("sim_a", args.noite_a), ("sim_b", args.noite_b)):
        m, sem = txt.split(":")
        dados[chave] = noite_simulada(float(m), int(sem))
        s = dados[chave]
        print(f"{chave}: margem final", s["margem_final"])
        for tela in s["telas"]:
            print(f"  {tela['hora']} apurado {tela['apurado']:5.1f}% parcial {tela['parcial']:+.2f} "
                  f"modelo {tela['mu']:+.2f}±{tela['sd']:.2f} P(F<4) {tela['p_menor4'] * 100:4.0f}% "
                  f"P(F4-8) {tela['p_4a8'] * 100:4.0f}%")
    dados["real1t"] = noite_real_1t()
    arq = RES / "guia_dados.json"
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    print("salvo", arq)


if __name__ == "__main__":
    main()
