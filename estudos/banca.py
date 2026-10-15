"""Quanto sobra de uma banca (padrão US$100) com cada regra de venda, nas noites simuladas.

Nas simulações não existe preço de mercado: o preço vem do mercado simulado de
nucleo/mercado_sim.py (preço de hoje → chance do modelo, em três ritmos). A venda sai 1¢ abaixo
desse preço (bid). O modelo vê os dados com 5 minutos de atraso.

Cada noite é agrupada pela margem final. O valor esperado pesa os grupos pelas chances que o
próprio mercado dá hoje a cada faixa (dentro de uma faixa, supõe margem uniforme).

    python eleicao/estudos/banca.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do projeto
from estudos.estrategia import REGRAS, Regra, faixa_idx, noite_real, toca_faixa  # noqa: E402
from estudos.relatorio import md, sd_atual  # noqa: E402
from nucleo.caminhos import RES  # noqa: E402
from nucleo.mercado_sim import PRECO_HOJE, RITMOS, chance_grupo, peso_modelo  # noqa: E402
from nucleo.modelo import Params, prob_faixas  # noqa: E402

REGRAS_BANCA = [Regra("Segurar até o fim", ())] + [r for r in REGRAS if r.nome in (
    "tudo se a faixa de 90% sair da sua, desde 2%",
    "tudo se chance ≤ 20%, desde 20%",
    "tudo se chance ≤ 20%, desde 5%",
    "escalonada: ⅓ a 30%, ⅓ a 15%, ⅓ a 5%, desde 5%")]
NOME_CURTO = {"Segurar até o fim": "Segurar até o fim",
              "tudo se a faixa de 90% sair da sua, desde 2%": "Faixa de 90% sai da sua",
              "tudo se chance ≤ 20%, desde 20%": "Chance ≤ 20% (desde 20%)",
              "tudo se chance ≤ 20%, desde 5%": "Chance ≤ 20% (desde 5%)",
              "escalonada: ⅓ a 30%, ⅓ a 15%, ⅓ a 5%, desde 5%": "Escalonada",
              "stop no preço": "Stop no preço (vende se o preço < 15¢)"}


def grupos(posicao: str) -> list[tuple[str, float, float, bool]]:
    """(nome, margem mínima, máxima, a posição ganha?) — cenários de resultado."""
    if posicao == "F <4%":
        return [("Lula vence", -99, 0, False), ("F <4%, longe de 4 (0 a 3)", 0, 3, True),
                ("F <4%, perto de 4 (3 a 4)", 3, 4, True), ("F 4-8%, perto de 4 (4 a 5)", 4, 5, False),
                ("Flávio por 5 ou mais", 5, 99, False)]
    return [("Lula vence", -99, 0, False), ("F <4%, longe de 4 (0 a 3)", 0, 3, False),
            ("F <4%, perto de 4 (3 a 4)", 3, 4, False), ("F 4-8%, perto de 4 (4 a 5)", 4, 5, True),
            ("F 4-8%, longe de 4 (5 a 8)", 5, 8, True), ("Flávio por 8 ou mais", 8, 99, False)]


def valor_por_cota(probs_pos, apurado, toca, t_dados, preco_mercado, regra: Regra | None,
                   ganha: bool, stop: float | None = None) -> tuple[float, float]:
    """(valor final por cota, fração vendida) para uma noite."""
    if stop is not None:
        v = np.maximum.accumulate(((apurado >= 0) & (preco_mercado < stop)).astype(float))
    elif regra is None or not regra.degraus:
        v = np.zeros(len(probs_pos))
    else:
        v = regra.vendas(probs_pos, apurado, toca)
    frac = np.diff(np.concatenate([[0.0], v]))
    preco_venda = np.maximum(preco_mercado - 0.01, 0.0)
    receita = float(np.sum(frac * preco_venda))
    return receita + (1.0 - float(v[-1])) * (1.0 if ganha else 0.0), float(v[-1])


def avaliar(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    linhas = []
    for sim, g in d.groupby("sim"):
        g = g.sort_values("t")
        t = g["t"].to_numpy(float)
        mu, sd, ap = g["mu"].to_numpy(), g["sd"].to_numpy(), g["apurado"].to_numpy()
        final = float(g["final"].iloc[0])
        probs = np.vstack([prob_faixas(m, s, p.gl) for m, s in zip(mu, sd)])
        for pos in ("F <4%", "F 4-8%"):
            i = faixa_idx(pos)
            pp = probs[:, i]
            ganha = (0 <= final < 4) if pos == "F <4%" else (4 <= final < 8)
            toca = toca_faixa(mu, sd, p.gl, i)
            for ritmo in RITMOS:
                # a decisão sai ATRASO minutos depois dos dados; o mercado anda até lá
                lam = peso_modelo(t, ritmo)
                preco = (1 - lam) * PRECO_HOJE[pos] + lam * pp
                for r in REGRAS_BANCA:
                    val, vend = valor_por_cota(pp, ap, toca, t, preco, r, ganha)
                    linhas.append({"sim": sim, "posicao": pos, "ritmo": ritmo, "regra": NOME_CURTO[r.nome],
                                   "final": final, "ganha": ganha, "valor": val, "vendido": vend})
                val, vend = valor_por_cota(pp, ap, toca, t, preco, None, ganha, stop=0.15)
                linhas.append({"sim": sim, "posicao": pos, "ritmo": ritmo, "regra": NOME_CURTO["stop no preço"],
                               "final": final, "ganha": ganha, "valor": val, "vendido": vend})
    return pd.DataFrame(linhas)


def tabela(av: pd.DataFrame, pos: str, ritmo: str, banca: float, entrada: float) -> tuple[pd.DataFrame, dict]:
    cotas = banca / entrada
    regras = list(dict.fromkeys(av["regra"]))
    linhas, ev = [], {}
    for nome, lo, hi, ganha in grupos(pos):
        sel = av[(av["posicao"] == pos) & (av["ritmo"] == ritmo) & (av["final"] >= lo) & (av["final"] < hi)]
        linha = {"cenário": nome, "chance hoje": f"{chance_grupo(lo, hi) * 100:.0f}%",
                 "noites": int(sel["sim"].nunique())}
        for r in regras:
            x = sel[sel["regra"] == r]
            linha[r] = f"US$ {x['valor'].mean() * cotas:.0f}" if len(x) else "—"
            ev[r] = ev.get(r, 0.0) + chance_grupo(lo, hi) * (x["valor"].mean() * cotas if len(x) else 0.0)
        linhas.append(linha)
    soma = sum(chance_grupo(lo, hi) for _, lo, hi, _ in grupos(pos))
    linha_ev = {"cenário": "**Média ponderada pelas chances de hoje**", "chance hoje": f"{soma * 100:.0f}%", "noites": ""}
    for r in regras:
        linha_ev[r] = f"**US$ {ev[r] / soma:.0f}**"
    linhas.append(linha_ev)
    return pd.DataFrame(linhas), {r: ev[r] / soma for r in regras}


def main() -> None:
    p = Params()
    d = pd.concat([pd.read_parquet(RES / "sim_2026.parquet").assign(lote="geral"),
                   pd.read_parquet(RES / "sim_2026_fronteira.parquet").assign(lote="fronteira")])
    d["sim"] = d["lote"] + "_" + d["sim"].astype(str)
    d["sd"] = sd_atual(d, p)
    av = avaliar(d, p)
    # o lote "fronteira" só entra nos cenários perto de 4 (fora deles distorceria as médias)
    perto = (av["final"] >= 3) & (av["final"] < 5)
    av = av[av["sim"].str.startswith("geral") | perto]
    av.to_csv(RES / "banca_noites.csv", index=False)
    saidas, resumo_json = [], {}
    for pos, entrada in (("F <4%", 0.41), ("F 4-8%", 0.33)):
        for ritmo in RITMOS:
            tab, ev = tabela(av, pos, ritmo, 100.0, entrada)
            saidas.append(f"### Sim em \"{pos}\" comprada a {entrada * 100:.0f}¢, US$100 "
                          f"(mercado {ritmo})\n\n" + md(tab, index=False))
            resumo_json[f"{pos}|{ritmo}"] = ev
    saidas.append(noite_real(p))
    (RES / "banca.md").write_text("\n\n".join(saidas), encoding="utf-8")
    # dados por noite para a calculadora do guia: valor por cota de cada regra em cada noite
    av.to_json(RES / "banca_noites.json", orient="records", force_ascii=False)
    print("\n\n".join(saidas))
    print(json.dumps(resumo_json, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
