"""Monitor ao vivo da apuração do 2º turno (TSE) com o modelo de margem.

Só leitura: consulta os JSON públicos do TSE e, se pedido, os preços públicos da Polymarket.
Não envia ordens (o Brasil é "close-only" na Polymarket; qualquer venda é manual).

    python eleicao/monitor.py --faixa "F <4%"                     # 25/10, a partir das 17h
    python eleicao/monitor.py --faixa "F 4-8%" --polymarket       # mostra também o mercado
    python eleicao/monitor.py --url http://127.0.0.1:8765 --faixa "F <4%"   # teste (replay)
    python eleicao/monitor.py --faixa "F <4%" --polymarket --retomar ultima   # depois de uma queda

Saídas em dados/ao_vivo/<sessão>/: log.jsonl (um resumo por ciclo), retratos .npz com os
acumulados por município (permitem refazer a noite depois) e sessao.json (URL e base). Com
--retomar, o monitor continua uma sessão gravada: refaz o modelo com os retratos e segue nela.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nucleo.dados_eleicao import DADOS, base_turno, secoes  # noqa: E402
from nucleo.fonte_tse import URL_OFICIAL, FonteTSE  # noqa: E402
from nucleo.modelo import (NOMES_FAIXAS, Ordem1T, Params, Transferencia, carregar_params,  # noqa: E402
                           faixa_provavel, faixas_cobertas, ingenuo, prob_faixas)

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
       "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO", "ZZ"]
BRT = dt.timezone(dt.timedelta(hours=-3))
SLUG = "brazil-presidential-election-second-round-margin-of-victory"
AO_VIVO = DADOS / "ao_vivo"


def minutos_desde_17h(data: str, hora: str) -> float | None:
    try:
        d = dt.datetime.strptime(f"{data} {hora}", "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None
    return (d - d.replace(hour=17, minute=0, second=0)).total_seconds() / 60


def precos_polymarket() -> dict[str, tuple[float, float]]:
    """{faixa: (bid, ask)} pela API pública Gamma (só leitura)."""
    r = requests.get("https://gamma-api.polymarket.com/events", params={"slug": SLUG}, timeout=10)
    r.raise_for_status()
    out = {}
    for m in r.json()[0]["markets"]:
        t = m.get("groupItemTitle", "")
        lado = "F" if t.startswith("Fl") else "L" if t.startswith("Lula") else None
        if lado is None:
            continue
        faixa = f"{lado} {t.split()[-1]}"
        out[faixa] = (float(m.get("bestBid") or 0), float(m.get("bestAsk") or 0))
    return out


class Degrau:
    """Um degrau do plano de venda, escrito como CHANCE@APURADO:FRACAO.

    CHANCE: % máximo de chance da posição para vender (ex.: 20), ou "f90" = quando a faixa
    provável de 90% deixa de dar chance à posição. APURADO: % mínimo do eleitorado apurado.
    FRACAO: % da posição a vender neste degrau. Ex.: "f90@2:50", "20@20:50".
    """

    def __init__(self, texto: str):
        self.texto = texto
        cond, resto = texto.split("@")
        ap, frac = resto.split(":") if ":" in resto else (resto, "100")
        self.f90 = cond.strip().lower() == "f90"
        self.chance = None if self.f90 else float(cond) / 100
        self.apurado, self.fracao = float(ap), float(frac)
        self.disparou = False

    def condicao(self) -> str:
        alvo = "faixa de 90% sair da posição" if self.f90 else f"chance ≤ {self.chance * 100:.0f}%"
        return f"{alvo}, desde {self.apurado:g}% apurado → vender {self.fracao:g}%"

    def testa(self, p_pos: float, apurado: float, fora: bool) -> bool:
        if self.disparou or apurado < self.apurado:
            return False
        return fora if self.f90 else p_pos <= self.chance


def carregar_base(ano_base: int, turno_base: int):
    """Base por município e ordem de chegada do 1º turno (demora ~10 s; o painel reaproveita)."""
    base = base_turno(ano_base, turno_base)
    sec1 = secoes(ano_base, turno_base, "auto")
    ordem = Ordem1T(sec1, base) if sec1["t"].notna().mean() > 0.9 else None
    if ordem is None:
        print("AVISO: sem hora de chegada do 1º turno (BU); modelo roda sem a ordem das seções")
    return base, ordem


# ---------- sessões gravadas (para retomar depois de uma queda) ----------

def retratos(pasta: Path) -> list[tuple[int, Path]]:
    """[(número do ciclo, arquivo)] dos retratos da sessão, em ordem."""
    achados = ((re.fullmatch(r"retrato_(\d+)\.npz", a.name), a) for a in pasta.glob("retrato_*.npz"))
    return sorted((int(m.group(1)), a) for m, a in achados if m)


def ler_log(pasta: Path) -> list[dict]:
    """Ciclos de log.jsonl; a linha cortada por uma queda no meio da escrita é pulada."""
    out = []
    arq = pasta / "log.jsonl"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(linha))
            except json.JSONDecodeError:
                pass
    return out


def ler_meta(pasta: Path) -> dict:
    try:
        return json.loads((pasta / "sessao.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recente(pasta: Path, horas: float = 12.0) -> bool:
    """A sessão (pasta com nome AAAAMMDD_HHMMSS) começou nas últimas `horas`."""
    try:
        criada = dt.datetime.strptime(pasta.name, "%Y%m%d_%H%M%S").replace(tzinfo=BRT)
    except ValueError:
        return False
    return dt.timedelta(0) <= dt.datetime.now(BRT) - criada <= dt.timedelta(hours=horas)


def achar_sessao(qual: str, url: str) -> Path | None:
    """Pasta a retomar. "ultima": a sessão mais recente em dados/ao_vivo/, das últimas 12 h, que
    leu a mesma URL e tem retratos (None se não houver). Ensaios contra o replay local e pré-voos
    de outros dias não entram no lugar da noite real. Senão, um caminho ou o nome de uma pasta
    de dados/ao_vivo/."""
    if qual.lower() == "ultima":
        pastas = sorted((p for p in AO_VIVO.iterdir() if p.is_dir()), reverse=True) if AO_VIVO.is_dir() else []
        return next((p for p in pastas if recente(p) and ler_meta(p).get("url") == url and retratos(p)), None)
    for p in (Path(qual), AO_VIVO / qual):
        if p.is_dir():
            return p.resolve()
    raise FileNotFoundError(f"pasta de sessão não encontrada: {qual}")


def conferir_sessao(pasta: Path, url: str, ano_base: int, turno_base: int) -> str | None:
    """Recusa retomar uma sessão de outra fonte ou base; devolve um aviso se não der para conferir."""
    meta = ler_meta(pasta)
    if not meta:
        return f"{pasta.name} não tem sessao.json (gravada antes desta versão): URL e base não conferidas"
    if meta.get("url") != url:
        raise ValueError(f"a sessão {pasta.name} leu {meta.get('url')}, não {url}; "
                         "retome com a mesma --url ou escolha outra pasta")
    if (meta.get("ano_base"), meta.get("turno_base")) != (ano_base, turno_base):
        raise ValueError(f"a sessão {pasta.name} usou a base {meta.get('ano_base')} "
                         f"{meta.get('turno_base')}º turno, não {ano_base} {turno_base}º turno")
    return None


def travar(pasta: Path):
    """Trava a pasta enquanto este processo grava nela (o sistema solta a trava se ele morrer):
    impede dois monitores (ou monitor e painel) escrevendo a mesma sessão."""
    f = open(pasta / ".trava", "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RuntimeError(f"a sessão {pasta.name} está aberta em outro monitor ou painel; "
                           "feche-o antes de retomar") from None
    return f


class Monitor:
    def __init__(self, fonte: FonteTSE, ano_base: int, turno_base: int, params: Params,
                 faixa: str, saida: Path, polymarket: bool = False, alerta: float = 0.5,
                 lado: str = "sim", max_mun: int = 450, plano: list[str] | None = None,
                 base_ordem=None, gravar: bool = True):
        self.fonte, self.params, self.faixa, self.lado = fonte, params, faixa, lado
        self.ano_base, self.turno_base = ano_base, turno_base
        self.max_mun = max_mun
        self.plano = [Degrau(x) for x in (plano or [])]
        self.polymarket, self.alerta = polymarket, alerta
        self.gravar = gravar
        self.base, self.ordem = base_ordem if base_ordem is not None else carregar_base(ano_base, turno_base)
        self.munis = self.base.index
        self.pos = {int(cd): j for j, cd in enumerate(self.munis)}
        self.uf = self.base["uf"].to_numpy()
        M = len(self.munis)
        self.F, self.L, self.est = np.zeros(M), np.zeros(M), np.zeros(M)
        self.st, self.ts = np.zeros(M, int), np.zeros(M, int)
        # eleitorado: o cadastro do 2º turno é o do 1º (aptos do BU); o TSE só confere
        aptos1 = self.base["aptos1"].to_numpy(float)
        self.te = np.where(np.isfinite(aptos1) & (aptos1 > 0), aptos1, 0.0)
        self.idx_uf = {u: np.flatnonzero(self.uf == u) for u in UFS}
        self.modelo: Transferencia | None = None
        self.saida = saida
        self.ultimo_alerta = 1.0
        self.ciclos = 0
        self._trava = None
        if gravar:
            saida.mkdir(parents=True, exist_ok=True)
            self._trava = travar(saida)
            ja = retratos(saida)
            self.ciclos = ja[-1][0] if ja else 0  # nunca sobrescreve um retrato
            if not ja and not ler_meta(saida):
                self._gravar_meta()

    def _gravar_meta(self) -> None:
        meta = {"url": self.fonte.base_url, "ano_base": self.ano_base, "turno_base": self.turno_base,
                "criada": dt.datetime.now(BRT).isoformat(timespec="seconds")}
        (self.saida / "sessao.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def fechar(self) -> None:
        """Solta a trava da pasta (o painel chama ao parar a sessão)."""
        if self._trava is not None:
            self._trava.close()
            self._trava = None

    def retomar(self, aviso=print) -> int:
        """Continua a sessão gravada em self.saida como se o monitor não tivesse parado.

        Passa os retratos, na ordem, pelo modelo (prever com o t de cada um): isso refaz o
        histórico com que ele julga a ordem de chegada (w). Restaura os acumulados do último
        retrato, e o próximo segue a numeração. O plano e o alerta são refeitos pelo log, para
        um degrau que já disparou não disparar de novo. Devolve quantos retratos entraram.
        """
        nota = conferir_sessao(self.saida, self.fonte.base_url, self.ano_base, self.turno_base)
        if nota:
            aviso(f"  aviso: {nota}")
            self._gravar_meta()
        log = self.saida / "log.jsonl"
        if log.exists() and log.stat().st_size:
            with open(log, "rb+") as f:  # linha cortada pela queda: a próxima começa numa linha nova
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
        arqs = retratos(self.saida)
        if arqs:
            aviso(f"  refazendo o modelo com {len(arqs)} retratos (~{0.1 * len(arqs):.0f} s)...")
        n = 0
        for _, arq in arqs:
            try:
                with np.load(arq) as r:
                    d = {c: r[c] for c in ("F", "L", "est", "st", "ts", "te", "t", "cd")}
            except Exception as e:  # retrato cortado pela queda
                aviso(f"  aviso: {arq.name} ilegível ({type(e).__name__}); pulado")
                continue
            if not np.array_equal(d["cd"], self.munis.to_numpy()):
                raise ValueError(f"{arq.name} tem outros municípios que a base de {self.ano_base} "
                                 f"({self.turno_base}º turno)")
            for nome in ("F", "L", "est", "st", "ts", "te"):
                getattr(self, nome)[:] = d[nome]
            if self.modelo is None:  # o modelo usa self.te (mesmo array), como na corrida original
                self.modelo = Transferencia(self.base, self.te, self.params, ordem=self.ordem)
                self.modelo.reiniciar()
            self.modelo.prever(self.F, self.L, self.est, t=float(d["t"]))
            n += 1
        if arqs:
            self.ciclos = max(self.ciclos, arqs[-1][0])
        for res in ler_log(self.saida):
            _, p_pos, _ = formatar_tela(res, self.faixa, self.lado)
            if p_pos is None:
                continue
            for deg in self.checar_plano(res, p_pos):
                aviso(f"  plano: degrau '{deg.texto}' já tinha disparado em {res.get('gerado') or '?'} "
                      f"(chance {p_pos * 100:.1f}%); não dispara de novo")
            if res.get("eleitorado_pct", 0) >= 1.0:
                self.ultimo_alerta = p_pos
        return n

    def _ab_todas(self) -> dict:
        """{uf: {cd: Municipio}}; None quando o arquivo da UF falta ou vem vazio."""
        import concurrent.futures as cf

        def uma(u):
            try:
                return u, (self.fonte.abrangencia(u) or None)
            except Exception:
                return u, None
        with cf.ThreadPoolExecutor(8) as ex:
            return dict(ex.map(uma, UFS))

    def _pedidos(self) -> list[tuple[str, int]]:
        """Municípios a (re)baixar neste ciclo, os mais desatualizados primeiro.

        O TSE responde ~15 arquivos/s por cliente; com o limite por ciclo, a prioridade é o
        eleitorado já apurado (arquivo de abrangência) que ainda não lemos. No backtest de
        2022, até 300 municípios por minuto deixaram o modelo praticamente igual.
        """
        prio = {}
        for uf, ab in self._ab_todas().items():
            js = self.idx_uf[uf]
            if not ab:  # sem abrangência confiável: rodízio pelos que ainda não acabaram
                for j in js:
                    if self.te[j] == 0 or self.ts[j] == 0 or self.st[j] < self.ts[j]:
                        prio[(uf, int(self.munis[j]))] = max(self.te[j] - self.est[j], 1.0) * 0.5
                continue
            for cd, m in ab.items():
                j = self.pos.get(cd, -1)
                if j < 0:
                    continue
                if self.te[j] == 0:
                    prio[(uf, cd)] = 1e12
                elif m.est > self.est[j] or m.st != self.st[j]:
                    prio[(uf, cd)] = max(m.est - self.est[j], 1.0)
        ordem = sorted(prio, key=prio.get, reverse=True)
        if self.modelo is not None and self.max_mun:
            ordem = ordem[: self.max_mun]
        return ordem

    def ciclo(self) -> dict | None:
        pedidos = self._pedidos()
        dif_te = 0
        for m in self.fonte.varios(pedidos):
            j = self.pos[m.cd]
            self.F[j], self.L[j], self.est[j], self.st[j], self.ts[j] = m.F, m.L, m.est, m.st, m.ts
            if self.te[j] == 0 and m.te > 0:
                self.te[j] = m.te
            elif m.te > 0 and abs(m.te - self.te[j]) > 0.02 * self.te[j]:
                dif_te += 1
        if self.modelo is None:
            self.modelo = Transferencia(self.base, self.te, self.params, ordem=self.ordem)
            self.modelo.reiniciar()
            print(f"{len(self.munis)} municípios na base; eleitorado {self.te.sum():,.0f}; "
                  f"{int(np.sum(self.te == 0))} sem eleitorado", flush=True)
        if dif_te:
            print(f"  aviso: {dif_te} municípios com eleitorado do TSE diferente do 1º turno (>2%)")
        br = self.fonte.brasil()
        data, hora = br["gerado"].split(" ") if " " in br["gerado"] else ("", "")
        t = minutos_desde_17h(data, hora)
        if t is None:
            agora = dt.datetime.now(BRT)
            t = (agora - agora.replace(hour=17, minute=0, second=0, microsecond=0)).total_seconds() / 60
        self.ciclos += 1
        res = {"t": t, "gerado": br["gerado"], "secoes_pct": 100 * br["st"] / max(br["ts"], 1),
               "eleitorado_pct": 100 * self.est.sum() / max(self.te.sum(), 1),
               "baixados": len(pedidos), "F_tse": br["F"], "L_tse": br["L"]}
        if self.polymarket:
            try:
                res["mercado"] = precos_polymarket()
            except Exception as e:
                res["mercado_erro"] = str(e)
        if self.F.sum() + self.L.sum() == 0:
            res["msg"] = "sem votos apurados ainda"
            return res
        r = self.modelo.prever(self.F, self.L, self.est, t=t)
        probs = prob_faixas(r["mu"], r["sd"], self.params.gl)
        res.update(parcial=ingenuo(self.F, self.L), parcial_tse=ingenuo(br["F"], br["L"]),
                   mu=r["mu"], sd=r["sd"], w=r["w_medio"],
                   probs=dict(zip(NOMES_FAIXAS, np.round(probs, 4).tolist())))
        if self.gravar:
            np.savez_compressed(self.saida / f"retrato_{self.ciclos:04d}.npz", F=self.F, L=self.L,
                                est=self.est, st=self.st, ts=self.ts, te=self.te, t=t, cd=self.munis.to_numpy())
            with open(self.saida / "log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
        return res

    def mostrar(self, res: dict) -> None:
        linhas, p_pos, nome_pos = formatar_tela(res, self.faixa, self.lado)
        print("\n" + "\n".join(linhas))
        if p_pos is None:
            return
        disparos = self.checar_plano(res, p_pos)
        for d in self.plano:
            marca = "x" if d.disparou else " "
            print(f"  plano [{marca}] {d.condicao()}")
        for d in disparos:
            print(f"  >>> PLANO: degrau '{d.texto}' disparou: vender {d.fracao:g}% da posição "
                  f"(chance {p_pos * 100:.1f}%, apurado {res['eleitorado_pct']:.1f}%)")
        if res.get("eleitorado_pct", 0) < 1.0:
            return  # com menos de 1% apurado o modelo ainda é quase só a priori: sem alertas
        if disparos or p_pos < self.alerta <= self.ultimo_alerta:
            if not disparos:
                print(f"  !!! ALERTA: chance da posição {nome_pos} caiu para {p_pos * 100:.1f}%")
            try:
                import winsound
                winsound.Beep(1000, 700)
            except Exception:
                print("\a")
        self.ultimo_alerta = p_pos

    def checar_plano(self, res: dict, p_pos: float) -> list[Degrau]:
        """Degraus do plano que disparam agora (cada um dispara uma vez só)."""
        if not self.plano or "mu" not in res:
            return []
        lo, hi = faixa_provavel(res["mu"], res["sd"], self.params.gl, 0.9)
        cobre = faixas_cobertas(lo, hi)
        # posição em Sim perde quando a faixa sai do intervalo; em Não, quando o intervalo
        # fica inteiro dentro da faixa
        fora = (self.faixa not in cobre) if self.lado == "sim" else (cobre == [self.faixa])
        disparos = [d for d in self.plano if d.testa(p_pos, res["eleitorado_pct"], fora)]
        for d in disparos:
            d.disparou = True
        return disparos


def formatar_tela(res: dict, faixa: str, lado: str = "sim") -> tuple[list[str], float | None, str]:
    """Linhas que o monitor imprime num ciclo, mais a chance da posição e o nome dela."""
    linhas = [f"[{res.get('gerado') or '?'}] +{res['t']:.0f}min | seções {res['secoes_pct']:.1f}% | "
              f"eleitorado {res['eleitorado_pct']:.1f}% | baixados {res.get('baixados', 0)}"]
    if "mu" not in res:
        return linhas + ["  " + res.get("msg", "")], None, ""
    linhas.append(f"  parcial (TSE): F {res['parcial_tse']:+.2f}   |   MODELO: F {res['mu']:+.2f} ± {res['sd']:.2f} "
                  f"(w {res['w']:.2f})")
    lo, hi = faixa_provavel(res["mu"], res["sd"], res.get("gl", 6.0), 0.9)
    cobre = faixas_cobertas(lo, hi)
    linhas.append(f"  faixa provável (90%): F {lo:+.2f} a F {hi:+.2f}  -> "
                  + (f"só {cobre[0]}" if len(cobre) == 1 else "cobre " + ", ".join(cobre)))
    mercado = res.get("mercado", {})
    for nome, p in res["probs"].items():
        if p < 0.0005 and nome != faixa and nome not in mercado:
            continue
        seta = ">>" if nome == faixa else "  "
        mk = mercado.get(nome)
        txt_mk = f"   mercado {mk[0] * 100:4.1f}/{mk[1] * 100:4.1f}" if mk else ""
        linhas.append(f"  {seta} {nome:8s} {p * 100:5.1f}%{txt_mk}")
    p_faixa = res["probs"].get(faixa)
    if p_faixa is None:
        return linhas, None, ""
    # chance de a posição pagar US$1 por cota e o preço pelo qual dá para vendê-la agora
    p_pos = p_faixa if lado == "sim" else 1 - p_faixa
    mk = mercado.get(faixa)
    bid = None if not mk else (mk[0] if lado == "sim" else 1 - mk[1])
    nome_pos = f"{'Sim' if lado == 'sim' else 'Não'} em '{faixa}'"
    linhas.append(f"  posição {nome_pos}: chance de pagar {p_pos * 100:.1f}%"
                  + (f" | dá para vender a ~{bid * 100:.1f}¢" if bid else ""))
    if bid and bid > p_pos:
        linhas.append(f"  !! modelo dá {p_pos * 100:.1f}% à posição, abaixo do preço de venda {bid * 100:.1f}¢")
    return linhas, p_pos, nome_pos


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--url", default=URL_OFICIAL)
    a.add_argument("--faixa", default="F <4%", choices=NOMES_FAIXAS)
    a.add_argument("--lado", default="sim", choices=["sim", "nao"], help="posição em Sim ou em Não")
    a.add_argument("--ano-base", type=int, default=2026)
    a.add_argument("--turno-base", type=int, default=1)
    a.add_argument("--intervalo", type=float, default=40.0, help="segundos entre ciclos")
    a.add_argument("--polymarket", action="store_true")
    a.add_argument("--alerta", type=float, default=0.5)
    a.add_argument("--ciclos", type=int, default=0, help="para depois de N ciclos (0 = sem fim)")
    a.add_argument("--max-municipios", type=int, default=450,
                   help="arquivos de município por ciclo (o TSE limita ~15/s por cliente)")
    a.add_argument("--degrau", action="append", default=[],
                   help="degrau do plano de venda CHANCE@APURADO:FRACAO, ex.: f90@2:50 ou 20@20:50 "
                        "(pode repetir; o monitor só avisa, não vende)")
    a.add_argument("--retomar", metavar="PASTA",
                   help='continua uma sessão gravada (depois de uma queda): "ultima" = a mais recente que '
                        'leu a mesma --url, ou a pasta (basta o nome, se estiver em dados/ao_vivo/)')
    args = a.parse_args()
    url = args.url.rstrip("/")
    pasta = None
    if args.retomar:  # pasta errada ou de outra fonte aparece já, antes de carregar a base
        try:
            pasta = achar_sessao(args.retomar, url)
            if pasta is not None:
                conferir_sessao(pasta, url, args.ano_base, args.turno_base)
        except (FileNotFoundError, ValueError) as e:
            a.error(str(e))
        if pasta is None:
            print(f"nada para retomar: nenhuma sessão das últimas 12 h em {AO_VIVO} leu {url} e tem "
                  "retratos; começando uma nova")
    retomando = pasta is not None
    pasta = pasta or AO_VIVO / dt.datetime.now(BRT).strftime("%Y%m%d_%H%M%S")
    try:
        mon = Monitor(FonteTSE(base_url=url), args.ano_base, args.turno_base, carregar_params(), args.faixa,
                      pasta, args.polymarket, args.alerta, args.lado, args.max_municipios, args.degrau)
    except RuntimeError as e:  # a pasta já está aberta em outro processo
        sys.exit(f"erro: {e}")
    print(f"monitor: {url} | posição: {args.lado} em {args.faixa} | base {args.ano_base} {args.turno_base}º turno | "
          f"ordem do 1º turno: {'sim' if mon.ordem is not None else 'não'}")
    print(f"sessão: {pasta}" + (" (retomada)" if retomando else ""), flush=True)
    if retomando:
        t0 = time.time()
        try:
            n = mon.retomar()
        except ValueError as e:
            sys.exit(f"erro ao retomar: {e}")
        u = next((r for r in reversed(ler_log(pasta)) if "mu" in r), None)
        print(f"retomada: modelo refeito com {n} retratos em {time.time() - t0:.0f} s"
              + (f"; último ciclo gravado [{u.get('gerado') or '?'}] eleitorado {u['eleitorado_pct']:.1f}%: "
                 f"F {u['mu']:+.2f} ± {u['sd']:.2f} (w {u['w']:.2f})" if u else ""), flush=True)
    inicio = mon.ciclos
    while True:
        t0 = time.time()
        try:
            mon.mostrar(mon.ciclo())
        except Exception as e:  # rede instável: segue no próximo ciclo
            print(f"  erro no ciclo: {e!r}", flush=True)
        if args.ciclos and mon.ciclos - inicio >= args.ciclos:
            break
        time.sleep(max(1.0, args.intervalo - (time.time() - t0)))


if __name__ == "__main__":
    main()
