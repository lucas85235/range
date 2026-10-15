"""Servidor local que imita a divulgação do TSE, para testar o monitor antes do dia 25.

Reproduz uma apuração (real, com a hora do BU, ou sintética) em tempo acelerado e serve os
mesmos arquivos JSON que o monitor lê do TSE.

    python eleicao/replay_tse.py --ano 2022 --turno 2 --velocidade 30
    python eleicao/replay_tse.py --sintetico --ano-base 2026 --margem 4.5 --velocidade 30
    (em outro terminal) python eleicao/monitor.py --url http://127.0.0.1:8765 --ano-base 2022 ...

--velocidade 30: cada segundo real avança 30 segundos da apuração (17h-21h em 8 minutos).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apuracao import apurar  # noqa: E402
from dados_eleicao import secoes  # noqa: E402

ELE = "006258"
GRADE = np.arange(-30, 360.01, 0.5)


def passo(t: float) -> int:
    """Índice da GRADE em vigor no minuto t (após as 17h)."""
    return int(np.clip(np.searchsorted(GRADE, t, side="right") - 1, 0, len(GRADE) - 1))


def _num(x) -> str:
    return str(int(round(float(x))))


def _pct(a, b) -> str:
    return f"{(100 * a / b if b else 0):.2f}".replace(".", ",")


class Replay:
    def __init__(self, sec: pd.DataFrame, dia: str, velocidade: float, inicio: float):
        self.sec = sec
        self.munis = pd.Index(sorted(sec["cd_mun"].unique()))
        self.pos = {int(cd): j for j, cd in enumerate(self.munis)}
        g = sec.groupby("cd_mun")
        self.uf_de = g["uf"].first().loc[self.munis].to_numpy()
        self.nome = g["nm_mun"].first().loc[self.munis].to_numpy()
        self.ap = apurar(sec, self.munis, GRADE)
        self.dia, self.vel, self.inicio = dia, velocidade, inicio
        self.t0 = time.time()

    def agora(self) -> int:
        return passo(self.inicio + (time.time() - self.t0) * self.vel / 60.0)

    def _hora(self, k: int) -> str:
        minutos = 17 * 60 + GRADE[k]
        h, m = divmod(int(minutos), 60)
        s = int(round((minutos - int(minutos)) * 60))
        return f"{h % 24:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _soma(a, j):
        """Total do país (j None) ou valor do município j."""
        return float(a.sum()) if j is None else float(a[j])

    def _blocos(self, j, k):
        ap, tot, soma = self.ap, self.ap["tot"], self._soma
        ts, st = soma(tot["nsec"], j), soma(ap["nsec"][k], j)
        te, est = soma(tot["aptos"], j), soma(ap["aptos"][k], j)
        c = soma(ap["C"][k], j)
        s = {"ts": _num(ts), "st": _num(st), "pst": _pct(st, ts)}
        e = {"te": _num(te), "est": _num(est), "pest": _pct(est, te), "c": _num(c)}
        return s, e

    def arq_u(self, j, k, tpabr, cdabr) -> dict:
        s, e = self._blocos(j, k)
        F, L = self._soma(self.ap["F"][k], j), self._soma(self.ap["L"][k], j)
        cand = lambda n, v: {"n": n, "vap": _num(v), "pvap": _pct(v, F + L)}  # noqa: E731
        return {"ele": ELE.lstrip("0"), "t": "2", "tpabr": tpabr, "cdabr": cdabr,
                "dg": self.dia, "hg": self._hora(k), "dt": self.dia, "ht": self._hora(k),
                "s": s, "e": e,
                "carg": [{"cd": "1", "agr": [{"par": [{"cand": [cand("22", F)]}]},
                                              {"par": [{"cand": [cand("13", L)]}]}]}]}

    def arq_ab(self, uf: str, k: int) -> dict:
        abr = []
        for j in np.flatnonzero(self.uf_de == uf.upper()):
            s, e = self._blocos(j, k)
            abr.append({"tpabr": "mun", "cdabr": f"{self.munis[j]:05d}", "dt": self.dia,
                        "ht": self._hora(k), "s": s, "e": e})
        return {"ele": ELE.lstrip("0"), "t": "2", "dg": self.dia, "hg": self._hora(k), "abr": abr}

    def arq_cm(self) -> dict:
        abr = []
        for uf in sorted(set(self.uf_de)):
            js = np.flatnonzero(self.uf_de == uf)
            abr.append({"cd": uf.lower(), "ds": uf, "mu": [{"cd": f"{self.munis[j]:05d}", "nm": self.nome[j]} for j in js]})
        return {"abr": abr}


PAD_AB = re.compile(rf"dados/([a-z]{{2}})/\1-e{ELE}-ab\.json$")
PAD_U = re.compile(rf"dados/([a-z]{{2}})/\1(\d{{5}})-c0001-e{ELE}-u\.json$")


def responder(rep: Replay, caminho: str, k: int) -> dict | None:
    """O JSON que o TSE serviria em `caminho` no passo k da apuração (None = 404)."""
    p = caminho.split("?")[0]
    if p.endswith(f"config/mun-e{ELE}-cm.json"):
        return rep.arq_cm()
    if p.endswith(f"dados/br/br-c0001-e{ELE}-u.json"):
        return rep.arq_u(None, k, "br", "br")
    if m := PAD_AB.search(p):
        return rep.arq_ab(m.group(1), k)
    if m := PAD_U.search(p):
        j = rep.pos.get(int(m.group(2)), -1)
        if j >= 0:
            return rep.arq_u(j, k, "mu", m.group(2))
    return None


def servir(rep: Replay, porta: int) -> None:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso
            pass

        def do_GET(self):
            corpo = responder(rep, self.path, rep.agora())
            if corpo is None:
                self.send_response(404)
                self.end_headers()
                return
            dados = json.dumps(corpo).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    print(f"replay em http://127.0.0.1:{porta} (Ctrl+C para parar)", flush=True)
    srv.serve_forever()


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--ano", type=int, default=2022)
    a.add_argument("--turno", type=int, default=2)
    a.add_argument("--sintetico", action="store_true")
    a.add_argument("--ano-base", type=int, default=2026)
    a.add_argument("--margem", type=float, default=4.0)
    a.add_argument("--semente", type=int, default=1)
    a.add_argument("--velocidade", type=float, default=30.0)
    a.add_argument("--inicio", type=float, default=-2.0, help="minuto (após 17h) em que começa")
    a.add_argument("--porta", type=int, default=8765)
    args = a.parse_args()
    if args.sintetico:
        from simulacao import gerar_apuracao, sortear_cenario
        rng = np.random.default_rng(args.semente)
        sec = gerar_apuracao(secoes(args.ano_base, 1, "bu"), args.ano_base, secoes(2022, 2, "bu"),
                             sortear_cenario(args.margem, rng), rng)
        dia = "25/10/2026"
    else:
        sec = secoes(args.ano, args.turno, "bu")
        dia = {2022: "30/10/2022" if args.turno == 2 else "02/10/2022",
               2026: "04/10/2026"}.get(args.ano, "01/01/2000")
    rep = Replay(sec, dia, args.velocidade, args.inicio)
    final = (rep.ap["tot"]["F"].sum() - rep.ap["tot"]["L"].sum()) / (rep.ap["tot"]["F"].sum() + rep.ap["tot"]["L"].sum()) * 100
    print(f"apuração com {len(sec)} seções, {len(rep.munis)} municípios; margem final F {final:+.2f}")
    servir(rep, args.porta)


if __name__ == "__main__":
    main()
