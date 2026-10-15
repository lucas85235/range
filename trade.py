"""Simulação de "trade": começar numa faixa e trocar para a faixa que o modelo aponta.

Só simulação, nas noites sintéticas: nada aqui envia ordens. Cada noite é jogada de dois jeitos:
  segurar      fica com a posição inicial até o fim;
  rebalancear  vende e compra a faixa que o modelo aponta, pela regra abaixo.

Regra (a mesma da aba Trade do painel, que a mostra na noite que está passando):
  - só age a partir de `apurado_min` % apurado e com o modelo já rodando;
  - alvo = faixa com maior chance no modelo; troca quando o alvo não é a faixa que se tem e o
    modelo dá ao alvo pelo menos `limiar`;
  - vende tudo no bid; em "rebalancear", compra o alvo no ask se a chance do modelo passar o ask
    em pelo menos `vantagem` (senão fica em dinheiro e pode comprar depois, se aparecer vantagem);
  - no máximo `max_trocas` vendas na noite.
Preço: o mercado simulado de banca.py (preço de hoje → chance do modelo no ritmo escolhido),
1¢ abaixo/acima para bid/ask. No ritmo "igual ao modelo" o mercado já sabe o que o modelo sabe.

    python eleicao/trade.py                 # tabela por cenário, nas noites simuladas salvas
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from banca import ATRASO, PRECO_HOJE, RITMOS, chance_grupo  # noqa: E402
from modelo import NOMES_FAIXAS, prob_faixas  # noqa: E402,F401  (probs_linhas = prob_faixas vetorizada)
from relatorio import md, sd_atual  # noqa: E402

RES = Path(__file__).resolve().parent / "resultados"
BORDAS = [-np.inf, -12, -8, -4, 0, 4, 8, 12, np.inf]
CENARIOS = [("Lula vence", -99, 0), ("F <4%, longe de 4 (0 a 3)", 0, 3), ("F <4%, perto de 4 (3 a 4)", 3, 4),
            ("F 4-8%, perto de 4 (4 a 5)", 4, 5), ("F 4-8%, longe de 4 (5 a 8)", 5, 8), ("Flávio por 8 ou mais", 8, 99)]
VERSOES = ("segurar", "rebalancear")


@dataclass
class Regra:
    inicial: str = "F <4%"
    entrada: float = 0.41      # preço pago pela posição inicial
    banca: float = 100.0
    limiar: float = 0.70
    vantagem: float = 0.05
    apurado_min: float = 2.0
    max_trocas: int = 2


def faixa_de(margem: float) -> str:
    """Faixa da Polymarket de uma margem (na fronteira exata vale a de cima)."""
    i = int(np.searchsorted(BORDAS, margem, side="right")) - 1
    return NOMES_FAIXAS[min(max(i, 0), len(NOMES_FAIXAS) - 1)]


def precos(probs: np.ndarray | None, t: float, ritmo: str) -> tuple[np.ndarray, np.ndarray]:
    """(bid, ask) simulados de cada faixa, como banca.py / painel.py."""
    hoje = np.array([PRECO_HOJE[f] for f in NOMES_FAIXAS])
    par, relogio = RITMOS[ritmo], t + ATRASO
    lam = 1.0 if par is None else (1 - math.exp(-(relogio - par[0]) / par[1]) if relogio > par[0] else 0.0)
    p = hoje if probs is None else (1 - lam) * hoje + lam * probs
    return np.maximum(p - 0.01, 0.0), np.minimum(p + 0.01, 1.0)


def jogar(t, apurado, probs, bids, asks, regra: Regra, versao: str, final: str) -> dict:
    """Uma noite com uma versão da regra. probs/bids/asks: (n, 8). Devolve valor final e trocas."""
    h = NOMES_FAIXAS.index(regra.inicial)
    cotas, caixa, vendas, ops = regra.banca / regra.entrada, 0.0, 0, []
    valor = []
    for k in range(len(t)):
        if versao != "segurar" and probs[k] is not None and apurado[k] >= regra.apurado_min:
            alvo = int(np.argmax(probs[k]))
            confiante = probs[k][alvo] >= regra.limiar
            if h is not None and alvo != h and confiante and vendas < regra.max_trocas:
                caixa += cotas * bids[k][h]
                ops.append({"k": k, "t": float(t[k]), "op": "vende", "faixa": NOMES_FAIXAS[h], "preco": float(bids[k][h]),
                            "cotas": cotas, "valor": cotas * bids[k][h]})
                cotas, h, vendas = 0.0, None, vendas + 1
            if (h is None and confiante
                    and probs[k][alvo] - asks[k][alvo] >= regra.vantagem and asks[k][alvo] > 0):
                h, cotas = alvo, caixa / asks[k][alvo]
                ops.append({"k": k, "t": float(t[k]), "op": "compra", "faixa": NOMES_FAIXAS[alvo], "preco": float(asks[k][alvo]),
                            "cotas": cotas, "valor": caixa})
                caixa = 0.0
        valor.append(caixa + (cotas * bids[k][h] if h is not None else 0.0))
    fim = caixa + (cotas if h is not None and NOMES_FAIXAS[h] == final else 0.0)
    return {"valor": fim, "ops": ops, "curva": valor, "termina_em": NOMES_FAIXAS[h] if h is not None else "dinheiro"}


def noites(params) -> pd.DataFrame:
    """Noites simuladas salvas (as mesmas de banca.py), com a incerteza recalculada."""
    d = pd.concat([pd.read_parquet(RES / "sim_2026.parquet").assign(lote="geral"),
                   pd.read_parquet(RES / "sim_2026_fronteira.parquet").assign(lote="fronteira")])
    d["sim"] = d["lote"] + "_" + d["sim"].astype(str)
    d["sd"] = sd_atual(d, params)
    # o lote "fronteira" só entra perto de 4 (fora disso distorceria as médias), como em banca.py
    perto = (d["final"] >= 3) & (d["final"] < 5)
    return d[(d["lote"] == "geral") | perto]


def probs_linhas(mu: np.ndarray, sd: np.ndarray, gl: float) -> np.ndarray:
    """prob_faixas para muitas linhas de uma vez: (n, 8)."""
    cortes = np.array(BORDAS[1:-1], float)
    cdf = stats.t(gl).cdf((cortes[None, :] - mu[:, None]) / np.maximum(sd[:, None], 1e-9))
    n = len(mu)
    return np.diff(np.hstack([np.zeros((n, 1)), cdf, np.ones((n, 1))]), axis=1)


def lote(d: pd.DataFrame, regra: Regra, ritmo: str, gl: float) -> pd.DataFrame:
    linhas = []
    for sim, g in d.groupby("sim"):
        g = g.sort_values("t")
        t, ap = g["t"].to_numpy(float), g["apurado"].to_numpy(float)
        probs = probs_linhas(g["mu"].to_numpy(float), g["sd"].to_numpy(float), gl)
        bids, asks = zip(*(precos(p, tk, ritmo) for p, tk in zip(probs, t)))
        mf = float(g["final"].iloc[0])
        fx = faixa_de(mf)
        linha = {"sim": sim, "final": mf, "faixa_final": fx}
        for v in VERSOES:
            r = jogar(t, ap, probs, bids, asks, regra, v, fx)
            linha[v] = r["valor"]
            if v == "rebalancear":
                linha["termina_em"] = r["termina_em"]
                linha["n_ops"] = len(r["ops"])
        linhas.append(linha)
    return pd.DataFrame(linhas)


def resumo(av: pd.DataFrame, banca: float) -> dict:
    """Por cenário (média por noite) e média ponderada pelas chances de hoje do mercado."""
    tab, pond = [], {v: 0.0 for v in VERSOES}
    peso_tot = 0.0
    for nome, lo, hi in CENARIOS:
        g = av[(av["final"] >= lo) & (av["final"] < hi)]
        if g.empty:
            continue
        w = chance_grupo(lo, hi)
        peso_tot += w
        linha = {"cenario": nome, "noites": len(g), "chance_hoje": w}
        for v in VERSOES:
            linha[v] = float(g[v].mean())
            pond[v] += w * linha[v]
        linha["acertou_faixa"] = float((g["termina_em"] == g["faixa_final"]).mean())
        tab.append(linha)
    media = {v: pond[v] / peso_tot for v in VERSOES} if peso_tot else {}
    return {"cenarios": tab, "media": media, "banca": banca,
            "lucro_noites": {v: float((av[v] > banca).mean()) for v in VERSOES}, "n": len(av)}


def main() -> None:
    from monitor import carregar_params
    p = carregar_params()
    d = noites(p)
    for inicial, entrada in (("F <4%", 0.41), ("F 4-8%", 0.33)):
        for ritmo in RITMOS:
            r = resumo(lote(d, Regra(inicial=inicial, entrada=entrada), ritmo, p.gl), 100.0)
            tab = pd.DataFrame(r["cenarios"]).round(2)
            print(f"\n### Começando em Sim \"{inicial}\" a {entrada * 100:.0f}¢, mercado {ritmo}\n")
            print(md(tab, index=False))
            print("média ponderada pelo mercado de hoje: "
                  + ", ".join(f"{v} US$ {x:.2f}" for v, x in r["media"].items()))


if __name__ == "__main__":
    main()
