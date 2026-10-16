"""Leitura dos JSON públicos de divulgação de resultados do TSE (só leitura).

Arquivos usados (2º turno de 2026 = eleição 6258):
  config/mun-e006258-cm.json                 municípios (código TSE, UF, nome)
  dados/{uf}/{uf}-e006258-ab.json            por município: seções e eleitorado totalizados
  dados/{uf}/{uf}{mun}-c0001-e006258-u.json  por município: votos de cada candidato
  dados/br/br-c0001-e006258-u.json           totais do país (para conferência)
A CDN do TSE guarda cada arquivo por ~40 s; consultar mais rápido que isso não adianta.
"""
from __future__ import annotations

import concurrent.futures as cf
import time
from dataclasses import dataclass, field

import requests

URL_OFICIAL = "https://resultados.tse.jus.br/oficial/ele2026/6258"


def _int(x) -> int:
    try:
        return int(str(x).replace(".", "").replace(",", "") or 0)
    except ValueError:
        return 0


@dataclass
class Municipio:
    uf: str
    cd: int
    ts: int = 0        # seções
    st: int = 0        # seções totalizadas
    te: int = 0        # eleitorado
    est: int = 0       # eleitorado das seções totalizadas
    F: int = 0
    L: int = 0
    hora: str = ""     # dt/ht do TSE na última atualização


@dataclass
class FonteTSE:
    base_url: str = URL_OFICIAL
    eleicao: str = "006258"
    cand_F: str = "22"
    cand_L: str = "13"
    workers: int = 16
    timeout: float = 15.0
    sessao: requests.Session = field(default_factory=requests.Session)
    falhas: int = 0                 # municípios que falharam no último varios()
    erro_exemplo: str | None = None

    def __post_init__(self):
        self.sessao.headers.update({"User-Agent": "monitor-apuracao (leitura publica)"})
        a = requests.adapters.HTTPAdapter(pool_connections=self.workers, pool_maxsize=self.workers)
        self.sessao.mount("https://", a)
        self.sessao.mount("http://", a)

    def _get(self, caminho: str, tentativas: int = 3):
        url = f"{self.base_url}/{caminho}"
        for k in range(tentativas):
            try:
                r = self.sessao.get(url, timeout=self.timeout)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except Exception:
                if k == tentativas - 1:
                    raise
                time.sleep(0.5 * (k + 1))

    def municipios(self) -> dict[int, tuple[str, str]]:
        """{cd_mun: (uf, nome)} pelo arquivo de configuração da eleição."""
        d = self._get(f"config/mun-e{self.eleicao}-cm.json")
        out = {}
        for abr in d["abr"]:
            for m in abr["mu"]:
                out[int(m["cd"])] = (abr["cd"].upper(), m["nm"])
        return out

    def abrangencia(self, uf: str) -> dict[int, Municipio]:
        """Situação de cada município da UF (seções/eleitorado totalizados)."""
        u = uf.lower()
        d = self._get(f"dados/{u}/{u}-e{self.eleicao}-ab.json")
        out = {}
        for a in (d or {}).get("abr", []):
            if a.get("tpabr") != "mun":
                continue
            s, e = a.get("s", {}), a.get("e", {})
            cd = int(a["cdabr"])
            out[cd] = Municipio(uf=uf.upper(), cd=cd, ts=_int(s.get("ts")), st=_int(s.get("st")),
                                te=_int(e.get("te")), est=_int(e.get("est")),
                                hora=f"{a.get('dt', '')} {a.get('ht', '')}".strip())
        return out

    def votos_municipio(self, uf: str, cd: int) -> Municipio | None:
        u = uf.lower()
        d = self._get(f"dados/{u}/{u}{cd:05d}-c0001-e{self.eleicao}-u.json")
        if not d:
            return None
        return self._parse_u(d, uf, cd)

    def _parse_u(self, d: dict, uf: str, cd: int) -> Municipio:
        s, e = d.get("s", {}), d.get("e", {})
        m = Municipio(uf=uf.upper(), cd=cd, ts=_int(s.get("ts")), st=_int(s.get("st")),
                      te=_int(e.get("te")), est=_int(e.get("est")),
                      hora=f"{d.get('dt', '')} {d.get('ht', '')}".strip())
        for agr in d["carg"][0].get("agr", []):
            for par in agr.get("par", []):
                for c in par.get("cand", []):
                    if c.get("n") == self.cand_F:
                        m.F = _int(c.get("vap"))
                    elif c.get("n") == self.cand_L:
                        m.L = _int(c.get("vap"))
        return m

    def brasil(self) -> dict:
        d = self._get(f"dados/br/br-c0001-e{self.eleicao}-u.json")
        m = self._parse_u(d, "BR", 0)
        return {"F": m.F, "L": m.L, "st": m.st, "ts": m.ts, "est": m.est, "te": m.te,
                "gerado": f"{d.get('dg', '')} {d.get('hg', '')}".strip(), "hora": m.hora}

    def varios(self, pedidos: list[tuple[str, int]]) -> list[Municipio]:
        """Baixa em paralelo os votos de vários municípios [(uf, cd), ...].

        Os que falham ficam para o próximo ciclo. Quantos falharam (erro ou arquivo ausente) fica
        em self.falhas e o primeiro erro em self.erro_exemplo: uma falha em massa não pode passar
        calada, porque na volta o modelo recebe tudo de uma vez e distorce (ver monitor.py).
        """
        self.falhas, self.erro_exemplo = 0, None
        if not pedidos:
            return []
        out = []
        with cf.ThreadPoolExecutor(self.workers) as ex:
            futs = [ex.submit(self.votos_municipio, uf, cd) for uf, cd in pedidos]
            for fu in cf.as_completed(futs):
                try:
                    m = fu.result()
                except Exception as e:
                    self.falhas += 1
                    self.erro_exemplo = self.erro_exemplo or repr(e)
                    continue
                if m is None:  # 404: o arquivo do município não existe (ainda)
                    self.falhas += 1
                    self.erro_exemplo = self.erro_exemplo or "arquivo não encontrado (404)"
                else:
                    out.append(m)
        return out
