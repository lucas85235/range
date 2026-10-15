"""Preços ao vivo do mercado de margem do 2º turno na Polymarket (só leitura).

A lista de mercados vem da API Gamma, mas o preço não: a Gamma passa por um cache de até 5 min
(Cache-Control: max-age=300), velho demais para a noite da apuração. Os preços saem do livro de
ofertas da CLOB, que é em tempo real: um POST /books com as 8 faixas de uma vez (~0,6 s).
"""
from __future__ import annotations

import json

import requests

GAMMA = "https://gamma-api.polymarket.com/events"
CLOB = "https://clob.polymarket.com"
SLUG = "brazil-presidential-election-second-round-margin-of-victory"
FAIXA_LIQUIDEZ = 0.02  # "dá para vender": cotas oferecidas até 2¢ abaixo do melhor preço


def nome_faixa(titulo: str) -> str | None:
    """"Flávio Bolsonaro <4%" → "F <4%"; None para o que não é faixa (ex.: "Other")."""
    lado = "F" if titulo.startswith("Fl") else "L" if titulo.startswith("Lula") else None
    return None if lado is None else f"{lado} {titulo.split()[-1]}"


class FontePolymarket:
    def __init__(self, slug: str = SLUG, timeout: float = 10.0):
        self.slug, self.timeout = slug, timeout
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": "monitor-apuracao (leitura publica)"})
        self._tokens: dict[str, str] | None = None

    def tokens(self) -> dict[str, str]:
        """{faixa: token do Sim} — muda só se o mercado for refeito, então é lido uma vez."""
        if self._tokens is None:
            r = self.sessao.get(GAMMA, params={"slug": self.slug}, timeout=self.timeout)
            r.raise_for_status()
            out = {}
            for m in r.json()[0]["markets"]:
                f = nome_faixa(m.get("groupItemTitle", ""))
                if f is None:
                    continue
                ids, lados = json.loads(m["clobTokenIds"]), json.loads(m["outcomes"])
                out[f] = ids[lados.index("Yes")]
            self._tokens = out
        return self._tokens

    def livros(self) -> dict[str, dict]:
        """{faixa: {bid, ask, bid_cotas, ask_cotas, ultimo, ts}} pelo livro de ofertas da CLOB.

        bid_cotas / ask_cotas: cotas oferecidas até FAIXA_LIQUIDEZ do melhor preço (quanto dá
        para vender ou comprar sem descer/subir mais que isso). ts: hora do livro (ms).
        """
        tokens = self.tokens()
        r = self.sessao.post(f"{CLOB}/books", json=[{"token_id": t} for t in tokens.values()], timeout=self.timeout)
        if r.status_code == 404:  # mercado refeito: lê os tokens de novo na próxima
            self._tokens = None
        r.raise_for_status()
        por_token = {b.get("asset_id"): b for b in r.json()}
        out = {}
        for f, tok in tokens.items():
            b = por_token.get(tok)
            if not b:
                continue
            bids = [(float(x["price"]), float(x["size"])) for x in b.get("bids", [])]
            asks = [(float(x["price"]), float(x["size"])) for x in b.get("asks", [])]
            bid = max((p for p, _ in bids), default=0.0)
            ask = min((p for p, _ in asks), default=1.0)
            ultimo = float(b.get("last_trade_price") or 0) or None
            out[f] = {"bid": bid, "ask": ask,
                      "bid_cotas": round(sum(s for p, s in bids if p >= bid - FAIXA_LIQUIDEZ - 1e-9), 1),
                      "ask_cotas": round(sum(s for p, s in asks if p <= ask + FAIXA_LIQUIDEZ + 1e-9), 1),
                      "ultimo": ultimo, "ts": int(b.get("timestamp") or 0)}
        return out

    def precos(self) -> dict[str, tuple[float, float]]:
        """{faixa: (bid, ask)}, o formato que o monitor grava em cada ciclo."""
        return {f: (x["bid"], x["ask"]) for f, x in self.livros().items()}

    def historico(self, intervalo: str = "1w", fidelidade: int = 60) -> dict[str, list[list[float]]]:
        """{faixa: [[unix_s, preço], ...]} do histórico de preços da CLOB (padrão: 7 dias, por hora)."""
        out = {}
        for f, tok in self.tokens().items():
            r = self.sessao.get(f"{CLOB}/prices-history", timeout=self.timeout,
                                params={"market": tok, "interval": intervalo, "fidelity": fidelidade})
            r.raise_for_status()
            out[f] = [[int(p["t"]), float(p["p"])] for p in r.json().get("history", [])]
        return out
