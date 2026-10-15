"""Testa regras de venda para quem tem uma posição (close-only: só dá para vender).

Para cada regra e para quem tem Sim em "F <4%" ou em "F 4-8%", mede nas simulações:
  - quando a faixa PERDE: em quantas noites a regra vende, quanto da posição e a que horas;
  - quando a faixa GANHA: em quantas noites a regra vende por engano e quanto.
E aplica as mesmas regras na noite real do 1º turno, com os preços reais da Polymarket.

O modelo vê os dados com 5 minutos de atraso (publicação do TSE e download).

    python eleicao/estudos/estrategia.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do projeto
from estudos.relatorio import md, sd_atual  # noqa: E402
from nucleo.caminhos import RES  # noqa: E402
from nucleo.modelo import NOMES_FAIXAS, Params, faixa_provavel, prob_faixas  # noqa: E402

ATRASO = 5
CORTES = np.array([-12, -8, -4, 0, 4, 8, 12], float)


@dataclass
class Degrau:
    chance: float              # vende quando a chance da posição fica ≤ isto
    fracao: float              # fração da posição vendida neste degrau
    apurado_min: float         # só a partir deste % do eleitorado apurado
    fora_da_faixa: bool = False  # em vez da chance: quando a faixa provável (90%) sai da sua


@dataclass
class Regra:
    nome: str
    degraus: tuple

    def vendas(self, p: np.ndarray, apurado: np.ndarray, toca: np.ndarray) -> np.ndarray:
        """Fração acumulada vendida em cada passo (cada degrau dispara uma vez)."""
        vendido = np.zeros(len(p))
        acc = 0.0
        feitos = [False] * len(self.degraus)
        for i in range(len(p)):
            for k, d in enumerate(self.degraus):
                if feitos[k] or apurado[i] < d.apurado_min:
                    continue
                if (not toca[i]) if d.fora_da_faixa else (p[i] <= d.chance):
                    feitos[k] = True
                    acc += d.fracao
            vendido[i] = min(acc, 1.0)
        return vendido


D = Degrau
REGRAS = [
    Regra("tudo se chance ≤ 10%, desde 2%", (D(0.10, 1, 2),)),
    Regra("tudo se chance ≤ 10%, desde 5%", (D(0.10, 1, 5),)),
    Regra("tudo se chance ≤ 20%, desde 5%", (D(0.20, 1, 5),)),
    Regra("tudo se chance ≤ 20%, desde 20%", (D(0.20, 1, 20),)),
    Regra("tudo se a faixa de 90% sair da sua, desde 2%", (D(1, 1, 2, True),)),
    Regra("metade se faixa de 90% sair (desde 2%) + resto se ≤ 20% (desde 20%)",
          (D(1, 0.5, 2, True), D(0.20, 0.5, 20))),
    Regra("metade se ≤ 10% (desde 5%) + resto se ≤ 20% (desde 20%)", (D(0.10, 0.5, 5), D(0.20, 0.5, 20))),
    Regra("escalonada: ⅓ a 30%, ⅓ a 15%, ⅓ a 5%, desde 5%",
          (D(0.30, 1 / 3, 5), D(0.15, 1 / 3, 5), D(0.05, 1 / 3, 5))),
]


def faixa_idx(nome: str) -> int:
    return NOMES_FAIXAS.index(nome)


def toca_faixa(mu, sd, gl, i_faixa, cortes=CORTES) -> np.ndarray:
    bordas = np.concatenate([[-np.inf], cortes, [np.inf]])
    lo, hi = faixa_provavel(np.asarray(mu), np.asarray(sd), gl, 0.9)
    return (hi >= bordas[i_faixa]) & (lo < bordas[i_faixa + 1])


def avaliar_sims(d: pd.DataFrame, p: Params) -> pd.DataFrame:
    linhas = []
    for (sim, g) in d.groupby("sim"):
        g = g.sort_values("t")
        mu, sd, ap = g["mu"].to_numpy(), g["sd"].to_numpy(), g["apurado"].to_numpy()
        final = float(g["final"].iloc[0])
        probs = np.vstack([prob_faixas(m, s, p.gl) for m, s in zip(mu, sd)])
        for faixa in ("F <4%", "F 4-8%"):
            i = faixa_idx(faixa)
            ganha = bool(CORTES[i - 1] <= final < CORTES[i]) if 0 < i < len(CORTES) else False
            toca = toca_faixa(mu, sd, p.gl, i)
            for r in REGRAS:
                v = r.vendas(probs[:, i], ap, toca)
                k = int(np.argmax(v > 0)) if (v > 0).any() else None
                linhas.append({"sim": sim, "faixa": faixa, "regra": r.nome, "ganha": ganha,
                               "dist4": abs(final - 4), "vendido": float(v[-1]),
                               "t_venda": (float(g["t"].iloc[k]) + ATRASO) if k is not None else np.nan,
                               "ap_venda": float(ap[k]) if k is not None else np.nan})
    return pd.DataFrame(linhas)


def hora(t: float) -> str:
    if t is None or np.isnan(t):
        return "—"
    m = int(round(17 * 60 + t))
    return f"{m // 60}h{m % 60:02d}"


def resumo(av: pd.DataFrame, filtro, titulo: str) -> str:
    a = av[filtro(av)]
    linhas = []
    for r in REGRAS:
        x = a[a["regra"] == r.nome]
        perde, ganha = x[~x["ganha"]], x[x["ganha"]]
        linhas.append({
            "regra": r.nome,
            "noites (perde/ganha)": f"{len(perde)}/{len(ganha)}",
            "quando perde: vendeu": f"{(perde['vendido'] > 0).mean() * 100:.0f}%" if len(perde) else "—",
            "fração vendida": f"{perde['vendido'].mean() * 100:.0f}%" if len(perde) else "—",
            "1ª venda (mediana)": hora(perde["t_venda"].median()) if len(perde) else "—",
            "quando ganha: vendeu por engano": f"{(ganha['vendido'] > 0).mean() * 100:.0f}%" if len(ganha) else "—",
            "fração vendida por engano": f"{ganha['vendido'].mean() * 100:.0f}%" if len(ganha) else "—",
        })
    return f"### {titulo}\n\n" + md(pd.DataFrame(linhas), index=False)


def noite_real(p: Params) -> str:
    """Regras na noite real do 1º turno (faixas de 5 pontos), com o preço real do minuto."""
    g = json.loads((RES / "guia_dados.json").read_text(encoding="utf-8"))["real1t"]
    m, pm = g["modelo_final"], g["mercado"]
    faixas = ["L 15%+", "L 10-15%", "L 5-10%", "L <5%", "F <5%", "F 5-10%", "F 10%+"]
    cortes = np.array([-15, -10, -5, 0, 5, 10], float)
    t = np.array(m["t"], float)
    mu, sd, ap = np.array(m["mu"]), np.array(m["sd"]), np.array(m["apurado"])
    linhas = []
    for f in ("L <5%", "F <5%", "F 5-10%"):
        i = faixas.index(f)
        prob = np.array(m[f])
        bordas = np.concatenate([[-np.inf], cortes, [np.inf]])
        lo, hi = faixa_provavel(mu, sd, p.gl, 0.9)
        toca = (hi >= bordas[i]) & (lo < bordas[i + 1])
        venceu = f == "F <5%"
        # preço do mercado (bruto, sem normalizar) no minuto de cada passo do modelo
        preco = np.interp(t, np.array(pm["t"], float), np.array(pm[f"bruto_{f}"], float))
        # regra que olha o preço: vende tudo quando a chance fica abaixo do preço menos uma margem
        # (20 pontos antes de 20% apurado, 5 pontos depois), a partir de 2% apurado
        margem = np.where(ap < 20, 0.20, 0.05)
        v_preco = np.maximum.accumulate(((ap >= 2) & (prob < preco - margem)).astype(float))
        for r, v in [(r, r.vendas(prob, ap, toca)) for r in REGRAS] + \
                [(Regra("tudo se chance < preço − 20 pts (antes de 20%) ou − 5 pts (depois), desde 2%", ()), v_preco)]:
            frac = np.diff(np.concatenate([[0.0], v]))
            receita = float(np.sum(frac * preco))
            resto = 1.0 - float(v[-1])
            valor = receita + resto * (1.0 if venceu else 0.0)
            k = int(np.argmax(v > 0)) if (v > 0).any() else None
            linhas.append({"posição": f'Sim em "{f}"' + (" (venceu)" if venceu else " (perdeu)"),
                           "regra": r.nome, "1ª venda": hora(t[k]) if k is not None else "não vendeu",
                           "preço médio": f"{receita / max(v[-1], 1e-9) * 100:.0f}¢" if v[-1] > 0 else "—",
                           "valor por cota": f"US$ {valor:.2f}"})
    return "### Noite real do 1º turno (preços reais da Polymarket)\n\n" + md(pd.DataFrame(linhas), index=False)


def main() -> None:
    p = Params()
    saidas = []
    avs = {}
    for nome in ("2026", "2026_fronteira", "2022"):
        arq = RES / f"sim_{nome}.parquet"
        if not arq.exists():
            continue
        d = pd.read_parquet(arq)
        d["sd"] = sd_atual(d, p)
        avs[nome] = avaliar_sims(d, p)
        avs[nome].to_csv(RES / f"estrategia_sims_{nome}.csv", index=False)
    # perto da fronteira: as noites a menos de 1 ponto de 4 de todos os lotes de 2026 juntos
    perto = pd.concat([a.assign(lote=n) for n, a in avs.items() if n.startswith("2026")])
    saidas.append(resumo(perto, lambda a: a["dist4"] < 1.0,
                         "Simulações 2026: margem final a menos de 1 ponto de 4 (o seu caso)"))
    saidas.append(resumo(perto, lambda a: a["dist4"] < 0.5, "Simulações 2026: a menos de 0,5 ponto de 4"))
    if "2026" in avs:
        saidas.append(resumo(avs["2026"], lambda a: a["dist4"] >= 1.0,
                             "Simulações 2026: margem final a 1 ponto ou mais de 4"))
    if "2022" in avs:
        saidas.append(resumo(avs["2022"], lambda a: a["dist4"] < 1.0, "Simulações 2022: a menos de 1 ponto de 4"))
    saidas.append(noite_real(p))
    texto = "\n\n".join(saidas)
    (RES / "estrategia.md").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
