"""Monta a página do guia (resultados/guia_apuracao.html) com os dados de guia/guia_dados.py.

    python eleicao/guia/guia_dados.py && python eleicao/guia/guia_pagina.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))  # raiz do projeto
from nucleo.caminhos import RES  # noqa: E402


def enxugar(d: dict) -> dict:
    """Só o que a página usa, com casas decimais cortadas para a página ficar leve."""
    def r(v, n=4):
        return [None if x is None else round(float(x), n) for x in v]
    out = {}
    for k in ("sim_a", "sim_b"):
        s = d[k]
        out[k] = {"margem_final": s["margem_final"], "t": s["t"], "apurado": r(s["apurado"], 2),
                  "secoes": r(s["secoes"], 2), "w": r(s["w"], 2), "parcial": r(s["parcial"], 2),
                  "mu": r(s["mu"], 3), "sd": r(s["sd"], 3),
                  "probs": {f: r(v, 4) for f, v in s["probs"].items()}}
    R = d["real1t"]
    out["real1t"] = {"margem_final": R["margem_final"], "atraso_min": R["atraso_min"]}
    for k in ("modelo_final", "modelo_antes"):
        m = R[k]
        out["real1t"][k] = {"t": m["t"], "apurado": r(m["apurado"], 2), "mu": r(m["mu"], 3),
                            "sd": r(m["sd"], 3), "parcial": r(m["parcial"], 3),
                            "F <5%": r(m["F <5%"]), "L <5%": r(m["L <5%"])}
    pm = R["mercado"]
    out["real1t"]["mercado"] = {"t": pm["t"], "F <5%": r(pm["F <5%"]), "L <5%": r(pm["L <5%"])}
    arq_banca = RES / "banca_resumo.json"
    if arq_banca.exists():
        out["banca"] = json.loads(arq_banca.read_text(encoding="utf-8"))
    return out


def main() -> None:
    dados = json.loads((RES / "guia_dados.json").read_text(encoding="utf-8"))
    modelo = (AQUI / "guia_template.html").read_text(encoding="utf-8")
    js = json.dumps(enxugar(dados), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    saida = RES / "guia_apuracao.html"
    saida.write_text(modelo.replace("__DADOS__", js), encoding="utf-8")
    print(f"salvo {saida} ({saida.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
