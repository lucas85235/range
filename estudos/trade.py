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
Preço: o mercado simulado de nucleo/mercado_sim.py (preço de hoje → chance do modelo no ritmo
escolhido), 1¢ abaixo/acima para bid/ask. No ritmo "igual ao modelo" o mercado já sabe o que o
modelo sabe.

    python eleicao/estudos/trade.py                 # tabela por cenário, nas noites simuladas salvas
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do projeto
from estudos.comparar_mercado import FAIXAS as FAIXAS_1T, NOME_PM  # noqa: E402
from estudos.relatorio import md, sd_atual  # noqa: E402
from nucleo.caminhos import DADOS, RES  # noqa: E402
from nucleo.mercado_sim import ATRASO, RITMOS, chance_grupo, precos  # noqa: E402
from nucleo.modelo import NOMES_FAIXAS, carregar_params  # noqa: E402

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


def jogar(t, apurado, probs, bids, asks, regra: Regra, versao: str, final: str,
          faixas: list[str] = NOMES_FAIXAS) -> dict:
    """Uma noite com uma versão da regra. probs/bids/asks: (n, faixas). Devolve valor final e trocas."""
    h = faixas.index(regra.inicial)
    cotas, caixa, vendas, ops = regra.banca / regra.entrada, 0.0, 0, []
    valor = []
    for k in range(len(t)):
        if versao != "segurar" and probs[k] is not None and apurado[k] >= regra.apurado_min:
            alvo = int(np.argmax(probs[k]))
            confiante = probs[k][alvo] >= regra.limiar
            if h is not None and alvo != h and confiante and vendas < regra.max_trocas:
                caixa += cotas * bids[k][h]
                ops.append({"k": k, "t": float(t[k]), "op": "vende", "faixa": faixas[h], "preco": float(bids[k][h]),
                            "cotas": cotas, "valor": cotas * bids[k][h]})
                cotas, h, vendas = 0.0, None, vendas + 1
            if (h is None and confiante
                    and probs[k][alvo] - asks[k][alvo] >= regra.vantagem and asks[k][alvo] > 0):
                h, cotas = alvo, caixa / asks[k][alvo]
                ops.append({"k": k, "t": float(t[k]), "op": "compra", "faixa": faixas[alvo], "preco": float(asks[k][alvo]),
                            "cotas": cotas, "valor": caixa})
                caixa = 0.0
        valor.append(caixa + (cotas * bids[k][h] if h is not None else 0.0))
    fim = caixa + (cotas if h is not None and faixas[h] == final else 0.0)
    return {"valor": fim, "ops": ops, "curva": valor, "termina_em": faixas[h] if h is not None else "dinheiro"}


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


def pesos(av: pd.DataFrame) -> np.ndarray:
    """Peso de cada noite: a chance de hoje do cenário dela, dividida entre as noites do cenário.
    (O lote tem noites extras perto de 4; sem o peso, elas pesariam demais.)"""
    w = np.zeros(len(av))
    for _, lo, hi in CENARIOS:
        m = ((av["final"] >= lo) & (av["final"] < hi)).to_numpy()
        if m.any():
            w[m] = chance_grupo(lo, hi) / m.sum()
    return w / w.sum()


def quantil(x: np.ndarray, w: np.ndarray, q: float) -> float:
    """Quantil ponderado: o menor valor com peso acumulado ≥ q."""
    o = np.argsort(x)
    return float(x[o][min(int(np.searchsorted(np.cumsum(w[o]), q)), len(x) - 1)])


def resumo(av: pd.DataFrame, banca: float) -> dict:
    """Por cenário (média por noite) e, sobre todas as noites com o peso de pesos(): média,
    mediana, os 10% piores e a chance de prejuízo."""
    tab = []
    for nome, lo, hi in CENARIOS:
        g = av[(av["final"] >= lo) & (av["final"] < hi)]
        if g.empty:
            continue
        linha = {"cenario": nome, "noites": len(g), "chance_hoje": chance_grupo(lo, hi)}
        for v in VERSOES:
            linha[v] = float(g[v].mean())
        linha["acertou_faixa"] = float((g["termina_em"] == g["faixa_final"]).mean())
        tab.append(linha)
    w = pesos(av)
    dist = {}
    for v in VERSOES:
        x = av[v].to_numpy(float)
        dist[v] = {"media": float(np.sum(w * x)), "mediana": quantil(x, w, 0.5), "p10": quantil(x, w, 0.1),
                   "lucro": float(np.sum(w[x > banca])), "prejuizo": float(np.sum(w[x < banca])),
                   "perde_metade": float(np.sum(w[x < banca / 2]))}
    return {"cenarios": tab, "media": {v: dist[v]["media"] for v in VERSOES}, "dist": dist, "banca": banca,
            "lucro_noites": {v: dist[v]["lucro"] for v in VERSOES}, "n": len(av)}


