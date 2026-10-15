"""Painel da apuração no navegador: acompanha o TSE ao vivo e ensaia noites simuladas.

    python eleicao/painel.py                        # abre http://127.0.0.1:8050
    python eleicao/painel.py --ao-vivo              # 25/10: já começa a ler o TSE
    python eleicao/painel.py --retomar ultima       # depois de uma queda: continua a sessão gravada
    python eleicao/painel.py --faixa "F 4-8%" --degrau f90@2:100

Ao vivo, roda o mesmo monitor do terminal (monitor.py) a cada 40 s, com os preços públicos da
Polymarket, e grava o log em dados/ao_vivo/<sessão>/. Com --retomar (ou o botão da aba ao vivo),
recarrega os ciclos do log e refaz o modelo com os retratos da sessão. Na simulação, gera uma apuração sintética
do 2º turno (como estudos/rodar_simulacoes.py) e a reproduz em tempo acelerado, servindo ao monitor os
mesmos JSON do TSE (nucleo/replay_tse.py) direto da memória. O preço de mercado da simulação
é o de nucleo/mercado_sim.py: mistura do preço de hoje com a chance do modelo.

A página (painel.html) calcula a posição, o plano de venda, os alertas e a banca simulada a
partir dos ciclos que este servidor entrega. Só leitura: nada aqui envia ordens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import math
import re
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nucleo.dados_eleicao import secoes  # noqa: E402
from nucleo.fonte_tse import URL_OFICIAL, FonteTSE  # noqa: E402
from nucleo.mercado_sim import PRECO_HOJE, RITMOS, mercado_sim, sortear_margem  # noqa: E402
from nucleo.modelo import NOMES_FAIXAS, carregar_params, faixa_provavel  # noqa: E402
from nucleo.polymarket import FontePolymarket  # noqa: E402
from monitor import (AO_VIVO, BRT, Degrau, Monitor, achar_sessao, carregar_base, conferir_sessao,  # noqa: E402
                     ler_log, retratos)
from nucleo.replay_tse import GRADE, Replay, passo, responder  # noqa: E402
from nucleo.simulacao import gerar_apuracao, sortear_cenario  # noqa: E402

AQUI = Path(__file__).resolve().parent
PASSO_SIM = 1.0  # minutos simulados entre ciclos (o TSE troca os arquivos a cada ~40 s)
VELOCIDADES = [10, 30, 60, 120, 300]  # segundos simulados por segundo real
CENARIOS = [  # atalhos da página; margem None = sorteada pelas chances do mercado de hoje
    {"nome": "Às cegas (sorteio pelo mercado de hoje)", "margem": None},
    {"nome": "F +2,0 (F <4%, folgado)", "margem": 2.0},
    {"nome": "F +3,6 (F <4%, perto da fronteira)", "margem": 3.6},
    {"nome": "F +4,4 (F 4-8%, perto da fronteira)", "margem": 4.4},
    {"nome": "F +6,0 (F 4-8%, folgado)", "margem": 6.0},
    {"nome": "L +1,0 (Lula vence)", "margem": -1.0},
]
# ids únicos também entre reinícios do painel: a página que ficou aberta reconhece a sessão
# nova (retomada ou não) e recarrega os ciclos do zero
_ids = itertools.count(int(time.time() * 1000))


def limpo(x):
    """Converte para JSON válido (NaN/inf viram null; numpy vira Python)."""
    if isinstance(x, dict):
        return {str(k): limpo(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [limpo(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else None
    return x


def linha_terminal(res: dict) -> str:
    cab = f"[{res.get('gerado') or '?'}] +{res['t']:.0f}min | eleitorado {res['eleitorado_pct']:.1f}%"
    if "mu" not in res:
        return f"{cab} | {res.get('msg', '')}"
    top = sorted(res["probs"].items(), key=lambda kv: -kv[1])[:2]
    return (f"{cab} | modelo F {res['mu']:+.2f} ± {res['sd']:.2f} | "
            + "  ".join(f"{f} {p * 100:.0f}%" for f, p in top))


class Relogio:
    """Minutos simulados após as 17h; anda `vel` segundos simulados por segundo real."""

    def __init__(self, inicio: float, vel: float, pausado: bool = False):
        self._t, self._t_real, self.vel, self.pausado = inicio, time.time(), vel, pausado
        self._lock = threading.Lock()

    def _agora(self) -> float:
        return self._t if self.pausado else self._t + (time.time() - self._t_real) * self.vel / 60.0

    def agora(self) -> float:
        with self._lock:
            return self._agora()

    def ajustar(self, vel: float | None = None, pausado: bool | None = None) -> None:
        with self._lock:
            self._t, self._t_real = self._agora(), time.time()
            if vel is not None:
                self.vel = vel
            if pausado is not None:
                self.pausado = pausado


class FonteReplay(FonteTSE):
    """Responde do replay em memória, sem rede, congelado no passo `k` da apuração."""

    def __init__(self, rep: Replay):
        super().__init__(base_url="memoria://replay", workers=1)
        self.rep, self.k = rep, 0

    def _get(self, caminho: str, tentativas: int = 3):
        return responder(self.rep, caminho, self.k)

    def varios(self, pedidos):
        return [m for uf, cd in pedidos if (m := self.votos_municipio(uf, cd)) is not None]


class Sessao:
    """Uma corrida do monitor (ao vivo ou simulada) numa thread; a página lê `json()`."""

    tipo = ""

    def __init__(self, ctx: Contexto):
        self.ctx, self.id = ctx, next(_ids)
        self.ciclos: list[dict] = []
        self.eventos: list[dict] = []
        self.estado, self.erro = "preparando", None
        self.parar = threading.Event()
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def iniciar(self) -> Sessao:
        self.thread = threading.Thread(target=self._rodar_seguro, daemon=True)
        self.thread.start()
        return self

    def viva(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _rodar_seguro(self) -> None:
        try:
            self.rodar()
        except Exception as e:
            self.estado, self.erro = "erro", repr(e)
            self.evento(f"parou com erro: {e!r}", "erro")
            traceback.print_exc()

    def rodar(self) -> None:
        raise NotImplementedError

    def evento(self, texto: str, nivel: str = "info") -> None:
        with self.lock:
            self.eventos.append({"quando": dt.datetime.now(BRT).strftime("%H:%M:%S"), "texto": texto, "nivel": nivel})
            del self.eventos[:-100]

    def adicionar(self, res: dict) -> None:
        if "mu" in res:
            lo, hi = faixa_provavel(res["mu"], res["sd"], self.ctx.params.gl, 0.9)
            res["lo90"], res["hi90"] = lo, hi
        with self.lock:
            self.ciclos.append(limpo(res))

    def info(self) -> dict:
        return {}

    def json(self, desde: int) -> dict:
        with self.lock:
            return {"id": self.id, "tipo": self.tipo, "estado": self.estado, "erro": self.erro,
                    "n": len(self.ciclos), "desde": desde, "ciclos": self.ciclos[desde:],
                    "eventos": list(self.eventos), "info": limpo(self.info())}


class SessaoVivo(Sessao):
    tipo = "vivo"

    def __init__(self, ctx: Contexto, retomar: Path | None = None):
        super().__init__(ctx)
        a = ctx.args
        self.url, self.intervalo, self.polymarket = a.url.rstrip("/"), a.intervalo, not a.sem_polymarket
        self.retomada = retomar is not None
        self.pasta = retomar or AO_VIVO / dt.datetime.now(BRT).strftime("%Y%m%d_%H%M%S")
        self.antes = 0  # ciclos de antes da queda, lidos do log da sessão retomada
        self.n_retratos = 0

    def info(self) -> dict:
        return {"url": self.url, "intervalo": self.intervalo, "polymarket": self.polymarket,
                "pasta": str(self.pasta.relative_to(AQUI)) if self.pasta.is_relative_to(AQUI) else str(self.pasta),
                "retomada": self.retomada, "antes": self.antes, "retratos": self.n_retratos}

    def _avisar(self, texto: str, nivel: str = "info") -> None:
        self.evento(texto, nivel)
        print(f"[ao vivo] {texto}", flush=True)

    def _retomar(self, mon: Monitor) -> None:
        """Recarrega os ciclos do log (a página mostra o histórico já) e refaz o modelo."""
        antigos = ler_log(self.pasta)
        for res in antigos:
            self.adicionar(res)
        self.antes, self.n_retratos = len(antigos), len(retratos(self.pasta))
        self._avisar(f"retomando {self.pasta.name}: {len(antigos)} ciclos do log")
        t0 = time.time()
        n = mon.retomar(aviso=lambda txt: self._avisar(txt.strip(), "aviso" if "aviso" in txt else "info"))
        self._avisar(f"modelo refeito com {n} retratos em {time.time() - t0:.0f} s; seguindo na mesma pasta")

    def _gravar_mercado(self) -> None:
        """Grava em mercado.jsonl, na pasta da sessão, os preços lidos desde o último ciclo."""
        m = self.ctx.mercado
        if m is None or not self.pasta.is_dir():
            return
        with m.lock:
            novos, self._mercado_n = m.pontos[self._mercado_n:], len(m.pontos)
        if novos:
            with open(self.pasta / "mercado.jsonl", "a", encoding="utf-8") as f:
                for p in novos:
                    f.write(json.dumps({"hora": p["hora"], "t": round(p["t"], 3), "livros": p["livros"]},
                                       ensure_ascii=False) + "\n")

    def rodar(self) -> None:
        # o preço vem do leitor da Polymarket do painel (a cada 10 s), não de uma leitura por ciclo
        mercado = self.ctx.mercado.precos if (self.polymarket and self.ctx.mercado) else self.polymarket
        mon = Monitor(FonteTSE(base_url=self.url), 2026, 1, self.ctx.params, "F <4%", self.pasta,
                      polymarket=mercado, max_mun=self.ctx.args.max_municipios,
                      base_ordem=self.ctx.base_ordem)
        self._mercado_n = len(self.ctx.mercado.pontos) if self.ctx.mercado else 0
        try:
            if self.retomada:
                self._retomar(mon)
            self.estado = "rodando"
            self.evento(f"lendo {self.url} a cada {self.intervalo:g} s"
                        + (" + preços da Polymarket" if self.polymarket else ""))
            while not self.parar.is_set():
                t0 = time.time()
                try:
                    res = mon.ciclo()
                    self.adicionar(res)
                    self._gravar_mercado()
                    print("[ao vivo] " + linha_terminal(res), flush=True)
                    if res.get("mercado_erro"):
                        self.evento(f"Polymarket indisponível: {res['mercado_erro']}", "aviso")
                except Exception as e:  # rede instável: segue no próximo ciclo
                    self.evento(f"erro no ciclo: {e!r}", "erro")
                    print(f"[ao vivo] erro no ciclo: {e!r}", flush=True)
                self.parar.wait(max(1.0, self.intervalo - (time.time() - t0)))
        finally:
            mon.fechar()
        self.estado = "parado"
        self.evento("parado")


class MercadoAoVivo:
    """Lê o livro de ofertas da Polymarket a cada `intervalo` s, à parte do TSE: o preço anda mais
    rápido que a apuração e já existe antes dela. Guarda as leituras em memória; a sessão ao vivo
    as grava em disco (mercado.jsonl)."""

    def __init__(self, intervalo: float):
        self.fonte, self.intervalo = FontePolymarket(), intervalo
        self.pontos: list[dict] = []
        self.historico: dict | None = None
        self.erro: str | None = None
        self.lock = threading.Lock()
        self.parar = threading.Event()

    def iniciar(self) -> MercadoAoVivo:
        threading.Thread(target=self._rodar, daemon=True).start()
        return self

    def _rodar(self) -> None:
        try:  # contexto: os últimos 7 dias, de hora em hora
            h = self.fonte.historico()
            with self.lock:
                self.historico = h
        except Exception as e:
            self.erro = f"histórico indisponível: {e!r}"
        while not self.parar.is_set():
            t0 = time.time()
            try:
                livros = {f: {k: x[k] for k in ("bid", "ask", "bid_cotas", "ultimo")}
                          for f, x in self.fonte.livros().items()}
                agora = dt.datetime.now(BRT)
                ponto = {"quando": time.time(), "hora": agora.strftime("%H:%M:%S"),
                         "t": (agora - agora.replace(hour=17, minute=0, second=0, microsecond=0)).total_seconds() / 60,
                         "livros": livros}
                with self.lock:
                    self.pontos.append(ponto)
                    self.erro = None
            except Exception as e:  # rede instável: tenta de novo no próximo
                self.erro = repr(e)
            self.parar.wait(max(1.0, self.intervalo - (time.time() - t0)))

    def precos(self) -> dict[str, tuple[float, float]]:
        """O último preço lido, para o ciclo do monitor (lê agora se o último tiver mais de 1 min)."""
        with self.lock:
            p = self.pontos[-1] if self.pontos else None
        if p is None or time.time() - p["quando"] > 60:
            return self.fonte.precos()
        return {f: (x["bid"], x["ask"]) for f, x in p["livros"].items()}

    def json(self, desde: int) -> dict:
        with self.lock:
            n = len(self.pontos)
            if desde <= 0:  # primeira leitura da página: só as últimas 6 h
                limite = time.time() - 6 * 3600
                desde = next((i for i, p in enumerate(self.pontos) if p["quando"] >= limite), n)
            return {"n": n, "desde": desde, "pontos": self.pontos[desde:], "erro": self.erro,
                    "intervalo": self.intervalo, "historico": self.historico}


class SessaoSim(Sessao):
    tipo = "sim"

    def __init__(self, ctx: Contexto, margem: float | None, semente: int | None, vel: float, ritmo: str):
        super().__init__(ctx)
        self.margem_pedida, self.ritmo = margem, ritmo
        self.semente = int(semente) if semente is not None else int(np.random.default_rng().integers(1, 1_000_000))
        self.relogio = Relogio(-2.0, vel, pausado=True)
        self.pausa_usuario, self.revelado = False, False
        self.final = None
        self.cenario = None

    def info(self) -> dict:
        d = {"semente": self.semente, "ritmo": self.ritmo, "velocidade": self.relogio.vel,
             "pausado": self.pausa_usuario, "relogio": self.relogio.agora(), "revelado": self.revelado,
             "as_cegas": self.margem_pedida is None}
        if self.revelado and self.final is not None:
            c = self.cenario
            d["margem_final"] = self.final
            d["cenario"] = {"horarios": "1º turno de 2026 no ritmo de 2022" if c.molde_1t else "2º turno de 2022",
                            "gradiente_ordem": c.grad_ordem, "sd_regiao": c.sd_reg, "sd_uf": c.sd_uf,
                            "sd_municipio": c.sd_mun}
        return d

    def controlar(self, pausado: bool | None = None, velocidade: float | None = None,
                  revelar: bool = False) -> None:
        if pausado is not None:
            self.pausa_usuario = bool(pausado)
            if self.estado == "rodando":
                self.relogio.ajustar(pausado=self.pausa_usuario)
            self.evento("pausado" if pausado else "retomado")
        if velocidade is not None:
            self.relogio.ajustar(vel=float(velocidade))
        if revelar and not self.revelado:
            self.revelado = True
            self.evento("resultado revelado")

    def rodar(self) -> None:
        try:
            self._rodar()
        finally:  # acabou, parou ou deu erro: o relógio da noite simulada para junto
            self.relogio.ajustar(pausado=True)

    def _rodar(self) -> None:
        self.estado = "gerando"
        self.evento(f"gerando a apuração (semente {self.semente})...")
        sec1, ref2 = self.ctx.dados_sim()
        rng = np.random.default_rng(self.semente)
        margem = self.margem_pedida if self.margem_pedida is not None else sortear_margem(rng)
        self.cenario = sortear_cenario(margem, rng)
        rep = Replay(gerar_apuracao(sec1, 2026, ref2, self.cenario, rng), "25/10/2026", 0.0, 0.0)
        tot = rep.ap["tot"]
        F, L = tot["F"].sum(), tot["L"].sum()
        self.final = float((F - L) / (F + L) * 100)
        if self.parar.is_set():
            self.estado = "parado"
            return
        fonte = FonteReplay(rep)
        mon = Monitor(fonte, 2026, 1, self.ctx.params, "F <4%", None, max_mun=0,
                      base_ordem=self.ctx.base_ordem, gravar=False)
        self.estado = "rodando"
        self.relogio.ajustar(pausado=self.pausa_usuario)
        self.evento("apuração simulada começou (16h58)")
        while not self.parar.is_set():
            t = self.relogio.agora()
            fonte.k = passo(t)
            res = mon.ciclo()
            res["mercado"] = mercado_sim(res.get("probs"), res["t"], self.ritmo)
            self.adicionar(res)
            if res["eleitorado_pct"] >= 99.99 or t >= GRADE[-1]:
                self.estado, self.revelado = "fim", True
                self.evento(f"apuração terminou: margem final F {self.final:+.2f}")
                return
            alvo = t + PASSO_SIM
            while not self.parar.is_set() and self.relogio.agora() < alvo:
                time.sleep(0.05)
        self.estado = "parado"


class Contexto:
    """O que as sessões compartilham: parâmetros, base do 1º turno e as sessões atuais."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.params = carregar_params()
        print("carregando a base do 1º turno (~10 s)...", flush=True)
        self.base_ordem = carregar_base(2026, 1)
        self._dados_sim = None
        self._lock_dados = threading.Lock()
        self.lock = threading.Lock()
        self.vivo: SessaoVivo | None = None
        self.sim: SessaoSim | None = None
        self._retomavel = (0.0, None)
        # preços da Polymarket a cada intervalo_mercado s, desde já (não esperam o monitor do TSE)
        self.mercado = None if args.sem_polymarket else MercadoAoVivo(args.intervalo_mercado).iniciar()

    def dados_sim(self):
        with self._lock_dados:
            if self._dados_sim is None:
                self._dados_sim = (secoes(2026, 1, "bu"), secoes(2022, 2, "bu"))
            return self._dados_sim

    def config(self) -> dict:
        a = self.args
        plano = []
        for txt in a.degrau:
            Degrau(txt)  # valida
            plano.append(txt)
        return {"faixas": NOMES_FAIXAS, "faixa": a.faixa, "lado": a.lado, "alerta": a.alerta, "plano": plano,
                "ritmos": list(RITMOS), "preco_hoje": PRECO_HOJE, "cenarios": CENARIOS,
                "velocidades": VELOCIDADES, "url": a.url, "polymarket": not a.sem_polymarket,
                "intervalo": a.intervalo, "intervalo_mercado": a.intervalo_mercado}

    def iniciar_vivo(self, retomar: Path | None = None) -> SessaoVivo:
        with self.lock:
            if self.vivo and self.vivo.viva():
                if not self.vivo.parar.is_set():
                    return self.vivo
                raise ValueError("o monitor anterior ainda está fechando o último ciclo; tente de novo em alguns segundos")
            if retomar is not None:
                conferir_sessao(retomar, self.args.url.rstrip("/"), 2026, 1)
            self.vivo = SessaoVivo(self, retomar).iniciar()
            self._retomavel = (0.0, None)
            return self.vivo

    def retomavel(self) -> dict | None:
        """A sessão que o botão "Retomar" continuaria: a mais recente gravada lendo a mesma URL."""
        if self.vivo and self.vivo.viva():
            return None
        quando, d = self._retomavel
        if time.time() - quando > 5:
            p = achar_sessao("ultima", self.args.url.rstrip("/"))
            d = None
            if p is not None:
                log = ler_log(p)
                u = log[-1] if log else {}
                d = {"pasta": p.name, "ciclos": len(log), "retratos": len(retratos(p)),
                     "gerado": u.get("gerado"), "eleitorado_pct": u.get("eleitorado_pct")}
            self._retomavel = (time.time(), d)
        return d

    def parar_vivo(self) -> None:
        with self.lock:
            if self.vivo:
                self.vivo.parar.set()

    def trade_lote(self, d: dict) -> dict:
        """A regra de trade (trade.py) nas noites simuladas salvas, com os parâmetros da página."""
        from estudos import trade
        with self._lock_dados:
            if getattr(self, "_noites", None) is None:
                self._noites = trade.noites(self.params)
        ritmo = d.get("ritmo") or next(iter(RITMOS))
        if ritmo not in RITMOS:
            raise ValueError(f"ritmo desconhecido: {ritmo}")
        inicial = d.get("inicial") or "F <4%"
        if inicial == "dinheiro":  # começa sem posição e espera o sinal de compra
            inicial = None
        elif inicial not in NOMES_FAIXAS:
            raise ValueError(f"faixa desconhecida: {inicial}")
        regra = trade.Regra(inicial=inicial,
                            entrada=min(max(numero(d.get("entrada"), PRECO_HOJE.get(inicial, 0.5)), 0.01), 0.99),
                            banca=max(numero(d.get("banca"), 100.0), 1.0),
                            limiar=min(max(numero(d.get("limiar"), 0.7), 0.0), 1.0),
                            vantagem=numero(d.get("vantagem"), 0.05),
                            apurado_min=numero(d.get("apurado_min"), 2.0),
                            max_trocas=int(numero(d.get("max_trocas"), 2)))
        av = trade.lote(self._noites, regra, ritmo, self.params.gl)
        out = {**trade.resumo(av, regra.banca), "ritmo": ritmo, "noites": av.round(4).to_dict(orient="records")}
        if d.get("noite_real"):  # a mesma para os três ritmos: preços reais
            out["noite_real"] = trade.noite_real_1t(regra)
        return limpo(out)

    def iniciar_sim(self, margem, semente, vel, ritmo) -> SessaoSim:
        with self.lock:
            if self.sim:
                self.sim.parar.set()
            self.sim = SessaoSim(self, margem, semente, vel, ritmo).iniciar()
            return self.sim


