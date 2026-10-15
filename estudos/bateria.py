"""Bateria de testes: as estratégias lado a lado, nas mesmas noites, e onde cada uma tem viés.

    python eleicao/estudos/bateria.py      # grava resultados/bateria.md

Estratégias (todas começam com US$100):
  só vendem a posição que já têm: segurar até o fim; vender se a faixa de 90% sair da sua (desde
    2%); vender se a chance ficar ≤ 20% (desde 5% ou desde 20%); escalonada (⅓ a 30%, 15% e 5%);
    stop no preço (vende se o preço < 15¢);
  trade com posição: vende e compra a favorita do modelo (estudos/trade.py, regra padrão);
  trade em dinheiro: começa sem posição e só compra no sinal.
Mercados: os três ritmos de nucleo/mercado_sim.py (o preço vai atrás do modelo) e um "mercado que
sabe mais": o preço vem de uma estimativa com metade do erro do modelo, sem atraso.
Testes:
  1. resultado de cada estratégia em cada mercado;
  2. por cenário de resultado;
  3. viés do modelo por fase da apuração, nas simulações e nas apurações reais;
  4. direção dos erros: para que lado as estratégias erram;
  5. peso dos cenários: chances de hoje × todas as noites com o mesmo peso;
  6. parâmetros do trade escolhidos dentro × fora da amostra;
  7. apurações reais (2º turno de 2022, 1º de 2026) com preço simulado e a noite do 1º turno com
     o preço real da Polymarket.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do projeto
from estudos import trade  # noqa: E402
from estudos.banca import NOME_CURTO, REGRAS_BANCA  # noqa: E402
from estudos.estrategia import faixa_idx, toca_faixa  # noqa: E402
from estudos.relatorio import md, sd_atual  # noqa: E402
from nucleo.caminhos import RES  # noqa: E402
from nucleo.mercado_sim import ATRASO, PRECO_HOJE, RITMOS, precos  # noqa: E402
from nucleo.modelo import NOMES_FAIXAS, carregar_params, faixa_provavel  # noqa: E402

BANCA = 100.0
SABE_MAIS = "sabe mais que o modelo"
MERCADOS = [*RITMOS, SABE_MAIS]
BASE = "mais esperto"  # o mercado de referência das tabelas por cenário e de parâmetros
VENDA = [(NOME_CURTO[r.nome], r, None) for r in REGRAS_BANCA] + [(NOME_CURTO["stop no preço"], None, 0.15)]
TRADE = ["Trade com posição", "Trade em dinheiro"]
ESTRATEGIAS = [n for n, _, _ in VENDA] + TRADE
FASES = [0, 2, 5, 10, 20, 35, 50, 70, 90, 100.01]


# ---------- noites ----------
def preparar(t, ap, mu, sd, final, gl, nome) -> dict:
    """Uma noite com as chances do modelo e os preços de cada mercado."""
    probs = trade.probs_linhas(mu, sd, gl)
    mercados = {}
    for ritmo in RITMOS:
        b, a = zip(*(precos(p, tk, ritmo) for p, tk in zip(probs, t)))
        mercados[ritmo] = (np.array(b), np.array(a))
    # mercado que sabe mais: centro na metade do caminho entre o modelo e o resultado, sem atraso
    inf = trade.probs_linhas(final + 0.5 * (mu - final), sd, gl)
    mercados[SABE_MAIS] = (np.maximum(inf - 0.01, 0.0), np.minimum(inf + 0.01, 1.0))
    return {"nome": nome, "t": t, "ap": ap, "mu": mu, "sd": sd, "final": final,
            "fx": trade.faixa_de(final), "probs": probs, "mercados": mercados}


def noites_sim(p) -> list[dict]:
    d = trade.noites(p)
    out = []
    for sim, g in d.groupby("sim"):
        g = g.sort_values("t")
        out.append(preparar(g["t"].to_numpy(float), g["apurado"].to_numpy(float), g["mu"].to_numpy(float),
                            g["sd"].to_numpy(float), float(g["final"].iloc[0]), p.gl, sim))
    return out


def noites_reais(p) -> list[dict]:
    """As apurações reais com hora do BU, com o modelo de hoje (incerteza recalculada)."""
    out = []
    for arq, nome in (("real_2022_2t", "2º turno de 2022"), ("real_2026_1t_base2022", "1º turno de 2026")):
        d = pd.read_csv(RES / f"{arq}.csv").dropna(subset=["mu"]).sort_values("t")
        d["sd"] = sd_atual(d, p)
        out.append(preparar(d["t"].to_numpy(float), d["apurado"].to_numpy(float), d["mu"].to_numpy(float),
                            d["sd"].to_numpy(float), float(d["final"].iloc[0]), p.gl, nome))
    return out


# ---------- estratégias ----------
def vendas_regra(regra, pp, ap, toca, mid, stop) -> np.ndarray:
    """Fração acumulada vendida em cada passo (igual a banca.valor_por_cota)."""
    if stop is not None:
        return np.maximum.accumulate(((ap >= 0) & (mid < stop)).astype(float))
    if regra is None or not regra.degraus:
        return np.zeros(len(pp))
    return regra.vendas(pp, ap, toca)


def jogar_noite(n: dict, pos: str, mercado: str, gl: float) -> list[dict]:
    bids, asks = n["mercados"][mercado]
    i, entrada = faixa_idx(pos), PRECO_HOJE[pos]
    cotas, ganha = BANCA / entrada, n["fx"] == pos
    pp, mid = n["probs"][:, i], (bids[:, i] + asks[:, i]) / 2
    toca = toca_faixa(n["mu"], n["sd"], gl, i)
    out = []
    for nome, regra, stop in VENDA:
        v = vendas_regra(regra, pp, n["ap"], toca, mid, stop)
        frac = np.diff(np.concatenate([[0.0], v]))
        receita = float(np.sum(frac * np.maximum(mid - 0.01, 0.0)))
        valor = (receita + (1.0 - float(v[-1])) * (1.0 if ganha else 0.0)) * cotas
        k = int(np.argmax(v > 0)) if (v > 0).any() else None
        out.append({"estrategia": nome, "valor": valor, "operou": k is not None, "k": k, "termina_em": None,
                    "compra": None})
    for nome, rg in (("Trade com posição", trade.Regra(inicial=pos, entrada=entrada)),
                     ("Trade em dinheiro", trade.Regra(inicial=None))):
        r = trade.jogar(n["t"], n["ap"], n["probs"], bids, asks, rg, "rebalancear", n["fx"])
        compras = [o for o in r["ops"] if o["op"] == "compra"]
        out.append({"estrategia": nome, "valor": r["valor"], "operou": bool(r["ops"]),
                    "k": r["ops"][0]["k"] if r["ops"] else None, "termina_em": r["termina_em"],
                    "compra": compras[0]["faixa"] if compras else None})
    for o in out:
        o.update(noite=n["nome"], final=n["final"], fx=n["fx"], pos=pos, mercado=mercado)
    return out


# ---------- estatísticas ----------
def estat(x: np.ndarray, w: np.ndarray) -> dict:
    return {"média": float(np.sum(w * x)), "mediana": trade.quantil(x, w, 0.5), "10% piores": trade.quantil(x, w, 0.1),
            "prejuízo": float(np.sum(w[x < BANCA])), "perde > metade": float(np.sum(w[x < BANCA / 2]))}


def pesos_de(av: pd.DataFrame, modo: str) -> np.ndarray:
    return trade.pesos(av) if modo == "hoje" else np.full(len(av), 1 / len(av))


def tabela_resultados(R: pd.DataFrame, pos: str, modo: str = "hoje") -> pd.DataFrame:
    linhas = []
    for (mercado, est), g in R[R["pos"] == pos].groupby(["mercado", "estrategia"], sort=False):
        s = estat(g["valor"].to_numpy(float), pesos_de(g, modo))
        linhas.append({"mercado": mercado, "estratégia": est, **s, "operou": float(np.sum(pesos_de(g, modo)[g["operou"].to_numpy()]))})
    return pd.DataFrame(linhas)


def fmt_tabela(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    for c in ("média", "mediana", "10% piores"):
        if c in t:
            t[c] = t[c].map(lambda x: f"US$ {x:,.0f}".replace(",", "."))
    for c in ("prejuízo", "perde > metade", "operou"):
        if c in t:
            t[c] = t[c].map(lambda x: f"{x:.0%}")
    return t


# ---------- testes de viés ----------
def vies_modelo(nomes_dfs: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    """Erro médio (modelo − resultado) por fase da apuração: > 0 = puxa para Flávio."""
    linhas = []
    for nome, d in nomes_dfs:
        e = d["mu"] - d["final"]
        fase = pd.cut(d["apurado"], FASES, right=False)
        g = pd.DataFrame({"fase": fase, "e": e, "z": e / d["sd"]}).groupby("fase", observed=True)
        for f, x in g:
            linhas.append({"apuração": nome, "apurado": f"{f.left:g}–{min(f.right, 100):g}%",
                           "erro médio (pp)": round(float(x["e"].mean()), 2),
                           "erro típico (pp)": round(float(np.sqrt((x["e"] ** 2).mean())), 2),
                           "puxa para F": f"{float((x['e'] > 0).mean()):.0%}",
                           "|z| > 1,64": f"{float((x['z'].abs() > 1.645).mean()):.0%}"})
    return pd.DataFrame(linhas)


def direcao(R: pd.DataFrame, noites: dict) -> pd.DataFrame:
    """Para que lado cada estratégia erra (mercado de referência, posição F <4%)."""
    linhas = []
    g0 = R[(R["mercado"] == BASE) & (R["pos"] == "F <4%")]
    for est, g in g0.groupby("estrategia", sort=False):
        w = trade.pesos(g)
        cats = []
        for _, o in g.iterrows():
            n = noites[o["noite"]]
            if est in TRADE:
                alvo = o["compra"] if est == "Trade em dinheiro" else o["termina_em"]
                if not (isinstance(alvo, str) and alvo in NOMES_FAIXAS):  # None vira NaN no DataFrame
                    cats.append("não comprou" if est == "Trade em dinheiro" else "terminou em dinheiro")
                else:
                    dif = NOMES_FAIXAS.index(alvo) - NOMES_FAIXAS.index(o["fx"])
                    cats.append("faixa certa" if dif == 0 else "errou para Flávio" if dif > 0 else "errou para Lula")
            else:
                ganha = o["fx"] == "F <4%"
                if not o["operou"]:
                    cats.append("segurou e ganhou" if ganha else "segurou e perdeu")
                elif not ganha:
                    cats.append("vendeu e a faixa perdeu")
                else:  # vendeu uma posição que ia ganhar: o modelo errou para que lado?
                    e = n["mu"][int(o["k"])] - o["final"]
                    cats.append("vendeu à toa (modelo puxava para F)" if e > 0 else "vendeu à toa (modelo puxava para L)")
        c = pd.Series(cats)
        for cat in c.unique():
            linhas.append({"estratégia": est, "resultado": cat, "noites": f"{float(np.sum(w[(c == cat).to_numpy()])):.0%}"})
    return pd.DataFrame(linhas)


def por_cenario(R: pd.DataFrame, pos: str) -> pd.DataFrame:
    g0 = R[(R["mercado"] == BASE) & (R["pos"] == pos)]
    linhas = []
    for nome, lo, hi in trade.CENARIOS:
        g = g0[(g0["final"] >= lo) & (g0["final"] < hi)]
        if g.empty:
            continue
        linha = {"cenário": nome, "noites": g["noite"].nunique()}
        for est in ESTRATEGIAS:
            linha[est] = f"US$ {g[g['estrategia'] == est]['valor'].mean():,.0f}".replace(",", ".")
        linhas.append(linha)
    return pd.DataFrame(linhas)


def parametros(noites: list[dict], gl: float) -> pd.DataFrame:
    """Escolhe os parâmetros do trade na metade A das noites e mede na B (e vice-versa)."""
    grade = list(itertools.product((0.6, 0.7, 0.8, 0.9), (0.0, 0.05, 0.10), (2.0, 5.0, 10.0), (1, 2)))
    finais = pd.DataFrame({"final": [n["final"] for n in noites]})
    metades = {"A": np.arange(len(noites)) % 2 == 0, "B": np.arange(len(noites)) % 2 == 1}
    linhas = []
    for variante, inicial in (("Trade com posição", "F <4%"), ("Trade em dinheiro", None)):
        valores = {}
        for lim, van, ap_min, mx in grade:
            rg = trade.Regra(inicial=inicial, entrada=PRECO_HOJE["F <4%"], limiar=lim, vantagem=van,
                             apurado_min=ap_min, max_trocas=mx)
            valores[(lim, van, ap_min, mx)] = np.array([
                trade.jogar(n["t"], n["ap"], n["probs"], *n["mercados"][BASE], rg, "rebalancear", n["fx"])["valor"]
                for n in noites])

        def nota(v, m):
            sub = finais[m].reset_index(drop=True)
            return float(np.sum(trade.pesos(sub) * v[m]))

        padrao = (0.7, 0.05, 2.0, 2)
        for dentro, fora in (("A", "B"), ("B", "A")):
            melhor = max(grade, key=lambda c: nota(valores[c], metades[dentro]))
            linhas.append({"variante": variante, "escolhida em": dentro,
                           "parâmetros": f"limiar {melhor[0]:.0%}, vantagem {melhor[1] * 100:.0f} pts, desde {melhor[2]:g}%, {melhor[3]} troca(s)",
                           "média dentro": f"US$ {nota(valores[melhor], metades[dentro]):.0f}",
                           "média fora": f"US$ {nota(valores[melhor], metades[fora]):.0f}",
                           "padrão dentro": f"US$ {nota(valores[padrao], metades[dentro]):.0f}",
                           "padrão fora": f"US$ {nota(valores[padrao], metades[fora]):.0f}"})
    return pd.DataFrame(linhas)


def limiares(sims: list[dict], reais: list[dict]) -> pd.DataFrame:
    """O limiar de confiança do trade contra o viés pró-Flávio da noite real do 1º turno de 2026."""
    finais = pd.DataFrame({"final": [n["final"] for n in sims]})
    w = trade.pesos(finais)
    colunas = [("como em 4/10", None), (BASE, None), (SABE_MAIS, None), (BASE, "2º turno de 2022"),
               ("como em 4/10", "1º turno de 2026"), (SABE_MAIS, "1º turno de 2026")]
    linhas = []
    for variante, inicial in (("Trade em dinheiro", None), ("Trade com posição", "F <4%")):
        for lim in (0.6, 0.7, 0.8, 0.9):
            rg = trade.Regra(inicial=inicial, entrada=PRECO_HOJE["F <4%"], limiar=lim)
            linha = {"variante": variante, "limiar": f"{lim:.0%}"}
            for m, real in colunas:
                if real is None:
                    v = np.array([trade.jogar(n["t"], n["ap"], n["probs"], *n["mercados"][m], rg, "rebalancear", n["fx"])["valor"]
                                  for n in sims])
                    linha[f"simulações, {m}"] = f"US$ {np.sum(w * v):.0f} ({np.sum(w[v < BANCA]):.0%} prejuízo)"
                else:
                    n = next(x for x in reais if x["nome"] == real)
                    r = trade.jogar(n["t"], n["ap"], n["probs"], *n["mercados"][m], rg, "rebalancear", n["fx"])
                    linha[f"{real}, {m}"] = f"US$ {r['valor']:.0f}"
            linhas.append(linha)
    return pd.DataFrame(linhas)


def noite_1t_venda(p) -> pd.DataFrame:
    """Regras de venda na noite real do 1º turno, com os preços reais (faixas de 5 pontos)."""
    from estudos.comparar_mercado import CORTES as CORTES_1T, FAIXAS as FAIXAS_1T
    r = pd.read_csv(RES / "mercado_1t_modelo_antes.csv").sort_values("t")
    t, ap = r["t"].to_numpy(float), r["apurado"].to_numpy(float)
    k = np.maximum(np.searchsorted(t, t - ATRASO, side="right") - 1, 0)  # o modelo decide com 5 min de atraso
    lo, hi = faixa_provavel(r["mu_mercado"].to_numpy(float), r["sd_mercado"].to_numpy(float), p.gl, 0.9)
    bordas = np.concatenate([[-np.inf], CORTES_1T, [np.inf]])
    linhas = []
    for pos in ("F <5%", "L <5%"):
        i = FAIXAS_1T.index(pos)
        pp = r[f"mod_{pos}"].to_numpy(float)[k]
        toca = ((hi >= bordas[i]) & (lo < bordas[i + 1]))[k]
        mid = r[f"bruto_{pos}"].to_numpy(float)
        cotas, ganha = BANCA / mid[0], pos == "F <5%"
        for nome, regra, stop in VENDA:
            v = vendas_regra(regra, pp, ap[k], toca, mid, stop)
            frac = np.diff(np.concatenate([[0.0], v]))
            valor = (float(np.sum(frac * np.maximum(mid - 0.01, 0.0))) + (1 - float(v[-1])) * (1.0 if ganha else 0.0)) * cotas
            j = int(np.argmax(v > 0)) if (v > 0).any() else None
            quando = f"vendeu às {17 + int(t[j] // 60)}h{int(t[j] % 60):02d} a {(mid[j] - 0.01) * 100:.0f}¢" if j is not None else "não vendeu"
            linhas.append({"posição": f"{pos} ({'ganhou' if ganha else 'perdeu'})", "estratégia": nome,
                           "valor": f"US$ {valor:.0f}", "o que fez": quando})
    return pd.DataFrame(linhas)


def main() -> None:
    p = carregar_params()
    sims, reais = noites_sim(p), noites_reais(p)
    por_nome = {n["nome"]: n for n in sims + reais}
    R = pd.DataFrame([o for n in sims for pos in ("F <4%", "F 4-8%") for m in MERCADOS for o in jogar_noite(n, pos, m, p.gl)])
    Rr = pd.DataFrame([o for n in reais for m in MERCADOS for o in jogar_noite(n, "F <4%", m, p.gl)])
    partes = ["# Bateria de testes das estratégias",
              "Gerado por `estudos/bateria.py`. Todas começam com US$100; posição comprada ao preço de hoje "
              "(F <4% a 40,5¢, F 4-8% a 32,5¢). Média, mediana e prejuízo pesam cada noite pela chance que o "
              "mercado dá hoje ao cenário dela. Mercados: os três ritmos (o preço vai atrás do modelo) e um "
              "que sabe mais que o modelo (metade do erro dele, sem atraso)."]
    for pos in ("F <4%", "F 4-8%"):
        t = tabela_resultados(R, pos)
        partes.append(f"## 1. Resultado por mercado — começando em Sim \"{pos}\"\n\n" + md(fmt_tabela(t), index=False))
    partes.append(f"## 2. Por cenário (mercado \"{BASE}\", Sim \"F <4%\")\n\n" + md(por_cenario(R, "F <4%"), index=False))
    sims_df = pd.concat([pd.DataFrame({"apurado": n["ap"], "mu": n["mu"], "sd": n["sd"], "final": n["final"]}) for n in sims])
    reais_dfs = [(n["nome"], pd.DataFrame({"apurado": n["ap"], "mu": n["mu"], "sd": n["sd"], "final": n["final"]})) for n in reais]
    partes.append("## 3. Viés do modelo por fase da apuração\n\nErro = margem prevista − resultado (> 0: puxa para "
                  "Flávio). |z| > 1,64 deveria acontecer ~10% das vezes se a incerteza estiver certa.\n\n"
                  + md(vies_modelo([("simulações", sims_df), *reais_dfs]), index=False))
    partes.append(f"## 4. Para que lado as estratégias erram (mercado \"{BASE}\", Sim \"F <4%\")\n\n" + md(direcao(R, por_nome), index=False))
    ranks = []
    for modo, nome in (("hoje", "chances de hoje"), ("iguais", "todas as noites iguais")):
        t = tabela_resultados(R, "F <4%", modo)
        t = t[t["mercado"] == BASE].sort_values("média", ascending=False)
        ranks.append(t.assign(peso=nome)[["peso", "estratégia", "média", "mediana", "prejuízo"]])
    partes.append(f"## 5. Peso dos cenários (mercado \"{BASE}\", Sim \"F <4%\")\n\n" + md(fmt_tabela(pd.concat(ranks)), index=False))
    partes.append(f"## 6. Parâmetros do trade: dentro × fora da amostra (mercado \"{BASE}\")\n\n" + md(parametros(sims, p.gl), index=False))
    tr = Rr.groupby(["noite", "mercado", "estrategia"], sort=False)["valor"].first().unstack("mercado")[MERCADOS]
    tr = tr.map(lambda x: f"US$ {x:,.0f}".replace(",", ".")).reset_index().rename(columns={"noite": "apuração", "estrategia": "estratégia"})
    finais = ", ".join(f"{n['nome']}: {n['fx']} (F {n['final']:+.1f})" for n in reais)
    partes.append(f"## 7. Apurações reais, com preço simulado (começando em Sim \"F <4%\")\n\nResultados: {finais}.\n\n" + md(tr, index=False))
    partes.append("### Noite real do 1º turno com os preços reais da Polymarket (faixas de 5 pontos)\n\n" + md(noite_1t_venda(p), index=False))
    real_trade = []
    for rg in (trade.Regra(inicial="F <4%", entrada=0.405), trade.Regra(inicial=None)):
        for ln in trade.noite_real_1t(rg)["linhas"]:
            if ln["spread"] == 0.01:
                ops = "; ".join(f"{o['op']} {o['faixa']} a {o['preco'] * 100:.0f}¢" for o in ln["ops"]) or "não operou"
                real_trade.append({"estratégia": "Trade em dinheiro" if rg.inicial is None else "Trade com posição",
                                   "começa em": ln["inicio"], "valor": f"US$ {ln['com_trocas']:.0f}", "o que fez": ops})
    partes.append(md(pd.DataFrame(real_trade), index=False))
    partes.append("## 8. Limiar de confiança do trade × o viés pró-Flávio\n\nNo 1º turno de 2026 o modelo ficou ~2 pontos "
                  "pró-Flávio por horas (seção 3). Com limiar baixo, o trade compra \"F 4-8%\" nesse erro; com limiar mais "
                  "alto, ele espera. Começando em Sim \"F <4%\" (com posição) ou em dinheiro.\n\n" + md(limiares(sims, reais), index=False))
    (RES / "bateria.md").write_text("\n\n".join(partes) + "\n", encoding="utf-8")
    print("\n\n".join(partes))


if __name__ == "__main__":
    main()