# faixa do 1º turno (5 pontos) que corresponde a cada faixa do 2º (4 pontos)
EQUIVALENTE_1T = {"L 12%+": "L 15%+", "L 8-12%": "L 10-15%", "L 4-8%": "L 5-10%", "L <4%": "L <5%",
                  "F <4%": "F <5%", "F 4-8%": "F 5-10%", "F 8-12%": "F 10%+", "F 12%+": "F 10%+"}


def noite_real_1t(regra: Regra, spreads=(0.01, 0.03)) -> dict:
    """A regra na noite real do 1º turno (4/10), com os preços reais da Polymarket.

    Aquele mercado tinha faixas de 5 pontos: a posição inicial vira a faixa equivalente
    (F <4% → F <5% etc.) e também se testa começar na favorita do mercado antes da apuração.
    Modelo: o de parâmetros "antes" (escolhidos sem olhar esta noite), decidindo com os dados de
    ATRASO minutos antes; preço: o real daquele minuto, com 1¢ (e 3¢) de cada lado. A compra
    inicial sai pelo preço do primeiro ciclo com votos.
    """
    r = pd.read_csv(RES / "mercado_1t_modelo_antes.csv").sort_values("t")
    t, ap = r["t"].to_numpy(float), r["apurado"].to_numpy(float)
    probs = r[[f"mod_{f}" for f in FAIXAS_1T]].to_numpy()
    preco = r[[f"bruto_{f}" for f in FAIXAS_1T]].to_numpy()
    k = np.searchsorted(t, t - ATRASO, side="right") - 1
    probs_d = [probs[j] if j >= 0 else None for j in k]
    ap_d = np.where(k >= 0, ap[np.maximum(k, 0)], 0.0)
    pm = pd.read_parquet(DADOS / "polymarket_1t.parquet")
    final = NOME_PM[pm[(pm["mercado"] == "margem") & pm["venceu"].astype(bool)]["faixa"].iloc[0]]
    favorita = FAIXAS_1T[int(np.argmax(preco[0]))]
    inicios = list(dict.fromkeys([EQUIVALENTE_1T[regra.inicial], favorita]))
    linhas = []
    for ini in inicios:
        entrada = float(preco[0][FAIXAS_1T.index(ini)])
        rg = replace(regra, inicial=ini, entrada=entrada)
        for s in spreads:
            bids, asks = np.maximum(preco - s, 0.0), np.minimum(preco + s, 1.0)
            com = jogar(t, ap_d, probs_d, bids, asks, rg, "rebalancear", final, faixas=FAIXAS_1T)
            linhas.append({"inicio": ini, "sua": ini == EQUIVALENTE_1T[regra.inicial], "favorita": ini == favorita,
                           "entrada": entrada, "spread": s, "com_trocas": com["valor"],
                           "segurar": regra.banca / entrada if ini == final else 0.0,
                           "ops": [{k2: o[k2] for k2 in ("t", "op", "faixa", "preco")} for o in com["ops"]]})
    return {"final": final, "t_entrada": float(t[0]), "linhas": linhas}


def main() -> None:
    p = carregar_params()
    d = noites(p)
    for inicial, entrada in (("F <4%", 0.405), ("F 4-8%", 0.325)):
        for ritmo in RITMOS:
            r = resumo(lote(d, Regra(inicial=inicial, entrada=entrada), ritmo, p.gl), 100.0)
            tab = pd.DataFrame(r["cenarios"]).round(2)
            print(f"\n### Começando em Sim \"{inicial}\" a {entrada * 100:.1f}¢, mercado {ritmo}\n")
            print(md(tab, index=False))
            for v, x in r["dist"].items():
                print(f"{v:12s} média US$ {x['media']:6.1f} | mediana US$ {x['mediana']:6.1f} | 10% piores ≤ US$ "
                      f"{x['p10']:6.1f} | prejuízo {x['prejuizo']:4.0%} | perde mais da metade {x['perde_metade']:4.0%}")
        real = noite_real_1t(Regra(inicial=inicial, entrada=entrada))
        print(f"\nNoite real do 1º turno (preços reais; venceu {real['final']}):")
        for ln in real["linhas"]:
            ops = "; ".join(f"{o['op']} {o['faixa']} a {o['preco'] * 100:.0f}¢" for o in ln["ops"]) or "sem trocas"
            print(f"  começa em {ln['inicio']:7s} a {ln['entrada'] * 100:4.1f}¢, ±{ln['spread'] * 100:.0f}¢: "
                  f"com trocas US$ {ln['com_trocas']:6.1f} | segurar US$ {ln['segurar']:6.1f} | {ops}")


if __name__ == "__main__":
    main()
