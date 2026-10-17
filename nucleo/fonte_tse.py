"""Leitura dos JSON públicos de divulgação de resultados do TSE (só leitura).

Arquivos usados (2º turno de 2026 = eleição 6258):
  config/mun-e006258-cm.json                 municípios (código TSE, UF, nome)
  dados/{uf}/{uf}-e006258-ab.json            por município: seções e eleitorado totalizados
  dados/{uf}/{uf}{mun}-c0001-e006258-u.json  por município: votos de cada candidato
  dados/br/br-c0001-e006258-u.json           totais do país (para conferência)
A CDN do TSE guarda cada arquivo por ~55 s; consultar mais rápido que isso não adianta.
"""
from __future__ import annotations

import concurrent.futures as cf
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import requests

URL_OFICIAL = "https://resultados.tse.jus.br/oficial/ele2026/6258"
AB_VALIDADE = 120.0  # s: até quando vale a última abrangência de uma UF cuja leitura atrasou


class Conexoes:
    """n threads que atendem uma fila de pedidos em ordem, entre um ciclo e outro.

    Como um ThreadPoolExecutor, mas as threads são daemon: com o TSE pendurado, a fila pode ter
    centenas de pedidos, e o ThreadPoolExecutor só deixa o programa sair (Ctrl+C) depois de
    atender todos.
    """

    def __init__(self, n: int):
        self.n, self.fila = n, queue.SimpleQueue()
        for _ in range(n):
            threading.Thread(target=self._atender, daemon=True).start()

    def submit(self, fn, *args) -> cf.Future:
        fu = cf.Future()
        self.fila.put((fu, fn, args))
        return fu

    def fechar(self) -> None:
        for _ in range(self.n):
            self.fila.put(None)

    def _atender(self) -> None:
        while (item := self.fila.get()) is not None:
            fu, fn, args = item
            if not fu.set_running_or_notify_cancel():  # cancelado ainda na fila
                continue
            try:
                fu.set_result(fn(*args))
            except BaseException as e:
                fu.set_exception(e)


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
    sessao: requests.Session = field(default_factory=requests.Session)
    falhas: int = 0                 # municípios que falharam no último varios()
    atrasados: int = 0              # municípios ainda a caminho no fim do último varios()
    erro_exemplo: str | None = None

    def __post_init__(self):
        self.sessao.headers.update({"User-Agent": "monitor-apuracao (leitura publica)"})
        # municípios e abrangências podem estar no ar ao mesmo tempo (ver varios)
        a = requests.adapters.HTTPAdapter(pool_connections=self.workers, pool_maxsize=2 * self.workers)
        self.sessao.mount("https://", a)
        self.sessao.mount("http://", a)
        self._duracoes = deque(maxlen=200)  # s das últimas respostas, para o timeout da 1ª tentativa
        self._trava = threading.Lock()
        self._pool = self._pool_ab = None   # criados no primeiro uso; seguem entre ciclos
        self._no_ar: dict[tuple[str, int], cf.Future] = {}
        self._ab_no_ar: dict[str, cf.Future] = {}
        self._ab: dict[str, tuple[float, dict]] = {}  # uf -> (quando chegou, abrangência)

    def fechar(self) -> None:
        """Tira da fila o que ainda não começou e encerra as threads (o painel, ao parar a sessão)."""
        for fu in [*self._no_ar.values(), *self._ab_no_ar.values()]:
            fu.cancel()
        for p in (self._pool, self._pool_ab):
            if p is not None:
                p.fechar()
        self._pool = self._pool_ab = None
        self._no_ar.clear()
        self._ab_no_ar.clear()

    def _timeouts(self) -> tuple[float, float, float]:
        """Segundos de cada tentativa. A 1ª é 4x a mediana das últimas respostas, entre 6 e 15 s:
        corta cedo um pedido pendurado sem cortar um TSE que está só lento (com 6 s fixos, um TSE
        respondendo em 8 s falharia sempre na 1ª). As outras dão mais tempo."""
        with self._trava:
            d = sorted(self._duracoes)
        primeira = min(15.0, max(6.0, 4 * d[len(d) // 2])) if d else 6.0
        return primeira, max(primeira, 10.0), 15.0

    def _get(self, caminho: str):
        """JSON de `caminho` (None se 404), com até 3 tentativas."""
        url = f"{self.base_url}/{caminho}"
        limites = self._timeouts()
        for k, limite in enumerate(limites):
            try:
                t0 = time.monotonic()
                r = self.sessao.get(url, timeout=limite)
                if r.status_code != 404:
                    r.raise_for_status()
                with self._trava:
                    self._duracoes.append(time.monotonic() - t0)
                return None if r.status_code == 404 else r.json()
            except Exception:
                if k == len(limites) - 1:
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

    def _abrangencia_hora(self, uf: str) -> tuple[float, dict[int, Municipio]]:
        ab = self.abrangencia(uf)
        return time.monotonic(), ab

    def abrangencias(self, ufs: list[str], prazo: float | None = None) -> dict[str, dict[int, Municipio] | None]:
        """{uf: abrangência}, lidas 8 por vez; None quando a UF não tem uma recente.

        Com `prazo` (segundos), a leitura que não terminou segue no ar e entra no próximo ciclo;
        enquanto isso vale a última que chegou, se tiver até AB_VALIDADE s. Sem nenhuma (ou com o
        arquivo vazio), None: o monitor faz rodízio pelos municípios dessa UF.
        """
        if self._pool_ab is None:
            self._pool_ab = Conexoes(8)
        for uf in ufs:
            if uf not in self._ab_no_ar:
                self._ab_no_ar[uf] = self._pool_ab.submit(self._abrangencia_hora, uf)
        cf.wait(list(self._ab_no_ar.values()), timeout=prazo)
        for uf, fu in list(self._ab_no_ar.items()):
            if not fu.done():
                continue
            del self._ab_no_ar[uf]
            try:
                quando, ab = fu.result()
            except Exception:  # erro: vale a anterior, se for recente
                continue
            if ab:
                self._ab[uf] = (quando, ab)
            else:
                self._ab.pop(uf, None)
        agora = time.monotonic()
        return {uf: (self._ab[uf][1] if uf in self._ab and agora - self._ab[uf][0] <= AB_VALIDADE else None)
                for uf in ufs}

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

    def varios(self, pedidos: list[tuple[str, int]], prazo: float | None = None) -> list[Municipio]:
        """Baixa em paralelo os votos de vários municípios [(uf, cd), ...].

        Os que falham ficam para o próximo ciclo. Quantos falharam (erro ou arquivo ausente) fica
        em self.falhas e o primeiro erro em self.erro_exemplo: uma falha em massa não pode passar
        calada, porque na volta o modelo recebe tudo de uma vez e distorce (ver monitor.py).
        Com `prazo` (segundos), o ciclo para de esperar ali, mas nada se perde: os pedidos seguem
        baixando e o que chegar entra no próximo ciclo (self.atrasados conta os que ainda estão a
        caminho). Os que nem tinham começado saem da fila no próximo ciclo, que tem outra ordem.
        Assim um TSE lento não segura o ciclo, e as 16 conexões não ficam paradas entre ciclos.
        """
        self.falhas, self.atrasados, self.erro_exemplo = 0, 0, None
        if self._pool is None:
            self._pool = Conexoes(self.workers)
        for chave, fu in list(self._no_ar.items()):
            if fu.cancel():  # ainda na fila do ciclo anterior
                del self._no_ar[chave]
        for chave in pedidos:
            if chave not in self._no_ar:
                self._no_ar[chave] = self._pool.submit(self.votos_municipio, *chave)
        cf.wait(list(self._no_ar.values()), timeout=prazo)
        out = []
        for chave, fu in list(self._no_ar.items()):
            if not fu.done():
                self.atrasados += 1
                continue
            del self._no_ar[chave]
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
