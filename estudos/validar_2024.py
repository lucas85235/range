"""Valida a ordem de chegada do 1º turno (peso w do modelo) nos 2ºs turnos de prefeito de 2024.

O modelo ao vivo (modelo.Ordem1T) supõe que a parte já apurada de cada município tem composição
X(w) = média + w * (primeiras seções pela ordem do 1º turno - média). A priori de w
(calibracao.json) veio quase só do 2º turno de 2022. Cada uma das 51 cidades com 2º turno de
prefeito em 2024 é um teste independente, com o mesmo sistema de transmissão do TSE.

Para cada cidade, refaz a apuração do 2º turno pela hora do BU e, com 10, 25, 50 e 75% das
seções apuradas, mede:
  - w_comp: o w que faz a composição prevista da parte apurada bater com a real (votos do 1º
    turno das seções que de fato já chegaram), comparadas pela margem que cada uma implica;
  - a projeção da margem final da cidade com vários w, e w_proj, o w que a acerta. Projeção =
    o cálculo do modelo com psi = 1: parte apurada + parte restante com a mesma taxa por
    eleitor da apurada, corrigida pela diferença de composição prevista entre as duas. Com
    w = 0 ela é a própria parcial.

Categorias do 1º turno (como no modelo): os dois finalistas (F = o mais votado no 1º turno),
cada outro candidato com >= 1% dos válidos, demais, brancos+nulos e abstenção. A transferência
b vem de uma regressão por seção dentro da cidade (2º turno sobre 1º) e usa o resultado final:
é um oráculo, para isolar o efeito de w do de b.

Erro-padrão de w por cidade: o que se teria se os locais de votação (que chegam juntos)
chegassem em ordem aleatória. Com ele, a dispersão de w entre cidades é separada do ruído
(efeitos aleatórios, DerSimonian-Laird).

    python eleicao/estudos/validar_2024.py      # grava resultados/validacao_2024.csv, _tabelas.md e _w.png
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do projeto
from nucleo.apuracao import apurar  # noqa: E402
from nucleo.caminhos import DADOS, RES  # noqa: E402
from nucleo.modelo import Ordem1T, carregar_params  # noqa: E402

DIA = {1: "2024-10-06", 2: "2024-10-27"}
PONTOS = (0.10, 0.25, 0.50, 0.75)
BRANCO, NULO = 95, 96
SIGLAS = {10: "REPUBLICANOS", 11: "PP", 12: "PDT", 13: "PT", 15: "MDB", 16: "PSTU", 18: "REDE",
          20: "PODE", 21: "PCB", 22: "PL", 23: "CIDADANIA", 25: "PRD", 27: "DC", 28: "PRTB",
          29: "PCO", 30: "NOVO", 33: "MOBILIZA", 35: "PMB", 36: "AGIR", 40: "PSB", 43: "PV",
          44: "UNIÃO", 45: "PSDB", 50: "PSOL", 55: "PSD", 65: "PCdoB", 70: "AVANTE",
          77: "SOLIDARIEDADE", 80: "UP"}


def ler(turno: int) -> pd.DataFrame:
    df = pd.read_parquet(DADOS / f"bu_2024_{turno}t_prefeito.parquet")
    df["t"] = (df["dt_bu"] - pd.Timestamp(f"{DIA[turno]} 17:00")).dt.total_seconds() / 60
    return df


def numeros(df: pd.DataFrame) -> list[int]:
    """Números com voto na cidade (o parquet tem colunas de todos os partidos da UF)."""
    return [int(c[1:]) for c in df.columns if c.startswith("v") and c[1:].isdigit() and df[c].sum() > 0]


def montar(c1: pd.DataFrame, c2: pd.DataFrame) -> dict:
    """Seções da cidade no formato do modelo: s1 (1º turno, para Ordem1T), base e s2 (2º turno),
    mais a matriz de categorias do 1º turno (K, na ordem de Ordem1T) casada com o 2º."""
    cd = int(c2["cd_mun"].iloc[0])
    nom1 = [n for n in numeros(c1) if n not in (BRANCO, NULO)]
    tot1 = {n: float(c1[f"v{n}"].sum()) for n in nom1}
    fin = [n for n in numeros(c2) if n not in (BRANCO, NULO)]
    if len(fin) != 2:
        raise ValueError(f"{cd}: {len(fin)} candidatos com voto no 2º turno")
    F, L = sorted(fin, key=lambda n: -tot1.get(n, 0.0))
    V1 = sum(tot1.values())
    outros = [n for n in sorted(tot1, key=lambda n: -tot1[n]) if n not in (F, L) and tot1[n] / V1 >= 0.01]

    def bn(df):
        return sum(df[f"v{n}"] for n in (BRANCO, NULO) if f"v{n}" in df.columns)

    s1 = c1[["cd_mun", "zona", "secao", "t", "aptos"]].copy()
    s1["F"], s1["L"] = c1[f"v{F}"], c1[f"v{L}"]
    s1["O"] = c1[[f"v{n}" for n in nom1]].sum(axis=1) - s1["F"] - s1["L"]
    s1["BN"] = bn(c1)
    s1["C"] = s1["F"] + s1["L"] + s1["O"] + s1["BN"]
    for n in outros:
        s1[f"v{n}"] = c1[f"v{n}"]
    base = pd.DataFrame({"uf": c1["uf"].iloc[0], "F1": s1["F"].sum(), "L1": s1["L"].sum(),
                         "O1": s1["O"].sum(), "BN1": s1["BN"].sum(), "C1": s1["C"].sum()}
                        | {f"o{n}": s1[f"v{n}"].sum() for n in outros},
                        index=pd.Index([cd], name="cd_mun"))
    nomes = ["F1", "L1"] + [f"o{n}" for n in outros] + ["Orest", "BN1", "ABS1"]
    K = np.column_stack([s1["F"], s1["L"]] + [s1[f"v{n}"] for n in outros]
                        + [s1["O"] - sum(s1[f"v{n}"] for n in outros), s1["BN"],
                           np.maximum(s1["aptos"] - s1["C"], 0)]).astype(float)
    s2 = c2[["cd_mun", "zona", "secao", "local", "t", "aptos"]].copy()
    s2["F"], s2["L"] = c2[f"v{F}"], c2[f"v{L}"]
    s2["BN"] = bn(c2)
    s2["C"] = s2["F"] + s2["L"] + s2["BN"]
    k1 = pd.DataFrame(K, columns=nomes, index=s1.index)
    k1["zona"], k1["secao"], k1["aptos1"], k1["t1"] = s1["zona"], s1["secao"], s1["aptos"], s1["t"]
    m = s2.merge(k1, on=["zona", "secao"], how="left", validate="one_to_one")
    return dict(cd=cd, F=F, L=L, outros=outros, nomes=nomes, s1=s1, base=base, s2=s2, m=m,
                m1=100 * (tot1[F] - tot1[L]) / (tot1[F] + tot1[L]))


def transferencia(X: np.ndarray, y: np.ndarray, ap: np.ndarray, b0: np.ndarray, s1: float,
                  tau_b: float) -> np.ndarray:
    """b por seção, dentro da cidade: MQP com variância s1²/aptos e a priori do modelo."""
    w = ap / s1 ** 2
    H = X.T @ (X * w[:, None]) + np.eye(X.shape[1]) / tau_b ** 2
    return np.linalg.solve(H, X.T @ (w * y) + b0 / tau_b ** 2)


def var_aleatoria(A: np.ndarray, z: np.ndarray, f: float) -> float:
    """Variância da média de z (ponderada por A) numa amostra aleatória simples de uma fração f
    das unidades (estimador de razão, com correção de população finita)."""
    N = len(A)
    zb = np.sum(A * z) / np.sum(A)
    S2 = np.sum((A * (z - zb)) ** 2) / max(N - 1, 1)
    return (1 - f) / (f * N) * S2 / np.mean(A) ** 2


def avaliar(d: dict, p) -> list[dict]:
    """Uma linha por ponto da apuração (10/25/50/75% das seções)."""
    m, nomes = d["m"], d["nomes"]
    casou = m["aptos1"].notna().to_numpy()
    K = m.loc[casou, nomes].to_numpy(float)
    a1 = m.loc[casou, "aptos1"].to_numpy(float)
    F2, L2, a2 = (m.loc[casou, c].to_numpy(float) for c in ("F", "L", "aptos"))
    # transferência "oráculo": seções com eleitorado razoável nos dois turnos
    ok = (a1 >= 20) & (a2 >= 20)
    X = K[ok] / a1[ok, None]
    b0_D = np.array([1.0 if n == "F1" else -1.0 if n == "L1" else 0.0 for n in nomes])
    b0_S = np.array([1.0 if n in ("F1", "L1") else 0.5 if n.startswith("o") or n == "Orest" else 0.1
                     for n in nomes])
    bD = transferencia(X, (F2 - L2)[ok] / a2[ok], a2[ok], b0_D, p.s1_D, p.tau_b)
    bS = transferencia(X, (F2 + L2)[ok] / a2[ok], a2[ok], b0_S, p.s1_S, p.tau_b)
    # conferência sem b: só o duelo F1 × L1 do 1º turno
    eF, eL = (np.array([n == c for n in nomes], float) for c in ("F1", "L1"))
    bases = {"": (bD, bS), "_h": (eF - eL, eF + eL)}

    def mi(Xc, b=(bD, bS)):  # margem implícita (pontos) de uma composição do 1º turno
        return 100 * (Xc @ b[0]) / (Xc @ b[1])

    s2, base = d["s2"], d["base"]
    ordem = Ordem1T(d["s1"], base)
    tt = np.sort(s2["t"].to_numpy())
    tempos = np.array([tt[math.ceil(q * len(tt)) - 1] for q in PONTOS])
    ap = apurar(s2, base.index, tempos)
    A2 = float(ap["tot"]["aptos"][0])
    Dfin = float(ap["tot"]["F"][0] - ap["tot"]["L"][0])
    Sfin = float(ap["tot"]["F"][0] + ap["tot"]["L"][0])
    mfin = 100 * Dfin / Sfin
    # unidades de ruído: locais de votação (as seções de um local chegam juntas)
    u = m.loc[casou, ["zona", "local"]].astype(str).agg("-".join, axis=1).to_numpy()
    _, iu = np.unique(u, return_inverse=True)
    soma = lambda v: np.bincount(iu, weights=v)  # noqa: E731
    Ku = np.column_stack([soma(K[:, i]) for i in range(K.shape[1])])
    A1u, A2u = soma(a1), soma(a2)
    vu = 100 * (soma(F2 - L2) - mfin / 100 * soma(F2 + L2)) / A2u / (Sfin / A2)
    t1, t2 = m.loc[casou, "t1"], m.loc[casou, "t"]
    rho = float(t1.rank().corr(t2.rank()))
    linhas = []
    for k, q in enumerate(PONTOS):
        Fc, Lc, Ac, Nc = (float(ap[c][k, 0]) for c in ("F", "L", "aptos", "nsec"))
        pi = Ac / A2
        Xc1, Xr1, Xm = (x[0] for x in ordem.partes(np.array([pi])))
        cont = (m.loc[casou, "t"] <= tempos[k]).to_numpy()
        Xc_real = K[cont].sum(0) / a1[cont].sum()
        Xr_real = K[~cont].sum(0) / a1[~cont].sum()
        r = mi(Xc_real) / 100
        dD, dS = (Xc1 - Xm) @ bD, (Xc1 - Xm) @ bS
        w_comp = (r * (Xm @ bS) - Xm @ bD) / (dD - r * dS)
        # projeção da margem final: 100 (N0 + w N1) / (Q0 + w Q1)
        Dc, Sc, Ar = Fc - Lc, Fc + Lc, A2 - Ac
        d1 = Xr1 - Xc1
        N0, Q0 = Dc + Ar * Dc / Ac, Sc + Ar * Sc / Ac
        N1, Q1 = Ar * (d1 @ bD), Ar * (d1 @ bS)
        dr = Xr_real - Xc_real
        oraculo = 100 * (N0 + Ar * (dr @ bD)) / (Q0 + Ar * (dr @ bS))
        mf = mfin / 100
        w_proj = (mf * Q0 - N0) / (N1 - mf * Q1)
        # viés de composição da parte apurada (pontos de margem implícita): previsto pela ordem
        # do 1º turno (w = 1) e real; variância se os locais chegassem em ordem aleatória
        vies, Xu = {}, Ku / A1u[:, None] - Xm
        for suf, b in bases.items():
            mm = mi(Xm, b)
            qu = 100 * (Xu @ b[0] - mm / 100 * (Xu @ b[1])) / (Xm @ b[1])
            vies |= {f"B1{suf}": mi(Xc1, b) - mm, f"Br{suf}": mi(Xc_real, b) - mm,
                     f"var_comp{suf}": var_aleatoria(A1u, qu, pi)}
        # a mesma variância como o modelo a calcula (Ordem1T.var_composicao): seções sorteadas
        Xs = K / np.maximum(a1, 1.0)[:, None] - Xm
        qs = 100 * (Xs @ bD - mi(Xm) / 100 * (Xs @ bS)) / (Xm @ bS)
        vies["var_comp_sec"] = np.average((qs - np.average(qs, weights=a1)) ** 2, weights=a1) \
            * (1 - pi) / (pi * len(qs))
        linhas.append(dict(
            cd_mun=d["cd"], p=q, t=tempos[k], secoes=Nc / ap["tot"]["nsec"][0], pi=pi,
            parcial=100 * Dc / Sc, final=mfin, **vies, w_comp=w_comp, e0=100 * Dc / Sc - mfin,
            inc=100 * (N0 + N1) / (Q0 + Q1) - 100 * N0 / Q0, w_proj=w_proj,
            var_proj=var_aleatoria(A2u, vu, pi), e_oraculo=oraculo - mfin,
            N0=N0, Q0=Q0, N1=N1, Q1=Q1, rho=rho, casou=casou.mean(),
            n_locais=len(A1u), n_secoes=len(m), aptos=A2, validos=Sfin, m1=d["m1"],
            F=d["F"], L=d["L"], n_outros=len(d["outros"])))
    return linhas


def projetar(r: pd.DataFrame | pd.Series, w) -> np.ndarray:
    return 100 * (r["N0"] + w * r["N1"]) / (r["Q0"] + w * r["Q1"]) - r["final"]


def efeitos_aleatorios(est: np.ndarray, var: np.ndarray) -> dict:
    """DerSimonian-Laird: média e dispersão verdadeira (tau) entre cidades."""
    w = 1 / var
    mu_fe = np.sum(w * est) / np.sum(w)
    Q = float(np.sum(w * (est - mu_fe) ** 2))
    c = np.sum(w) - np.sum(w ** 2) / np.sum(w)
    tau2 = max(0.0, (Q - (len(est) - 1)) / c)
    wr = 1 / (var + tau2)
    return dict(mu=float(np.sum(wr * est) / np.sum(wr)), ep=float(np.sqrt(1 / np.sum(wr))),
                tau=math.sqrt(tau2), Q=Q, gl=len(est) - 1)


def por_cidade(df: pd.DataFrame) -> pd.DataFrame:
    """w de cada cidade (MQO sobre os 4 pontos) e erro-padrão com a covariância dos pontos
    aninhados: cov(k, l) = var do ponto com mais seções."""
    S_all = float(np.sum(df["inc"] * df["e0"]))
    SS_all = float(np.sum(df["inc"] ** 2))
    linhas = []
    for cd, g in df.groupby("cd_mun", sort=False):
        out = {"cd_mun": cd}
        for nome, x, y, v, sinal in (("comp", "B1", "Br", "var_comp", 1), ("comp_h", "B1_h", "Br_h", "var_comp_h", 1),
                                     ("proj", "inc", "e0", "var_proj", -1)):
            a, b = g[x].to_numpy(), g[y].to_numpy()
            C = np.minimum.outer(g[v].to_numpy(), g[v].to_numpy())
            out[f"wc_{nome}"] = sinal * float(a @ b / (a @ a))
            out[f"ep_{nome}"] = float(math.sqrt(a @ C @ a) / (a @ a))
        S_c, SS_c = float(np.sum(g["inc"] * g["e0"])), float(np.sum(g["inc"] ** 2))
        out["w_fora"] = -(S_all - S_c) / (SS_all - SS_c)   # agrupado sem a própria cidade
        linhas.append(out)
    return pd.DataFrame(linhas)


def num(v, casas: int = 2, sinal: bool = True) -> str:
    """Número no estilo do README: vírgula decimal e sinal de menos tipográfico."""
    if v is None or not np.isfinite(v):
        return "–"
    return (f"{v:+.{casas}f}" if sinal else f"{v:.{casas}f}").replace("-", "−").replace(".", ",")


def md(df: pd.DataFrame) -> str:
    cab = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    return "\n".join([cab, sep] + ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)])


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def resumo(df: pd.DataFrame, info: dict, p) -> str:
    out = []
    cid = df.groupby("cd_mun", sort=False).first()
    # 1. por ponto da apuração
    tab = []
    for q, g in df.groupby("p"):
        tab.append({"seções apuradas": f"{q:.0%}", "eleitores apurados (mediana)": f"{g['pi'].median():.0%}",
                    "viés real com o sinal previsto": f"{np.mean(np.sign(g['Br']) == np.sign(g['B1'])):.0%}",
                    "w_comp agrupado": num(np.sum(g["B1"] * g["Br"]) / np.sum(g["B1"] ** 2), 2, False),
                    "w_proj agrupado": num(-np.sum(g["inc"] * g["e0"]) / np.sum(g["inc"] ** 2), 2, False),
                    "erro parcial (w=0)": num(rms(g["e0"]), 2, False),
                    "w=0,65": num(rms(g["e065"]), 2, False),
                    "w agrupado (sem a cidade)": num(rms(g["e_fora"]), 2, False),
                    "w da cidade": num(rms(g["e_cidade"]), 2, False),
                    "composição real": num(rms(g["e_oraculo"]), 2, False),
                    "w=0,65 erra menos que w=0": f"{np.mean(np.abs(g['e065']) < np.abs(g['e0'])):.0%}"})
    out.append(f"### Erro da projeção da margem final da cidade (RMS entre as {len(cid)} cidades, pontos)\n\n"
               + md(pd.DataFrame(tab)) + f"\n\nCorrelação de ordem 1T × 2T dentro da cidade (Spearman, "
               f"seções): mediana {num(cid['rho'].median(), 2, False)}, de {num(cid['rho'].min(), 2, False)} "
               f"a {num(cid['rho'].max(), 2, False)}.")
    # 2. distribuição de w entre cidades
    lo, hi = p.w_media - 1.645 * p.w_dp, p.w_media + 1.645 * p.w_dp
    # no modelo nacional um w só vale para todos os municípios: o que conta é a média dos w das
    # cidades pesada pelo efeito da ordem em votos (válidos × viés previsto pela ordem do 1T)
    peso = cid["validos"] * df.groupby("cd_mun", sort=False)["B1"].apply(rms)
    tab = []
    for nome, rot in (("comp", "w_comp (composição)"), ("comp_h", "w_comp só com F1 × L1 do 1T (sem b)"),
                      ("proj", "w_proj (projeção)")):
        w, ep = cid[f"wc_{nome}"].to_numpy(), cid[f"ep_{nome}"].to_numpy()
        pc = np.percentile(w, [10, 25, 50, 75, 90])
        re = efeitos_aleatorios(w, ep ** 2)
        z = (w - p.w_media) / np.sqrt(p.w_dp ** 2 + ep ** 2)
        x, y = {"comp": ("B1", "Br"), "comp_h": ("B1_h", "Br_h"), "proj": ("inc", "e0")}[nome]
        agr = (-1 if nome == "proj" else 1) * np.sum(df[x] * df[y]) / np.sum(df[x] ** 2)
        tab.append({"medida": rot, "agrupado": num(agr, 2, False),
                    "média pesada (votos × viés)": num(np.average(w, weights=peso.loc[cid.index]), 2, False),
                    "p10 / p25 / mediana / p75 / p90": " / ".join(num(v, 2, False) for v in pc),
                    "efeitos aleatórios: média ± ep": f"{num(re['mu'], 2, False)} ± {num(re['ep'], 2, False)}",
                    "dispersão verdadeira (tau)": num(re["tau"], 2, False),
                    f"dentro de {num(lo, 2, False)} a {num(hi, 2, False)}": f"{np.mean((w >= lo) & (w <= hi)):.0%}",
                    "dentro da grade 0–2": f"{np.mean((w >= min(p.ws)) & (w <= max(p.ws))):.0%}",
                    "nos 90% da priori, com o ruído": f"{np.mean(np.abs(z) < 1.645):.0%}"})
    out.append("### w por cidade: distribuição e cobertura da priori\n\n" + md(pd.DataFrame(tab)))
    # ruído de composição: o modelo sorteia seções; na prática chegam locais inteiros
    mu = efeitos_aleatorios(cid["wc_comp"].to_numpy(), cid["ep_comp"].to_numpy() ** 2)["mu"]
    tab = []
    for q, g in df.groupby("p"):
        res2 = (g["Br"] - mu * g["B1"]) ** 2
        tab.append({"seções apuradas": f"{q:.0%}",
                    "dp do viés real − w·previsto (mediana, pontos)": num(np.median(np.sqrt(res2)), 2, False),
                    "dp do modelo, seções sorteadas (mediana)": num(np.median(np.sqrt(g["var_comp_sec"])), 2, False),
                    "dp com locais sorteados (mediana)": num(np.median(np.sqrt(g["var_comp"])), 2, False),
                    "z² médio, seções": num(np.mean(res2 / g["var_comp_sec"]), 1, False),
                    "z² médio, locais": num(np.mean(res2 / g["var_comp"]), 1, False)})
    out.append(f"### Ruído de composição da parte apurada (w = {num(mu, 2, False)} em todas as cidades; "
               "z² ≈ 1 se o ruído suposto for o certo)\n\n" + md(pd.DataFrame(tab)))
    # 3. por cidade
    tab = []
    for cd, g in df.groupby("cd_mun", sort=False):
        r, i = g.iloc[0], info[cd]
        g25 = g[g["p"] == 0.25].iloc[0]
        tab.append({"cidade": f"{i['nome']} ({i['uf']})", "eleitores (mil)": f"{r['aptos'] / 1e3:.0f}",
                    "F × L": i["duelo"], "1T F−L": num(r["m1"], 1), "2T final": num(r["final"], 1),
                    "ρ ordem 1T×2T": num(r["rho"], 2, False),
                    "viés a 25%: 1T / real": f"{num(g25['B1'], 2)} / {num(g25['Br'], 2)}",
                    "w_comp ± ep": f"{num(r['wc_comp'], 2)} ± {num(r['ep_comp'], 2, False)}",
                    "w_proj ± ep": f"{num(r['wc_proj'], 2)} ± {num(r['ep_proj'], 2, False)}",
                    "erro w=0": num(rms(g["e0"]), 2, False), "w=0,65": num(rms(g["e065"]), 2, False),
                    "w agrup.": num(rms(g["e_fora"]), 2, False), "w cidade": num(rms(g["e_cidade"]), 2, False),
                    "comp. real": num(rms(g["e_oraculo"]), 2, False), "_ap": r["aptos"]})
    tab = pd.DataFrame(tab).sort_values("_ap", ascending=False).drop(columns="_ap")
    out.append("### Por cidade (erros: RMS da projeção em 10/25/50/75% das seções, pontos)\n\n" + md(tab))
    return "\n\n".join(out)


def grafico(df: pd.DataFrame, info: dict, p, arq: str = "validacao_2024_w.png") -> None:
    """w de composição por cidade (± 1,96 ep) contra a priori do modelo."""
    import matplotlib.pyplot as plt
    from estudos.relatorio import COR, estilo
    cid = df.groupby("cd_mun", sort=False).first().sort_values("wc_comp")
    w, ep = cid["wc_comp"].to_numpy(), cid["ep_comp"].to_numpy()
    re = efeitos_aleatorios(w, ep ** 2)
    n, y = len(cid), np.arange(len(cid))
    x0, x1 = min(-2.0, np.floor(w.min() * 2) / 2 - 0.3), max(4.0, np.ceil(w.max() * 2) / 2 + 0.3)
    fig, ax = plt.subplots(figsize=(7.5, 0.16 * n + 1.4), dpi=150)
    estilo(ax, "w de composição por cidade, prefeito 2º turno 2024 (± 1,96 ep)",
           "w (0 = média da cidade; 1 = ordem do 1º turno)", "")
    ax.grid(False, axis="y")
    lo, hi = p.w_media - 1.645 * p.w_dp, p.w_media + 1.645 * p.w_dp
    ax.axvspan(lo, hi, color=COR["grade"], alpha=0.7, linewidth=0)
    ax.axvline(p.w_media, color=COR["texto2"], linewidth=1)
    ax.axvline(re["mu"], color=COR["azul"], linewidth=1)
    ax.hlines(y, np.clip(w - 1.96 * ep, x0, x1), np.clip(w + 1.96 * ep, x0, x1), color=COR["azul"],
              linewidth=1.2, alpha=0.45)
    ax.scatter(np.clip(w, x0, x1), y, s=22, color=COR["azul"], edgecolor=COR["fundo"], linewidth=1, zorder=3)
    ax.set_yticks(y, [f"{info[c]['nome']} ({info[c]['uf']})" for c in cid.index], fontsize=6.5)
    ax.set_xlim(x0, x1)
    ax.set_ylim(-1.4, n + 0.9)
    ax.text(lo + 0.04, n + 0.2, f"faixa: priori do modelo, 90% ({num(p.w_media, 2, False)} ± "
            f"{num(1.645 * p.w_dp, 2, False)})", fontsize=7, color=COR["texto2"])
    ax.text(re["mu"] - 0.04, -1.1, f"linha: média das cidades (efeitos aleatórios) {num(re['mu'], 2, False)}",
            fontsize=7, color=COR["texto"], ha="right")
    fig.tight_layout()
    fig.savefig(RES / arq)
    plt.close(fig)


def main() -> None:
    p = carregar_params()
    s1, s2 = ler(1), ler(2)
    linhas, info = [], {}
    for cd, c2 in s2.groupby("cd_mun", sort=False):
        d = montar(s1[s1["cd_mun"] == cd], c2)
        info[cd] = dict(uf=c2["uf"].iloc[0], nome=c2["nm_mun"].iloc[0].title(),
                        duelo=f"{SIGLAS.get(d['F'], d['F'])} × {SIGLAS.get(d['L'], d['L'])}")
        linhas += avaliar(d, p)
    df = pd.DataFrame(linhas)
    df = df.merge(por_cidade(df), on="cd_mun")
    df["e065"] = projetar(df, p.w_media)
    df["e_fora"] = projetar(df, df["w_fora"])
    df["e_cidade"] = projetar(df, df["wc_proj"])
    df["e_comp"] = projetar(df, df["wc_comp"])
    df["nome"] = df["cd_mun"].map(lambda c: info[c]["nome"])
    df["uf"] = df["cd_mun"].map(lambda c: info[c]["uf"])
    RES.mkdir(exist_ok=True)
    df.to_csv(RES / "validacao_2024.csv", index=False)
    txt = resumo(df, info, p)
    (RES / "validacao_2024_tabelas.md").write_text(txt + "\n", encoding="utf-8")
    grafico(df, info, p)
    print(txt)


if __name__ == "__main__":
    main()
