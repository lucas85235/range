"""Estimadores da margem final a partir da apuração parcial por município.

Modelo principal (`Transferencia`): regressão de transferência de votos do 1º para o 2º turno.
Para cada município j, com A_j eleitores aptos no 2º turno:
  x_j = taxas do 1º turno por eleitor: F1, L1, cada outro candidato relevante, demais nominais,
        brancos+nulos e abstenção (somam 1).
  yD_j = (F - L) / aptos apurados    (diferença por eleitor, na parte já apurada)
  yS_j = (F + L) / aptos apurados    (válidos por eleitor)
  y = x' b + efeito da região + efeito da UF + e_j
O efeito de região e o de UF são aleatórios (encolhidos para zero); e_j tem variância
s0^2 + s1^2 / aptos (piso político + ruído amostral) + incerteza da composição da parte apurada.
A parte ainda não apurada de cada município recebe a previsão do modelo mais uma fração (psi)
do resíduo já visto nele.

Ordem de chegada (Ordem1T): dentro de cada município as primeiras seções a chegar são mais
favoráveis a F que as últimas, e isso já aparecia no 1º turno. Com a hora do BU do 1º turno, x_j
da parte apurada passa a ser a composição das seções que chegaram primeiro no 1º turno,
misturada com a média do município (peso w). w não é conhecido: o modelo mistura hipóteses de w
com uma priori e as julga pelo erro com que previram os votos que chegaram depois.

Margem prevista = 100 * soma(D) / soma(S); a incerteza vem dos parâmetros, do ruído dos
municípios por apurar, da mistura sobre w e de um termo sistemático proporcional ao que falta.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
from scipy import stats

REGIAO = {"AC": "N", "AM": "N", "AP": "N", "PA": "N", "RO": "N", "RR": "N", "TO": "N",
          "AL": "NE", "BA": "NE", "CE": "NE", "MA": "NE", "PB": "NE", "PE": "NE", "PI": "NE",
          "RN": "NE", "SE": "NE", "DF": "CO", "GO": "CO", "MS": "CO", "MT": "CO",
          "ES": "SE", "MG": "SE", "RJ": "SE", "SP": "SE", "PR": "S", "RS": "S", "SC": "S",
          "ZZ": "ZZ"}
FAIXAS = [(-np.inf, -12), (-12, -8), (-8, -4), (-4, 0), (0, 4), (4, 8), (8, 12), (12, np.inf)]
NOMES_FAIXAS = ["L 12%+", "L 8-12%", "L 4-8%", "L <4%", "F <4%", "F 4-8%", "F 8-12%", "F 12%+"]


@dataclass
class Params:
    s0_D: float = 0.03       # dp do efeito político do município (por eleitor), equação D
    s1_D: float = 0.5        # ruído amostral: dp por eleitor = s1 / sqrt(aptos)
    s0_S: float = 0.02
    s1_S: float = 0.4
    tau_reg: float = 0.02    # dp do efeito de região (por eleitor)
    tau_uf: float = 0.02     # dp do efeito de UF
    tau_b: float = 0.5       # dp a priori dos coeficientes de transferência
    psi: float = 0.8         # quanto do resíduo visto no município vale para o resto dele
    k: float = 1.0           # fator de calibração da incerteza
    gl: float = 6.0          # graus de liberdade da t nas faixas (0 = normal)
    dispersao: bool = True   # estima ao vivo o quanto os resíduos excedem o esperado
    n0_disp: float = 200.0   # peso a priori da dispersão = 1
    # hipóteses para a ordem de chegada dentro do município (só com Ordem1T): w = peso da
    # ordem do 1º turno na composição da parte apurada (0 = média do município).
    ws: tuple = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
    w_media: float = 0.65    # a priori: em 2022 o melhor w ficou entre 0,5 e 1,0; no 1º turno de
                             # 2026 (base 2022, ordem de outra eleição) chegou a 1,5
    w_dp: float = 0.45
    # atualização prequencial: cada w é julgado pelo erro com que previu os votos que
    # chegaram depois (janelas de preq_lag minutos), na escala de pontos de margem
    preq_lag: float = 10.0
    preq_tau: float = 0.03   # ruído típico do erro de uma janela (pp)
    preq_temp: float = 3.0   # janelas são correlacionadas: divide a evidência
    sis_a: float = 0.3       # erro sistemático extra: dp = sis_a * fração ainda por apurar
    sis_b: float = 0.7       # e mais este no começo: dp = sis_b * (fração por apurar - r0)/(1 - r0)
    sis_r0: float = 0.8      # (só enquanto falta mais de 80%; calibrado nas simulações de 2026)
    kappa_comp: float = 1.0  # peso da incerteza de composição da parte apurada (Ordem1T)
    # efeito do tamanho do município: ajudou no 1º turno de 2026 com base de 2022, mas nas simulações
    # cria viés falso a favor de F no começo (cidades pequenas chegam antes) e no 2º turno real de
    # 2022 não mudou nada. Desligado (0) para o 2º turno de 2026.
    tau_tam: float = 0.0


def carregar_params() -> Params:
    """Os parâmetros congelados em calibracao.json (os que o monitor usa); sem o arquivo, os padrões."""
    from nucleo.caminhos import CALIBRACAO
    if not CALIBRACAO.exists():
        return Params()
    d = json.loads(CALIBRACAO.read_text(encoding="utf-8")).get("params", {})
    if "ws" in d:
        d["ws"] = tuple(d["ws"])
    return replace(Params(), **d)


def contagens_base(base: pd.DataFrame, aptos: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Votos do 1º turno por categoria (F1, L1, outros, brancos+nulos, abstenção)."""
    A = np.asarray(aptos, float)
    outros = [c for c in base.columns if c.startswith("o") and c[1:].isdigit()]
    cols = {"F1": base["F1"], "L1": base["L1"]}
    for c in outros:
        cols[c] = base[c]
    cols["Orest"] = base["O1"] - base[outros].sum(axis=1)
    cols["BN1"] = base["BN1"]
    cols["ABS1"] = np.maximum(A - base["C1"].to_numpy(float), 0.0)
    return np.column_stack([np.asarray(v, float) for v in cols.values()]), list(cols.keys())


