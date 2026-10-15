"""Gráficos e tabelas do backtest (real e simulado) para o README.

    python eleicao/relatorio.py

Lê resultados/sim_*.parquet (de rodar_simulacoes.py), roda as apurações reais de 2022 e
salva PNGs e tabelas em resultados/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apuracao import apurar  # noqa: E402
from backtest import GRADE, preparar, rodar  # noqa: E402
from modelo import NOMES_FAIXAS, Ordem1T, Params, prob_faixas, var_sistematica  # noqa: E402

RES = Path(__file__).resolve().parent / "resultados"
COR = {"azul": "#2a78d6", "laranja": "#eb6834", "aqua": "#1baf7a", "fundo": "#fcfcfb",
       "texto": "#0b0b0b", "texto2": "#52514e", "grade": "#e4e3df"}
CORTES = np.array([-12, -8, -4, 0, 4, 8, 12], float)


def md(df: pd.DataFrame, index: bool = True) -> str:
    """Tabela markdown simples (sem depender do pacote tabulate)."""
    d = df.reset_index() if index else df
    cab = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    fmt = lambda v: f"{v:.3g}" if isinstance(v, float) else str(v)  # noqa: E731
    linhas = ["| " + " | ".join(fmt(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([cab, sep] + linhas)


def estilo(ax, titulo: str, xl: str, yl: str) -> None:
    ax.set_facecolor(COR["fundo"])
    ax.figure.set_facecolor(COR["fundo"])
    ax.set_title(titulo, loc="left", fontsize=11, color=COR["texto"], pad=10)
    ax.set_xlabel(xl, color=COR["texto2"], fontsize=9)
    ax.set_ylabel(yl, color=COR["texto2"], fontsize=9)
    ax.tick_params(colors=COR["texto2"], labelsize=8)
    ax.grid(True, color=COR["grade"], linewidth=0.6)
    for s in ax.spines.values():
        s.set_visible(False)


def faixa_de(m: float) -> int:
    """Índice da faixa da Polymarket (na fronteira exata vale a de cima)."""
    return int(np.searchsorted(CORTES, m, side="right"))


def probs_df(df: pd.DataFrame, gl: float) -> np.ndarray:
    return np.vstack([prob_faixas(m, s, gl) for m, s in zip(df["mu"], df["sd"])])


def grafico_real(df: pd.DataFrame, titulo: str, arq: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    t = df["t"]
    ax.fill_between(t, df["mu"] - 1.96 * df["sd"], df["mu"] + 1.96 * df["sd"], color=COR["azul"],
                    alpha=0.15, linewidth=0)
    ax.plot(t, df["ingenuo"], color=COR["laranja"], linewidth=2)
    ax.plot(t, df["mu"], color=COR["azul"], linewidth=2)
    ax.axhline(df["final"].iloc[0], color=COR["texto2"], linewidth=1, linestyle="--")
    ax.set_ylim(-8, 8)
    ax.set_xlim(0, 180)
    estilo(ax, titulo, "minutos depois das 17h", "margem F − L (pontos)")
    y_ing = df.loc[df["t"] == 25, "ingenuo"]
    y_mod = df.loc[df["t"] == 25, "mu"]
    if len(y_ing):
        ax.annotate("parcial do TSE", (25, float(y_ing.iloc[0])), xytext=(30, 6.5), fontsize=8,
                    color=COR["texto"], arrowprops=dict(arrowstyle="-", color=COR["texto2"], lw=0.6))
    if len(y_mod):
        ax.annotate("modelo (faixa = 95%)", (25, float(y_mod.iloc[0])), xytext=(30, -6.8), fontsize=8,
                    color=COR["texto"], arrowprops=dict(arrowstyle="-", color=COR["texto2"], lw=0.6))
    ax.text(178, df["final"].iloc[0] - 0.7, "resultado final", ha="right", fontsize=8, color=COR["texto2"])
    fig.tight_layout()
    fig.savefig(RES / arq)
    plt.close(fig)


def tabela_real(df: pd.DataFrame) -> pd.DataFrame:
    pr = probs_df(df, Params().gl)
    certa = faixa_de(df["final"].iloc[0])
    linhas = []
    for t in [10, 15, 20, 30, 45, 60, 90, 120]:
        r = df[df["t"] <= t]
        if r.empty:
            continue
        i = r.index[-1]
        linhas.append({"hora": f"{17 + t // 60}:{t % 60:02d}", "apurado %": round(df.loc[i, "apurado"], 1),
                       "parcial TSE": round(df.loc[i, "ingenuo"], 2), "modelo": round(df.loc[i, "mu"], 2),
                       "± (1 dp)": round(df.loc[i, "sd"], 2), "final": round(df.loc[i, "final"], 2),
                       "P(faixa certa)": f"{pr[df.index.get_loc(i), certa] * 100:.0f}%"})
    return pd.DataFrame(linhas)


def sd_atual(d: pd.DataFrame, p: Params) -> pd.Series:
    """Recalcula a incerteza total com os parâmetros atuais. Os termos sistemáticos só somam
    variância no fim (não mudam a média nem a escolha de w), então isso equivale a rodar de novo."""
    return np.sqrt(p.k ** 2 * d["sd_bruto"] ** 2 + var_sistematica(1 - d["apurado"] / 100, p))


def metricas_sim(d: pd.DataFrame, gl: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = d.copy()
    d["err"] = d["mu"] - d["final"]
    d["z"] = d["err"] / d["sd"]
    d["err_ing"] = d["ingenuo"] - d["final"]
    fases = [0, 2, 5, 10, 20, 35, 50, 70, 90, 100]
    d["fase"] = pd.cut(d["apurado"], fases)
    g = d.groupby("fase", observed=True).agg(
        passos=("z", "size"),
        erro_parcial=("err_ing", lambda x: np.sqrt(np.mean(x ** 2))),
        erro_modelo=("err", lambda x: np.sqrt(np.mean(x ** 2))),
        dp_modelo=("sd", "median"),
        cobre_95=("z", lambda x: np.mean(np.abs(x) < 1.96)))
    # tempo até a faixa certa ficar acima de 90% (e não sair mais)
    linhas = []
    for sim, s in d.groupby("sim"):
        s = s.sort_values("t")
        pr = probs_df(s, gl)
        certa = faixa_de(s["final"].iloc[0])
        pc = pr[:, certa]
        ok = pc >= 0.9
        k = len(ok)
        while k > 0 and ok[k - 1]:
            k -= 1
        t90 = s["t"].iloc[k] if k < len(ok) else np.nan
        ap90 = s["apurado"].iloc[k] if k < len(ok) else np.nan
        tarde = s["t"] >= 15
        errada = pr[tarde.to_numpy()].copy()
        errada[:, certa] = 0
        linhas.append({"sim": sim, "final": s["final"].iloc[0],
                       "dist": float(np.min(np.abs(CORTES - s["final"].iloc[0]))),
                       "t90": t90, "apurado90": ap90, "max_errada": float(errada.max())})
    return g, pd.DataFrame(linhas)


def grafico_tempo(tt: pd.DataFrame, arq: str, titulo: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.scatter(tt["dist"], tt["t90"], s=22, color=COR["azul"], edgecolor=COR["fundo"], linewidth=1)
    ax.set_xlim(0, 2.05)
    estilo(ax, titulo, "distância da margem final até a fronteira de faixa mais próxima (pontos)",
           "minutos depois das 17h")
    fig.tight_layout()
    fig.savefig(RES / arq)
    plt.close(fig)


def grafico_confiabilidade(d: pd.DataFrame, gl: float, arq: str) -> pd.DataFrame:
    d = d[(d["apurado"] > 1) & (d["apurado"] < 98)]
    pr = probs_df(d, gl)
    certa = np.array([faixa_de(m) for m in d["final"]])
    acerto = np.zeros_like(pr)
    acerto[np.arange(len(d)), certa] = 1
    p, y = pr.ravel(), acerto.ravel()
    bins = np.array([0, 0.02, 0.1, 0.25, 0.4, 0.6, 0.75, 0.9, 0.98, 1.0001])
    i = np.digitize(p, bins) - 1
    tab = pd.DataFrame({"i": i, "p": p, "y": y}).groupby("i").agg(prev=("p", "mean"), obs=("y", "mean"), n=("y", "size"))
    fig, ax = plt.subplots(figsize=(4.6, 4.4), dpi=150)
    ax.plot([0, 1], [0, 1], color=COR["texto2"], linewidth=1, linestyle="--")
    ax.plot(tab["prev"], tab["obs"], color=COR["azul"], linewidth=2, marker="o", markersize=5)
    estilo(ax, "Probabilidade prevista × frequência real", "probabilidade da faixa (modelo)",
           "fração em que a faixa saiu")
    fig.tight_layout()
    fig.savefig(RES / arq)
    plt.close(fig)
    return tab


def main() -> None:
    RES.mkdir(exist_ok=True)
    p = Params()
    saida = []
    casos = [((2022, 2), (2022, 1), "real_2022_2t", True),
             ((2022, 1), (2022, 2), "real_2022_1t_inverso", True),
             ((2026, 1), (2022, 2), "real_2026_1t_base2022", False),
             ((2026, 1), (2022, 2), "real_2026_1t_base2022_ordem2022", True)]
    for alvo, base, nome, usa_ordem in casos:
        try:
            b, sec, munis, aptos, sb = preparar(alvo, base)
        except FileNotFoundError:
            continue
        if sec["t"].isna().mean() > 0.1:  # sem hora de chegada: não dá para reconstruir
            continue
        ap = apurar(sec, munis, GRADE)
        ordem = Ordem1T(sb, b) if (usa_ordem and sb is not None) else None
        df = rodar(b, aptos, ap, p, passos=range(0, 241, 1), ordem=ordem).reset_index(drop=True)
        df.to_csv(RES / f"{nome}.csv", index=False)
        grafico_real(df, f"Apuração real {alvo[1]}º turno {alvo[0]}: parcial × modelo", f"{nome}.png")
        saida.append(f"### {nome}\n\n" + md(tabela_real(df), index=False))
    for arq in sorted(RES.glob("sim_*.parquet")):
        d = pd.read_parquet(arq)
        d["sd"] = sd_atual(d, p)
        g, tt = metricas_sim(d, p.gl)
        nome = arq.stem
        grafico_tempo(tt, f"{nome}_tempo90.png", "Quando a faixa certa passa de 90% (e não cai mais)")
        tab = grafico_confiabilidade(d, p.gl, f"{nome}_confiabilidade.png")
        tt["dist_faixa"] = pd.cut(tt["dist"], [0, 0.25, 0.5, 1, 2, 99])
        resumo_t = tt.groupby("dist_faixa", observed=True).agg(
            sims=("sim", "size"), t90_mediana=("t90", "median"), apurado90_mediana=("apurado90", "median"),
            alarme_falso_80=("max_errada", lambda x: np.mean(x >= 0.8)))
        saida.append(f"### {nome}: erro por fase\n\n" + md(g.round(3)))
        saida.append(f"### {nome}: tempo até 90% na faixa certa\n\n" + md(resumo_t.round(2)))
        saida.append(f"### {nome}: confiabilidade\n\n" + md(tab.round(3)))
    (RES / "tabelas.md").write_text("\n\n".join(saida), encoding="utf-8")
    print("\n\n".join(saida))


if __name__ == "__main__":
    main()
