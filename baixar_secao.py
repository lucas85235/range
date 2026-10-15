"""Baixa "Presidente - Votação por seção eleitoral" (votacao_secao_{ano}_BR.zip) do TSE.

É só o cargo de Presidente, por seção, nos dois turnos, sem horário de chegada.
Saída: dados/secao_{ano}_{turno}t.parquet, uma linha por seção:
  uf, cd_mun, nm_mun, zona, secao, local, v<numero> (v95 branco, v96 nulo).

    python eleicao/baixar_secao.py 2014 2018 2022 2026
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # funciona também com python -P
from baixar_bu import DADOS, baixar  # noqa: E402

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_{ano}_BR.zip"
COLS = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO",
        "NR_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO"]


def processar(ano: int) -> None:
    pasta = DADOS / "secao_zip"
    pasta.mkdir(parents=True, exist_ok=True)
    z = baixar(URL.format(ano=ano), pasta / f"votacao_secao_{ano}_BR.zip")
    zf = zipfile.ZipFile(z)
    nome = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    partes = []
    with zf.open(nome) as f:
        for ch in pd.read_csv(f, sep=";", encoding="latin-1", usecols=lambda c: c in COLS,
                              dtype=str, chunksize=4_000_000):
            ch = ch[ch["CD_CARGO"].astype(int) == 1]
            partes.append(ch)
            print(f"  {ano}: {sum(len(p) for p in partes):,} linhas", flush=True)
    df = pd.concat(partes, ignore_index=True)
    df = df.rename(columns={"NR_TURNO": "turno", "SG_UF": "uf", "CD_MUNICIPIO": "cd_mun",
                            "NM_MUNICIPIO": "nm_mun", "NR_ZONA": "zona", "NR_SECAO": "secao",
                            "NR_VOTAVEL": "nr", "QT_VOTOS": "votos", "NR_LOCAL_VOTACAO": "local"})
    for c in ["turno", "cd_mun", "zona", "secao", "nr", "votos"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(-1).astype(int)
    df["local"] = pd.to_numeric(df["local"], errors="coerce").fillna(-1).astype(int)
    for turno, g in df.groupby("turno"):
        chave = ["uf", "cd_mun", "zona", "secao"]
        base = g.groupby(chave, sort=False)[["nm_mun", "local"]].first()
        votos = g.pivot_table(index=chave, columns="nr", values="votos", aggfunc="sum", fill_value=0)
        votos.columns = [f"v{int(c)}" for c in votos.columns]
        out = base.join(votos).reset_index()
        saida = DADOS / f"secao_{ano}_{turno}t.parquet"
        out.to_parquet(saida, index=False)
        vc = [c for c in out.columns if c.startswith("v")]
        tot = out[vc].sum().sort_values(ascending=False)
        print(f"salvo {saida.name}: {len(out)} seções; " +
              ", ".join(f"{k}={v:,}" for k, v in tot.head(6).items()), flush=True)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        processar(int(a))
