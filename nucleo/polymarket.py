"""Preços ao vivo do mercado de margem do 2º turno na Polymarket (só leitura).

A lista de mercados vem da API Gamma, mas o preço não: a Gamma passa por um cache de até 5 min
(Cache-Control: max-age=300), velho demais para a noite da apuração. Os preços saem do livro de
ofertas da CLOB, que é em tempo real: um POST /books com as 8 faixas de uma vez (~0,6 s).

CarteiraPolymarket lê, pela Data API pública, a posição e as compras e vendas de uma carteira
neste mercado. Só precisa do endereço (o do perfil na Polymarket): nada de chave, nada de ordem.
"""
from __future__ import annotations

import json
import re

import requests

GAMMA = "https://gamma-api.polymarket.com/events"
CLOB = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
SLUG = "brazil-presidential-election-second-round-margin-of-victory"
FAIXA_LIQUIDEZ = 0.02  # "dá para vender": cotas oferecidas até 2¢ abaixo do melhor preço
ENDERECO = re.compile(r"0x[0-9a-fA-F]{40}")


def nome_faixa(titulo: str) -> str | None:
    """"Flávio Bolsonaro <4%" → "F <4%"; None para o que não é faixa (ex.: "Other")."""
    lado = "F" if titulo.startswith("Fl") else "L" if titulo.startswith("Lula") else None
    return None if lado is None else f"{lado} {titulo.split()[-1]}"


class FontePolymarket:
    def __init__(self, slug: str = SLUG, timeout: float = 10.0):
        self.slug, self.timeout = slug, timeout
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": "monitor-apuracao (leitura publica)"})
        self._mercados: dict[str, dict] | None = None

    def mercados(self) -> dict[str, dict]:
        """{faixa: {"cid": conditionId, "sim": token do Sim, "nao": token do Não}} — muda só se o
        mercado for refeito, então é lido uma vez."""
        if self._mercados is None:
            r = self.sessao.get(GAMMA, params={"slug": self.slug}, timeout=self.timeout)
            r.raise_for_status()
            out = {}
            for m in r.json()[0]["markets"]:
                f = nome_faixa(m.get("groupItemTitle", ""))
                if f is None:
                    continue
                ids, lados = json.loads(m["clobTokenIds"]), json.loads(m["outcomes"])
                out[f] = {"cid": m["conditionId"], "sim": ids[lados.index("Yes")], "nao": ids[lados.index("No")]}
            self._mercados = out
        return self._mercados

    def tokens(self) -> dict[str, str]:
        """{faixa: token do Sim}."""
        return {f: x["sim"] for f, x in self.mercados().items()}

    def livros(self) -> dict[str, dict]:
        """{faixa: {bid, ask, bid_cotas, ask_cotas, ultimo, ts}} pelo livro de ofertas da CLOB.

        bid_cotas / ask_cotas: cotas oferecidas até FAIXA_LIQUIDEZ do melhor preço (quanto dá
        para vender ou comprar sem descer/subir mais que isso). ts: hora do livro (ms).
        """
        tokens = self.tokens()
        r = self.sessao.post(f"{CLOB}/books", json=[{"token_id": t} for t in tokens.values()], timeout=self.timeout)
        if r.status_code == 404:  # mercado refeito: lê os tokens de novo na próxima
            self._mercados = None
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


class CarteiraPolymarket:
    """Posição e operações de uma carteira neste mercado, pela Data API pública (só leitura).

    A Data API já filtra pelos conditionId das 8 faixas. As posições são o que a carteira tem
    agora; as operações (TRADE de compra e venda; SPLIT e MERGE, que criam e desfazem cotas de
    Sim e Não juntas; REDEEM e CONVERSION, raras) dão a hora de cada mudança, para refazer a
    carteira ciclo a ciclo.
    """

    def __init__(self, fonte: FontePolymarket, endereco: str, data_api: str = DATA_API):
        if not ENDERECO.fullmatch(endereco or ""):
            raise ValueError("endereço inválido: use o 0x… de 40 dígitos do seu perfil na Polymarket")
        self.fonte, self.endereco, self.data_api = fonte, endereco.lower(), data_api.rstrip("/")

    def _get(self, caminho: str, **params) -> list:
        r = self.fonte.sessao.get(f"{self.data_api}/{caminho}", timeout=self.fonte.timeout,
                                  params={"user": self.endereco, **params})
        r.raise_for_status()
        d = r.json()
        return d if isinstance(d, list) else []

    def ler(self) -> dict:
        m = self.fonte.mercados()
        cids = ",".join(x["cid"] for x in m.values())
        por_token = {tok: (f, lado) for f, x in m.items() for lado, tok in (("sim", x["sim"]), ("nao", x["nao"]))}
        por_cid = {x["cid"]: f for f, x in m.items()}
        posicoes = []
        for p in self._get("positions", market=cids, sizeThreshold=0, limit=500):
            f, lado = por_token.get(p.get("asset"), (por_cid.get(p.get("conditionId")), None))
            if f is None or not float(p.get("size") or 0):
                continue
            posicoes.append({"faixa": f, "lado": lado or ("sim" if p.get("outcome") == "Yes" else "nao"),
                             "cotas": float(p["size"]), "preco_medio": float(p.get("avgPrice") or 0),
                             "custo": float(p.get("initialValue") or 0), "valor": float(p.get("currentValue") or 0)})
        # em ordem crescente, uma operação nova entra no fim e não desloca as páginas. Conferido em
        # 17/10 com 12 carteiras deste mercado: compras − vendas (+ SPLIT − MERGE nos dois lados)
        # dão a posição atual
        operacoes = []
        for pagina in range(10):  # até 5.000 operações neste mercado
            lote = self._get("activity", market=cids, limit=500, offset=500 * pagina,
                             sortBy="TIMESTAMP", sortDirection="ASC")
            for a in lote:
                f, lado = por_token.get(a.get("asset"), (por_cid.get(a.get("conditionId")), None))
                if f is None:
                    continue
                operacoes.append({"ts": int(a.get("timestamp") or 0), "tipo": a.get("type") or "TRADE",
                                  "op": (a.get("side") or "").upper() or None, "faixa": f, "lado": lado,
                                  "cotas": float(a.get("size") or 0), "preco": float(a.get("price") or 0),
                                  "usdc": float(a.get("usdcSize") or 0)})
            if len(lote) < 500:
                break
        operacoes.sort(key=lambda o: o["ts"])
        return {"endereco": self.endereco, "posicoes": posicoes, "operacoes": operacoes}
