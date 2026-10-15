"""Baixa os Boletins de Urna (BU) do TSE e reduz a um cargo (padrão: Presidente).

Saída: dados/bu_{ano}_{turno}t.parquet (Presidente) ou bu_{ano}_{turno}t_{cargo}.parquet
(outros cargos, ex.: bu_2024_2t_prefeito.parquet), uma linha por seção:
  uf, cd_mun, nm_mun, zona, secao, aptos, comparecimento, tipo_urna,
  dt_bu (DT_BU_RECEBIDO; só existe com hora em 2022, 2024 e 2026),
  dt_enc (DT_ENCERRAMENTO), dt_emissao (DT_EMISSAO_BU), local (NR_LOCAL_VOTACAO, se houver),
  v<numero> = votos de cada número (v13, v22, ..., v95 = branco, v96 = nulo).

Os zips do 1º turno são grandes (todos os cargos): cada um é baixado, filtrado em
streaming e apagado. Os do 2º turno ficam em dados/bu_zip/.

    python eleicao/baixar_bu.py --ano 2022 --turno 2
    python eleicao/baixar_bu.py --ano 2024 --turno 1 --cargo 11 --ufs SP,RJ --workers 2
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
ZIPS = DADOS / "bu_zip"
PARTES = DADOS / "bu_partes"
CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-{ano}-boletim-de-urna"

# 2014 não tem cabeçalho: posições tiradas do LEIAME_BUWEB e conferidas numa linha
# (aptos 230 - abstenções 22 = comparecimento 208).
COLS_2014 = {"SG_UF": 4, "CD_CARGO_PERGUNTA": 5, "NR_ZONA": 7, "NR_SECAO": 8,
             "CD_MUNICIPIO": 12, "NM_MUNICIPIO": 13, "QT_APTOS": 15,
             "QT_COMPARECIMENTO": 17, "DS_TIPO_URNA": 20, "NR_VOTAVEL": 21, "QT_VOTOS": 23}
OPCIONAIS = ["DT_BU_RECEBIDO", "DT_ENCERRAMENTO", "DT_EMISSAO_BU", "NR_LOCAL_VOTACAO"]
# CD_CARGO_PERGUNTA -> DS_CARGO_PERGUNTA (o nome serve de pré-filtro rápido das linhas)
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 11: "Prefeito"}


def sufixo(cargo: int) -> str:
    """Presidente mantém os nomes de arquivo antigos; os outros cargos ganham sufixo."""
    return "" if cargo == 1 else f"_{CARGOS[cargo].lower()}"


def recursos(ano: int, turno: int) -> list[str]:
    r = requests.get(CKAN.format(ano=ano), timeout=60)
    r.raise_for_status()
    urls = [res["url"] for res in r.json()["result"]["resources"]]
    return sorted(u for u in urls if u.lower().endswith(".zip") and f"_{turno}t_" in u.lower())


def baixar(url: str, destino: Path, tentativas: int = 40) -> Path:
    """Baixa com retomada (HTTP Range): a CDN do TSE derruba conexões longas."""
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    tmp = destino.with_suffix(".parcial")
    total = None
    for k in range(tentativas):
        ja = tmp.stat().st_size if tmp.exists() else 0
        try:
            cab = {"Range": f"bytes={ja}-"} if ja else {}
            with requests.get(url, stream=True, timeout=60, headers=cab) as r:
                if r.status_code == 416:  # já está completo
                    break
                r.raise_for_status()
                if ja and r.status_code != 206:  # servidor ignorou o Range: recomeça
                    ja = 0
                if total is None:
                    cr = r.headers.get("Content-Range", "")
                    total = int(cr.split("/")[-1]) if "/" in cr else int(r.headers.get("Content-Length", 0)) + ja
                with open(tmp, "ab" if ja else "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
            if total is None or tmp.stat().st_size >= total:
                break
        except Exception as e:  # rede do TSE oscila; continua de onde parou
            if k % 5 == 4:
                print(f"  falha {url.split('/')[-1]} ({k + 1}/{tentativas}, "
                      f"{tmp.stat().st_size / 1e6 if tmp.exists() else 0:.0f}MB): {e}", flush=True)
            time.sleep(min(30, 2 * (k + 1)))
    else:
        raise RuntimeError(f"não baixou {url}")
    tmp.replace(destino)
    return destino


def _indices(cabecalho: list[str]) -> dict[str, int]:
    nomes = [c.strip().replace(" ", "").upper() for c in cabecalho]
    idx = {n: i for i, n in enumerate(nomes)}
    obrig = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA",
             "QT_APTOS", "QT_COMPARECIMENTO", "DS_TIPO_URNA", "NR_VOTAVEL", "QT_VOTOS"]
    out = {n: idx[n] for n in obrig}
    for n in OPCIONAIS:
        if n in idx:
            out[n] = idx[n]
    return out


def reduzir_zip(caminho: Path, cargo: int = 1) -> pd.DataFrame:
    """Lê o CSV de dentro do zip em streaming e devolve uma linha por seção (só `cargo`)."""
    nome_cargo = CARGOS[cargo][1:].encode()  # sem a inicial: "residente", "refeito"
    pre = (nome_cargo.lower(), nome_cargo.upper())
    cd = str(cargo)
    z = zipfile.ZipFile(caminho)
    nome = next(n for n in z.namelist() if n.lower().endswith((".csv", ".txt")))
    linhas = []
    with z.open(nome) as bruto:
        f = io.BufferedReader(bruto, 1 << 22)
        primeira = f.readline().decode("latin-1")
        if primeira.startswith('"DT_GERACAO"'):
            idx = _indices(next(csv.reader([primeira], delimiter=";")))
        else:  # 2014: sem cabeçalho, a primeira linha já é dado
            idx = dict(COLS_2014)
            f = _reencadear(primeira, f)
        i_cargo = idx["CD_CARGO_PERGUNTA"]
        for linha in f:
            if pre[0] not in linha and pre[1] not in linha:
                continue
            campos = next(csv.reader([linha.decode("latin-1")], delimiter=";"))
            if campos[i_cargo].strip() != cd:
                continue
            linhas.append([campos[i] for i in idx.values()])
    df = pd.DataFrame(linhas, columns=list(idx.keys()))
    return _secoes(df)


def _reencadear(primeira: str, resto):
    """Gera a primeira linha (já lida) seguida do resto do arquivo."""
    yield primeira.encode("latin-1")
    yield from resto


def _secoes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.rename(columns={"SG_UF": "uf", "CD_MUNICIPIO": "cd_mun", "NM_MUNICIPIO": "nm_mun",
                            "NR_ZONA": "zona", "NR_SECAO": "secao", "QT_APTOS": "aptos",
                            "QT_COMPARECIMENTO": "comparecimento", "DS_TIPO_URNA": "tipo_urna",
                            "NR_VOTAVEL": "nr", "QT_VOTOS": "votos", "DT_BU_RECEBIDO": "dt_bu",
                            "DT_ENCERRAMENTO": "dt_enc", "DT_EMISSAO_BU": "dt_emissao",
                            "NR_LOCAL_VOTACAO": "local"})
    df["uf"] = df["uf"].str.upper()
    df["cd_mun"] = df["cd_mun"].astype(int)
    for c in ["zona", "secao", "aptos", "comparecimento", "votos", "nr", "local"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(-1).astype(int)
    chave = ["uf", "cd_mun", "zona", "secao"]
    attrs = [c for c in ["nm_mun", "local", "aptos", "comparecimento", "tipo_urna", "dt_bu", "dt_enc",
                         "dt_emissao"] if c in df.columns]
    base = df.groupby(chave, sort=False)[attrs].first()
    votos = df.pivot_table(index=chave, columns="nr", values="votos", aggfunc="sum", fill_value=0)
    votos.columns = [f"v{int(c)}" for c in votos.columns]
    out = base.join(votos).reset_index()
    for c in ["dt_bu", "dt_enc", "dt_emissao"]:
        if c in out.columns:
            out[c] = ler_data(out[c])
    return out


def ler_data(s: pd.Series) -> pd.Series:
    """Datas do BU: '30/10/2022 19:01:21' (até 2022) ou '2026-10-04 18:16:01' (2026).
    2014 traz só a data em DT_BU_RECEBIDO; vira NaT (hora desconhecida)."""
    out = pd.to_datetime(s, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    falta = out.isna() & s.notna()
    if falta.any():
        out[falta] = pd.to_datetime(s[falta], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    return out


def tarefa(url: str, ano: int, turno: int, cargo: int = 1) -> str:
    PARTES.mkdir(parents=True, exist_ok=True)
    nome = url.split("/")[-1]
    parte = PARTES / f"{ano}_{turno}t{sufixo(cargo)}_{nome.replace('.zip', '.parquet')}"
    if parte.exists():
        return f"{nome}: já feito"
    ZIPS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    z = baixar(url, ZIPS / nome)
    t1 = time.time()
    df = reduzir_zip(z, cargo)
    df.to_parquet(parte, index=False)
    if turno == 1:
        z.unlink()  # 1º turno é grande demais para guardar
    return f"{nome}: {z.stat().st_size / 1e6 if z.exists() else 0:.0f}MB, {len(df)} seções, " \
           f"baixou {t1 - t0:.0f}s, leu {time.time() - t1:.0f}s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--turno", type=int, required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--ufs", default="", help="ex.: AC,SP (padrão: todas)")
    ap.add_argument("--cargo", type=int, default=1, choices=sorted(CARGOS),
                    help="CD_CARGO_PERGUNTA: 1 Presidente (padrão), 11 Prefeito")
    a = ap.parse_args()
    urls = recursos(a.ano, a.turno)
    if a.ufs:
        quer = {u.strip().upper() for u in a.ufs.split(",")}
        urls = [u for u in urls if u.split("/")[-1].split("_")[2].upper() in quer]
    # maiores primeiro, para o paralelismo render
    ordem = ["SP", "MG", "RJ", "BA", "RS", "PR", "PE", "CE", "PA", "SC", "GO", "MA"]
    urls.sort(key=lambda u: ordem.index(u.split("_")[2].upper()) if u.split("_")[2].upper() in ordem else 99)
    print(f"{a.ano} {a.turno}º turno, {CARGOS[a.cargo]}: {len(urls)} arquivos", flush=True)
    with cf.ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(tarefa, u, a.ano, a.turno, a.cargo): u for u in urls}
        for fu in cf.as_completed(futs):
            try:
                print(" ", fu.result(), flush=True)
            except Exception as e:
                print("  ERRO", futs[fu].split("/")[-1], e, flush=True)
    suf = sufixo(a.cargo)
    partes = sorted(PARTES.glob(f"{a.ano}_{a.turno}t{suf}_bweb_*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)
    vcols = sorted([c for c in df.columns if c.startswith("v")], key=lambda c: int(c[1:]))
    df[vcols] = df[vcols].fillna(0).astype(int)
    saida = DADOS / f"bu_{a.ano}_{a.turno}t{suf}.parquet"
    df.to_parquet(saida, index=False)
    tot = df[vcols].sum().sort_values(ascending=False)
    print(f"salvo {saida.name}: {len(df)} seções, {df['uf'].nunique()} UFs")
    print(tot.head(8).to_string())


if __name__ == "__main__":
    sys.exit(main())