def matriz_base(base: pd.DataFrame, aptos: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Taxas do 1º turno por eleitor apto (colunas somam 1)."""
    Xc, nomes = contagens_base(base, aptos)
    return Xc / np.maximum(np.asarray(aptos, float), 1.0)[:, None], nomes


class Ordem1T:
    """Composição do 1º turno da parte já apurada de cada município, supondo que o 2º turno
    chega na mesma ordem das seções no 1º (hora do BU do 1º turno).

    partes(pi) devolve as taxas por eleitor (categorias de contagens_base) da parte apurada
    (fração pi dos aptos de cada município, primeiras seções pela ordem do 1º turno), da parte
    restante e a média do município. Quem usa mistura as duas hipóteses: ordem do 1º turno
    (peso w) e ordem sem informação (média do município).
    """

    def __init__(self, sec1: pd.DataFrame, base: pd.DataFrame):
        munis = base.index
        s = sec1[sec1["cd_mun"].isin(munis)].copy()
        s["j"] = munis.get_indexer(s["cd_mun"])
        s = s.sort_values(["j", "t"], kind="stable")
        cols = {"F1": s["F"], "L1": s["L"]}
        outros = [c for c in base.columns if c.startswith("o") and c[1:].isdigit()]
        for c in outros:
            cols[c] = s.get(f"v{c[1:]}", 0)
        cols["Orest"] = s["O"] - sum(np.asarray(s.get(f"v{c[1:]}", 0), float) for c in outros)
        cols["BN1"] = s["BN"]
        cols["ABS1"] = np.maximum(s["aptos"] - s["C"], 0)
        V = np.column_stack([np.asarray(v, float) for v in cols.values()])
        j = s["j"].to_numpy()
        ap = s["aptos"].to_numpy(float)
        M = len(munis)
        self.M = M
        self.tot = np.zeros((M, V.shape[1]))
        np.add.at(self.tot, j, V)
        self.apt = np.bincount(j, weights=ap, minlength=M)
        self.Xm = self.tot / np.maximum(self.apt, 1.0)[:, None]
        # acumulados dentro de cada município (inclusive); chave j + q permite uma busca só
        cumV, cumA = np.cumsum(V, axis=0), np.cumsum(ap)
        ini = np.r_[0, np.flatnonzero(np.diff(j)) + 1]
        cont = np.diff(np.r_[ini, len(j)])
        prevV = np.vstack([np.zeros((1, V.shape[1])), cumV[ini[1:] - 1]])
        prevA = np.r_[0.0, cumA[ini[1:] - 1]]
        self.cV = cumV - np.repeat(prevV, cont, axis=0)
        self.cA = cumA - np.repeat(prevA, cont)
        q = self.cA / np.maximum(self.apt[j], 1.0)
        self.chave = j + np.minimum(q, 1.0) * 0.999999
        self.j = j
        self.tem = self.apt > 0
        # variância entre seções (dentro do município) das taxas que importam para D e S:
        # mede o quanto a composição de uma parte pequena pode fugir da suposta
        apos = np.maximum(ap, 1.0)
        for nome, taxa in (("D", (s["F"] - s["L"]).to_numpy(float) / apos),
                           ("S", (s["F"] + s["L"] + s["O"]).to_numpy(float) / apos)):
            m1 = np.bincount(j, weights=ap * taxa, minlength=M) / np.maximum(self.apt, 1.0)
            m2 = np.bincount(j, weights=ap * taxa ** 2, minlength=M) / np.maximum(self.apt, 1.0)
            setattr(self, f"vsec_{nome}", np.maximum(m2 - m1 ** 2, 0.0))
        self.nsec = np.bincount(j, minlength=M).astype(float)

    def var_composicao(self, pi: np.ndarray, eq: str) -> np.ndarray:
        """Variância (por eleitor) da taxa média de uma parte pi do município, como se as
        seções da parte fossem sorteadas (correção de população finita)."""
        pi = np.clip(np.asarray(pi, float), 1e-6, 1.0)
        return getattr(self, f"vsec_{eq}") * (1 - pi) / (pi * np.maximum(self.nsec, 1.0))

    def contagem(self, pi: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Votos do 1º turno (categorias) e aptos das primeiras seções que somam a fração pi
        dos aptos de cada município, na ordem do 1º turno. Devolve (Vc, Ac, ok)."""
        pi = np.clip(np.asarray(pi, float), 0.0, 1.0)
        alvo = np.arange(self.M) + pi * 0.999999
        k = np.minimum(np.searchsorted(self.chave, alvo, side="left"), len(self.chave) - 1)
        ok = self.tem & (self.j[k] == np.arange(self.M))
        alvo_a = pi * self.apt
        mesmo = (k > 0) & (self.j[np.maximum(k - 1, 0)] == self.j[k])
        prevA = np.where(mesmo, self.cA[np.maximum(k - 1, 0)], 0.0)
        prevV = np.where(mesmo[:, None], self.cV[np.maximum(k - 1, 0)], 0.0)
        frac = np.clip((alvo_a - prevA) / np.maximum(self.cA[k] - prevA, 1e-9), 0, 1)
        Vc = prevV + frac[:, None] * (self.cV[k] - prevV)   # interpola dentro da seção k
        Ac = prevA + frac * (self.cA[k] - prevA)
        Vc = np.where(ok[:, None], Vc, self.Xm * alvo_a[:, None])
        Ac = np.where(ok, Ac, alvo_a)
        return Vc, Ac, ok

    def partes(self, pi: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        Xm = self.Xm
        Vc, Ac, ok = self.contagem(pi)
        Xc = np.where((ok & (Ac > 0))[:, None], Vc / np.maximum(Ac, 1e-9)[:, None], Xm)
        Ar = self.apt - Ac
        Xr = np.where((ok & (Ar > 0.5))[:, None], (self.tot - Vc) / np.maximum(Ar, 1e-9)[:, None], Xm)
        return Xc, Xr, Xm


@dataclass
class Transferencia:
    base: pd.DataFrame          # index = cd_mun, na mesma ordem das colunas da apuração
    aptos: np.ndarray           # aptos do 2º turno por município
    p: Params = field(default_factory=Params)
    ordem: Ordem1T | None = None  # composição da parte apurada pela ordem do 1º turno

    def __post_init__(self):
        self.A = np.asarray(self.aptos, float)
        self.X, self.nomes = matriz_base(self.base, self.A)
        ufs = self.base["uf"].to_numpy()
        self.uf_nomes = sorted(set(ufs))
        self.reg_nomes = sorted(set(REGIAO[u] for u in self.uf_nomes))
        iu = pd.Index(self.uf_nomes).get_indexer(ufs)
        ir = pd.Index(self.reg_nomes).get_indexer([REGIAO[u] for u in ufs])
        M = len(ufs)
        R = np.zeros((M, len(self.reg_nomes)))
        R[np.arange(M), ir] = 1
        U = np.zeros((M, len(self.uf_nomes)))
        U[np.arange(M), iu] = 1
        # tamanho do município (log do eleitorado, padronizado): a mudança de voto pode diferir
        # entre cidades pequenas (chegam primeiro) e grandes; o efeito é aprendido ao vivo
        la = np.log(np.maximum(self.A, 1.0))
        wm = np.average(la, weights=np.maximum(self.A, 1.0))
        tam = ((la - wm) / max(la.std(), 1e-9))[:, None] if self.p.tau_tam > 0 else np.zeros((M, 0))
        self.RU = np.hstack([R, U, tam])
        self.Z = np.hstack([self.X, self.RU])
        nb, nr, nu, nt = self.X.shape[1], R.shape[1], U.shape[1], tam.shape[1]
        self.nb = nb
        # a priori: F1 -> +1 em D, L1 -> -1 em D; demais 0. Em S: F1, L1 -> 1, resto 0.5
        b0_D = np.array([1.0 if n == "F1" else -1.0 if n == "L1" else 0.0 for n in self.nomes])
        b0_S = np.array([1.0 if n in ("F1", "L1") else 0.5 if n.startswith("o") or n == "Orest"
                         else 0.1 for n in self.nomes])
        self.m0 = {"D": np.concatenate([b0_D, np.zeros(nr + nu + nt)]),
                   "S": np.concatenate([b0_S, np.zeros(nr + nu + nt)])}
        p = self.p
        self.prec0 = np.concatenate([np.full(nb, 1 / p.tau_b ** 2), np.full(nr, 1 / p.tau_reg ** 2),
                                     np.full(nu, 1 / p.tau_uf ** 2),
                                     np.full(nt, 1 / max(p.tau_tam, 1e-9) ** 2)])

    def _ajusta(self, y, ap, mask, eq, Zc, v_extra=0.0):
        p = self.p
        s0, s1 = (p.s0_D, p.s1_D) if eq == "D" else (p.s0_S, p.s1_S)
        var = s0 ** 2 + s1 ** 2 / np.maximum(ap, 1.0) + v_extra
        w = np.where(mask, 1.0 / var, 0.0)
        Zw = Zc * w[:, None]
        H = Zc.T @ Zw + np.diag(self.prec0)
        g = Zw.T @ np.where(mask, y, 0.0) + self.prec0 * self.m0[eq]
        cov = np.linalg.inv(H)
        th = cov @ g
        r = np.where(mask, y - Zc @ th, 0.0)
        n = mask.sum()
        phi = 1.0
        if p.dispersao and n > 0:
            chi = float(np.sum(w * r ** 2))
            phi = max(1.0, (chi + p.n0_disp) / (n + p.n0_disp))
        return th, cov, r, var, phi, s0, s1

    def _uma_hipotese(self, F, L, ap, mask, Arem, Zc, Zr, vcomp=None) -> dict:
        """Previsão com uma composição fixa da parte apurada (Zc) e da restante (Zr)."""
        tot, var, out = {}, {}, {}
        for eq, conta in (("D", F - L), ("S", F + L)):
            y = np.divide(conta, ap, out=np.zeros_like(ap), where=ap > 0)
            vx = 0.0 if vcomp is None else vcomp[eq]
            th, cov, r, v, phi, s0, s1 = self._ajusta(y, ap, mask, eq, Zc, vx)
            enc = np.where(mask, s0 ** 2 / v, 0.0)          # quanto o resíduo visto é do município
            ef = self.p.psi * enc * r                        # efeito levado à parte por apurar
            tot[eq] = conta.sum() + np.sum(Arem * (Zr @ th + ef))
            # sensibilidade aos parâmetros (o efeito próprio também depende deles)
            grad = Arem @ Zr - (Arem * self.p.psi * enc) @ Zc
            v_par = grad @ cov @ grad
            v_mun = np.sum(Arem ** 2 * (s0 ** 2 * (1 - (self.p.psi ** 2) * enc)
                                        + s1 ** 2 / np.maximum(Arem, 1.0)))
            var[eq] = phi * (v_par + v_mun)
            out[f"phi_{eq}"] = phi
            out[f"theta_{eq}"] = th
            out[f"ef_{eq}"] = ef
        mu = 100 * tot["D"] / tot["S"]
        v_mu = (100 / tot["S"]) ** 2 * var["D"] + (100 * tot["D"] / tot["S"] ** 2) ** 2 * var["S"]
        out.update(mu=mu, var=v_mu, validos_prev=tot["S"])
        return out

    def reiniciar(self) -> None:
        """Esquece o histórico (início de uma nova apuração)."""
        self.hist = []
        self.ll_w = np.zeros(len(self.p.ws))
        self.n_janelas = 0
        self.t_ultimo = None

    def _prequencial(self, t, F, L, ap, pi) -> None:
        """Julga cada w pelo erro ao prever o que chegou desde o retrato de ~preq_lag atrás."""
        if not hasattr(self, "hist"):
            self.reiniciar()
        ok = [h for h in self.hist if h["t"] <= t - self.p.preq_lag and not h.get("usado")]
        if not ok:
            return
        h = ok[-1]
        for x in ok:   # cada retrato inicia no máximo uma janela
            x["usado"] = True
        dA = np.maximum(ap - h["ap"], 0.0)
        if dA.sum() <= 0:
            return
        V0, A0, _ = h["cont"]
        V1, A1, _ = self.ordem.contagem(pi)
        dAc = A1 - A0
        Xi1 = np.where((dAc > 0.5)[:, None], (V1 - V0) / np.maximum(dAc, 1e-9)[:, None], self.ordem.Xm)
        dD = (F - L) - h["D"]
        dS = (F + L) - h["S"]
        Stot = max(float(np.sum(self.A)) * 0.75, 1.0)
        M = float(np.sum(F - L) / max(np.sum(F + L), 1.0))
        erros = []
        for i, w in enumerate(self.p.ws):
            Zi = np.hstack([w * Xi1 + (1 - w) * self.ordem.Xm, self.RU])
            fit = h["fits"][i]
            pD = dA * (Zi @ fit["theta_D"] + fit["ef_D"])
            pS = dA * (Zi @ fit["theta_S"] + fit["ef_S"])
            erros.append(((pD - dD).sum() - M * (pS - dS).sum()) / Stot * 100)
        erros = np.array(erros)
        # janelas se sobrepõem: o peso de cada uma é proporcional ao tempo desde o ciclo
        # anterior (calibrado com ciclos de 2 min), para a evidência não depender da cadência
        passo = float(np.clip(t - self.t_ultimo, 0.0, 5.0)) if self.t_ultimo is not None else 2.0
        self.ll_w += -0.5 * erros ** 2 / self.p.preq_tau ** 2 / self.p.preq_temp * (passo / 2.0)
        self.n_janelas += 1

    def prever(self, F, L, aptos_ap, t: float | None = None) -> dict:
        """F, L, aptos_ap: acumulados por município no momento (arrays M); t em minutos.

        Com `t`, o modelo guarda o retrato e usa as janelas já fechadas para julgar w.
        """
        F, L, ap = (np.asarray(v, float) for v in (F, L, aptos_ap))
        mask = (ap > 0) & (F + L > 0)
        Arem = np.maximum(self.A - ap, 0.0)
        if self.ordem is None:
            hips = [(np.nan, self._uma_hipotese(F, L, ap, mask, Arem, self.Z, self.Z))]
            lp = np.zeros(1)
        else:
            pi = np.divide(ap, self.A, out=np.zeros_like(ap), where=self.A > 0)
            Xc1, Xr1, Xm = self.ordem.partes(pi)
            vcomp = {eq: self.p.kappa_comp * self.ordem.var_composicao(pi, eq) for eq in ("D", "S")}
            hips = []
            for w in self.p.ws:
                Zc = np.hstack([w * Xc1 + (1 - w) * Xm, self.RU])
                Zr = np.hstack([w * Xr1 + (1 - w) * Xm, self.RU])
                hips.append((w, self._uma_hipotese(F, L, ap, mask, Arem, Zc, Zr, vcomp)))
            ws = np.array(self.p.ws, float)
            lp = -0.5 * ((ws - self.p.w_media) / self.p.w_dp) ** 2
            if t is not None:
                self._prequencial(t, F, L, ap, pi)
                lp = lp + self.ll_w
                self.hist.append({"t": t, "ap": ap.copy(), "D": F - L, "S": F + L,
                                  "cont": self.ordem.contagem(pi),
                                  "fits": [{k: h[k] for k in ("theta_D", "theta_S", "ef_D", "ef_S")}
                                           for _, h in hips]})
                # retrato que já abriu uma janela não serve mais
                self.hist = [h for h in self.hist if not h.get("usado")][-100:]
                self.t_ultimo = t
        pw = np.exp(lp - lp.max())
        pw /= pw.sum()
        mus = np.array([h["mu"] for _, h in hips])
        mu = float(pw @ mus)
        v_mu = float(pw @ (np.array([h["var"] for _, h in hips]) + mus ** 2) - mu ** 2)
        resta = float(Arem.sum() / self.A.sum())
        v_tot = self.p.k ** 2 * v_mu + var_sistematica(resta, self.p)
        melhor = hips[int(np.argmax(pw))][1]
        out = {k: v for k, v in melhor.items() if k in ("phi_D", "phi_S", "validos_prev")}
        out.update(mu=mu, sd=float(np.sqrt(v_tot)), sd_bruto=float(np.sqrt(v_mu)),
                   apurado=1 - resta, w_post=dict(zip([w for w, _ in hips], pw.round(3))),
                   w_medio=float(pw @ np.array([w for w, _ in hips])), mus_w=mus)
        return out


def var_sistematica(resta: float | np.ndarray, p: Params):
    """Variância extra (pp²) que o modelo não enxerga, em função da fração por apurar."""
    inicio = np.clip((np.asarray(resta, float) - p.sis_r0) / (1 - p.sis_r0), 0.0, 1.0)
    return (p.sis_a * np.asarray(resta, float)) ** 2 + (p.sis_b * inicio) ** 2


def ingenuo(F, L) -> float:
    s = np.sum(F) + np.sum(L)
    return float((np.sum(F) - np.sum(L)) / s * 100) if s > 0 else np.nan


def faixa_provavel(mu: float, sd: float, gl: float = 0.0, nivel: float = 0.9) -> tuple[float, float]:
    """Intervalo central com `nivel` de chance para a margem final (mesma distribuição das faixas)."""
    dist = stats.t(gl) if gl and gl > 0 else stats.norm
    z = float(dist.ppf(0.5 + nivel / 2))
    return mu - z * sd, mu + z * sd


def faixas_cobertas(lo: float, hi: float, cortes=(-12, -8, -4, 0, 4, 8, 12)) -> list[str]:
    """Faixas da Polymarket que o intervalo [lo, hi] toca."""
    bordas = [-np.inf, *cortes, np.inf]
    return [NOMES_FAIXAS[i] for i in range(len(NOMES_FAIXAS)) if hi >= bordas[i] and lo < bordas[i + 1]]


def prob_faixas(mu: float, sd: float, gl: float = 0.0,
                cortes=(-12, -8, -4, 0, 4, 8, 12)) -> np.ndarray:
    """Probabilidade de cada faixa da Polymarket (na fronteira exata vale a faixa de cima)."""
    dist = stats.t(gl) if gl and gl > 0 else stats.norm
    cdf = dist.cdf((np.asarray(cortes, float) - mu) / max(sd, 1e-9))
    return np.diff(np.concatenate([[0.0], cdf, [1.0]]))
