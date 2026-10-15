"""Preços da Polymarket na noite do 1º turno de 2026 (4/10), só leitura.

Mercados: margem de vitória do 1º turno (faixas de 5 pontos) e vencedor do 1º turno.
Salva dados/polymarket_1t.parquet: uma linha por (mercado, faixa, minuto), com o preço do "Yes"
pela série /prices-history do CLOB (fidelity=1, ~1 ponto por minuto) e, para conferência, o
último negócio de cada minuto pela Data API.

    python eleicao/coleta/mercado_1t.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do projeto
from nucleo.dados_eleicao import DADOS  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
EVENTOS = {"margem": "brazil-presidential-election-first-round-margin-of-victory",
           "vencedor": "brazil-presidential-election-first-round-winner"}
BRT = timezone(timedelta(hours=-3))
INICIO = int(datetime(2026, 10, 4, 12, 0, tzinfo=BRT).timestamp())   # 12h de Brasília
FIM = int(datetime(2026, 10, 5, 2, 0, tzinfo=BRT).timestamp())       # 2h do dia seguinte
H17 = int(datetime(2026, 10, 4, 17, 0, tzinfo=BRT).timestamp())


def _get(url: str, params: dict | None = None, tentativas: int = 6):
    espera = 1.0
    for _ in range(tentativas):
        try:
            r = requests.get(url, params=params, timeout=60,
                             headers={"User-Agent": "pesquisa (somente leitura)"})
            if r.status_code in (429,) or r.status_code >= 500:
                time.sleep(espera)
                espera *= 2
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(espera)
            espera *= 2
    raise RuntimeError(f"falhou: {url}")


def faixas(slug: str) -> list[dict]:
    ev = _get(f"{GAMMA}/events", {"slug": slug})[0]
    out = []
    for m in ev["markets"]:
        tokens = json.loads(m.get("clobTokenIds") or "[]")
        precos = json.loads(m.get("outcomePrices") or "[]")
        out.append({"faixa": m.get("groupItemTitle") or m.get("question"), "condition": m["conditionId"],
                    "token_sim": tokens[0] if tokens else None,
                    "venceu": bool(precos and float(precos[0]) > 0.5)})
    return out


def serie_precos(token: str) -> pd.DataFrame:
    d = _get(f"{CLOB}/prices-history", {"market": token, "startTs": INICIO, "endTs": FIM, "fidelity": 1})
    h = (d or {}).get("history", [])
    return pd.DataFrame({"ts": [int(x["t"]) for x in h], "preco": [float(x["p"]) for x in h]})


def negocios(condition: str) -> pd.DataFrame:
    """Negócios (lado taker) da noite; preço convertido para o "Yes"."""
    linhas, fim = [], FIM
    for _ in range(40):
        lote = _get(f"{DATA_API}/trades", {"market": condition, "limit": 10000, "takerOnly": "true",
                                           "end": fim}) or []
        lote = [x for x in lote if INICIO <= int(x["timestamp"]) <= FIM]
        linhas += lote
        if len(lote) < 10000:
            break
        fim = min(int(x["timestamp"]) for x in lote) - 1
    if not linhas:
        return pd.DataFrame(columns=["ts", "preco_sim", "tamanho"])
    df = pd.DataFrame(linhas)
    sim = df["outcomeIndex"].astype(int) == 0
    preco = df["price"].astype(float)
    return pd.DataFrame({"ts": df["timestamp"].astype(int), "preco_sim": preco.where(sim, 1 - preco),
                         "tamanho": df["size"].astype(float)})


def main() -> None:
    partes = []
    for mercado, slug in EVENTOS.items():
        for f in faixas(slug):
            if not f["token_sim"]:
                continue
            p = serie_precos(f["token_sim"])
            n = negocios(f["condition"])
            # último negócio de cada minuto (conferência da série do CLOB)
            n["min"] = (n["ts"] - H17) // 60
            ult = n.sort_values("ts").groupby("min").agg(ultimo=("preco_sim", "last"),
                                                         volume=("tamanho", "sum"))
            p["min"] = (p["ts"] - H17) // 60
            p = p.groupby("min").last().join(ult, how="outer").reset_index()
            p["mercado"], p["faixa"], p["venceu"] = mercado, f["faixa"], f["venceu"]
            partes.append(p)
            print(f"{mercado:9s} {f['faixa']:30s} venceu={f['venceu']!s:5s} pontos={len(p)} "
                  f"negócios={len(n)}", flush=True)
    df = pd.concat(partes, ignore_index=True)
    saida = DADOS / "polymarket_1t.parquet"
    df.to_parquet(saida, index=False)
    print("salvo", saida)


if __name__ == "__main__":
    main()