def numero(x, padrao=None):
    if x is None or x == "":
        return padrao
    v = float(str(x).replace(",", "."))
    if not math.isfinite(v):
        raise ValueError("número inválido")
    return v


def criar_servidor(ctx: Contexto, porta: int) -> ThreadingHTTPServer:
    hosts = {f"127.0.0.1:{porta}", f"localhost:{porta}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso
            pass

        def _enviar(self, status: int, corpo: bytes, tipo: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, obj, status: int = 200) -> None:
            self._enviar(status, json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _host_ok(self) -> bool:  # contra DNS rebinding: só atende quem chamou 127.0.0.1/localhost
            if self.headers.get("Host") in hosts:
                return True
            self._json({"erro": "host não permitido"}, 403)
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                # relido a cada pedido: dá para editar a página e só recarregar
                self._enviar(200, (AQUI / "painel.html").read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/api/mercado":
                q = parse_qs(u.query)
                self._json(ctx.mercado.json(int(q.get("desde", ["0"])[0])) if ctx.mercado else {"desligado": True})
            elif u.path == "/api/config":
                self._json(ctx.config())
            elif u.path == "/api/estado":
                q = parse_qs(u.query)
                vivo = q.get("tipo", ["vivo"])[0] == "vivo"
                ses = ctx.vivo if vivo else ctx.sim
                extra = {"retomavel": ctx.retomavel()} if vivo else {}
                if ses is None:
                    self._json({"id": None, "estado": "parado", "n": 0, "ciclos": [], "eventos": [], "info": {}, **extra})
                    return
                desde = int(q.get("desde", ["0"])[0]) if q.get("id", [""])[0] == str(ses.id) else 0
                self._json({**ses.json(max(desde, 0)), **extra})
            else:
                self._json({"erro": "não encontrado"}, 404)

        def do_POST(self):
            if not self._host_ok():
                return
            # só JSON: força o preflight de CORS, que este servidor não responde, contra
            # pedidos vindos de outras páginas abertas no navegador
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._json({"erro": "use Content-Type: application/json"}, 415)
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(n) or b"{}")
                caminho = urlparse(self.path).path
                if caminho == "/api/vivo/iniciar":
                    nome, pasta = d.get("retomar"), None
                    if nome:  # só uma pasta de dados/ao_vivo/, pelo nome que o painel ofereceu
                        pasta = AO_VIVO / str(nome)
                        if not re.fullmatch(r"\d{8}_\d{6}", str(nome)) or not pasta.is_dir():
                            raise ValueError(f"sessão não encontrada: {nome}")
                    self._json({"id": ctx.iniciar_vivo(pasta).id})
                elif caminho == "/api/vivo/parar":
                    ctx.parar_vivo()
                    self._json({"ok": True})
                elif caminho == "/api/sim/iniciar":
                    ritmo = d.get("ritmo") or next(iter(RITMOS))
                    if ritmo not in RITMOS:
                        raise ValueError(f"ritmo desconhecido: {ritmo}")
                    margem = numero(d.get("margem"))
                    if margem is not None and not -30 <= margem <= 30:
                        raise ValueError("margem fora de -30 a +30")
                    semente = numero(d.get("semente"))
                    vel = min(max(numero(d.get("velocidade"), 60.0), 1.0), 3600.0)
                    ses = ctx.iniciar_sim(margem, None if semente is None else int(semente), vel, ritmo)
                    self._json({"id": ses.id, "semente": ses.semente})
                elif caminho == "/api/sim/controle":
                    if ctx.sim is None:
                        raise ValueError("nenhuma simulação")
                    if d.get("parar"):
                        ctx.sim.parar.set()
                    vel = numero(d.get("velocidade"))
                    ctx.sim.controlar(pausado=d.get("pausado"),
                                      velocidade=None if vel is None else min(max(vel, 1.0), 3600.0),
                                      revelar=bool(d.get("revelar")))
                    self._json({"ok": True})
                elif caminho == "/api/trade/lote":
                    self._json(ctx.trade_lote(d))
                else:
                    self._json({"erro": "não encontrado"}, 404)
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                self._json({"erro": str(e)}, 400)

    return ThreadingHTTPServer(("127.0.0.1", porta), H)


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--porta", type=int, default=8050)
    a.add_argument("--ao-vivo", action="store_true", help="começa já a ler o TSE")
    a.add_argument("--url", default=URL_OFICIAL, help="divulgação do TSE (ou um replay_tse.py local)")
    a.add_argument("--intervalo", type=float, default=40.0, help="segundos entre ciclos ao vivo")
    a.add_argument("--sem-polymarket", action="store_true", help="não busca os preços da Polymarket")
    a.add_argument("--intervalo-mercado", type=float, default=10.0,
                   help="segundos entre leituras do livro de ofertas da Polymarket")
    a.add_argument("--max-municipios", type=int, default=450, help="arquivos de município por ciclo ao vivo")
    a.add_argument("--faixa", default="F <4%", choices=NOMES_FAIXAS, help="posição inicial (dá para trocar na página)")
    a.add_argument("--lado", default="sim", choices=["sim", "nao"])
    a.add_argument("--alerta", type=float, default=0.5, help="avisa quando a chance da posição cai abaixo disto")
    a.add_argument("--degrau", action="append", default=[], help="degrau do plano CHANCE@APURADO:FRACAO (pode repetir)")
    a.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    a.add_argument("--retomar", metavar="PASTA",
                   help='já começa ao vivo continuando uma sessão gravada (depois de uma queda): "ultima" = '
                        'a mais recente que leu a mesma --url, ou a pasta (basta o nome, se estiver em dados/ao_vivo/)')
    args = a.parse_args()
    for txt in args.degrau:
        Degrau(txt)  # erro de digitação aparece já, não no meio da noite
    retomar = None
    if args.retomar:  # pasta errada ou de outra fonte aparece já, antes de carregar a base
        try:
            retomar = achar_sessao(args.retomar, args.url.rstrip("/"))
            if retomar is not None:
                conferir_sessao(retomar, args.url.rstrip("/"), 2026, 1)
        except (FileNotFoundError, ValueError) as e:
            a.error(str(e))
        if retomar is None:
            print(f"nada para retomar: nenhuma sessão das últimas 12 h em {AO_VIVO} leu {args.url.rstrip('/')} "
                  "e tem retratos; começando uma sessão nova", flush=True)
    ctx = Contexto(args)
    srv = criar_servidor(ctx, args.porta)
    url = f"http://127.0.0.1:{args.porta}/"
    print(f"painel em {url}  (simulação: {url}#sim)  — Ctrl+C para sair", flush=True)
    if args.ao_vivo or args.retomar:
        ctx.iniciar_vivo(retomar)
    if not args.sem_navegador:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ctx.parar_vivo()
        srv.server_close()


if __name__ == "__main__":
    main()
