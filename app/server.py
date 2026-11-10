"""Servidor web local (aberto automaticamente por `python -m app`)."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import envio, llm, pipeline
from . import config
from .config import BASE_DIR
from .legis_api import LegisAPI, LegisError

app = FastAPI(title="Legis Marcador")

# ---- seguranca do servidor local -------------------------------------------------------------
# O programa roda no SEU computador e voce fica logado no Legis Videos enquanto ele esta aberto.
# Sem estas regras, um site qualquer aberto no navegador poderia mandar pedidos para http://localhost:8765
# (CSRF) ou "enganar" o navegador para ler as respostas (DNS rebinding). Por isso:
#  - so aceita o nome de host localhost / 127.0.0.1 / [::1];
#  - pedidos que alteram algo (POST/PUT/DELETE) so valem se vierem da propria pagina do programa.
HOSTS_PERMITIDOS = {"localhost", "127.0.0.1", "[::1]", "::1"}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; media-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def seguranca(request: Request, call_next):
    host = (request.headers.get("host") or "").strip().lower()
    nome = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
    if nome not in HOSTS_PERMITIDOS:
        return PlainTextResponse("Acesso negado (host nao permitido).", status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origem = request.headers.get("origin")
        if (origem and urlparse(origem).netloc.lower() != host) or request.headers.get("sec-fetch-site") == "cross-site":
            return PlainTextResponse("Acesso negado (origem nao permitida).", status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = CSP
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

api = LegisAPI()  # sessao unica, em memoria (a senha nunca e gravada)
_cache = {"videos": []}
ESTADO = {"rodando": False, "feitos": 0, "total": 0, "itens": {}, "atualizado_em": None}
ADMIN_URL = config.ADMIN_URL + "videos/editar/" if config.ADMIN_URL else ""


class LoginIn(BaseModel):
    cpf: str
    senha: str


class MarcadorIn(BaseModel):
    tempo: str
    fase_id: int
    fase: str
    deputado_id: int | None = None


class PrepararIn(BaseModel):
    ids: list[int]
    usar_ia: bool = True


class EnviarIn(BaseModel):
    marcadores: list[MarcadorIn]
    modo: str = "novo"  # novo | completar | substituir


def _need_login():
    if not api.token:
        raise HTTPException(401, "Entre com seu CPF e senha")


@app.post("/api/login")
def login(d: LoginIn):
    try:
        api.login(d.cpf, d.senha)
    except LegisError as e:
        raise HTTPException(401, str(e))
    return {"ok": True}


@app.post("/api/sair")
def sair():
    api.token = None
    ESTADO.update(rodando=False, feitos=0, total=0, itens={}, atualizado_em=None)
    return {"ok": True}


@app.get("/api/status")
def status():
    return {"logado": bool(api.token), "ollama": llm.disponivel(), "configurado": bool(config.API_BASE)}


@app.get("/api/sessoes")
def sessoes():
    """Sessoes Ordinarias, da mais recente para a mais antiga."""
    _need_login()
    try:
        vids = [v for v in api.videos() if "ordin" in (v.get("titulo") or "").lower()]
    except LegisError as e:
        raise HTTPException(401, str(e))
    out = [{"id": v["id"], "titulo": v["titulo"], "descricao": v.get("descricao"),
            "data": (v.get("dataVideo") or "")[:10], "duracao": v.get("duracao"), "hash": v["hash"],
            "link": (ADMIN_URL + str(v["id"])) if ADMIN_URL else ""} for v in vids]
    out.sort(key=lambda x: (x["data"], x["id"]), reverse=True)
    _cache["videos"] = out
    return out


# ---- estado de cada sessao (sem marcadores / nao publicados / publicados), calculado em segundo plano
def _verificar(ids: list[int]):
    ESTADO.update(rodando=True, feitos=0, total=len(ids))

    def um(i):
        try:
            ESTADO["itens"][i] = api.contagem(i)
        except Exception:
            ESTADO["itens"].setdefault(i, {"n": None, "publicos": 0})
        ESTADO["feitos"] += 1

    try:
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(um, ids))
    finally:
        ESTADO["atualizado_em"] = time.time()
        ESTADO["rodando"] = False


@app.post("/api/estado/atualizar")
def estado_atualizar(completo: bool = False):
    """Confere de novo no Legis Videos. Por padrao so as que ainda nao estao 100% publicadas (rapido)."""
    _need_login()
    if not ESTADO["rodando"]:
        def pendente(i):
            e = ESTADO["itens"].get(i)
            return completo or not e or e["n"] is None or e["publicos"] < e["n"] or e["n"] == 0
        ids = [v["id"] for v in _cache["videos"] if pendente(v["id"])]
        threading.Thread(target=_verificar, args=(ids,), daemon=True).start()
    return {"ok": True}


@app.get("/api/estado")
def estado():
    _need_login()
    return ESTADO


@app.get("/api/sessoes/{vid}/marcadores")
def marcadores_existentes(vid: int):
    _need_login()
    return [{k: m[k] for k in ("tempo", "fase", "deputado", "publico")}
            for m in envio.normalizar_existentes(api.marcadores(vid))]


@app.get("/api/referencias")
def referencias():
    _need_login()
    return {"deputados": [{"id": d["id"], "nome": d["nome"].strip(), "ativo": d.get("ativo", True)} for d in api.deputados()],
            "fases": [{"id": f["id"], "titulo": f["titulo"]} for f in api.fases()]}


@app.post("/api/processar/{vid}")
def processar(vid: int, usar_ia: bool = True):
    _need_login()
    video = next((v for v in _cache["videos"] if v["id"] == vid), None) or api.video(vid)
    if video.get("hash") is None:
        raise HTTPException(404, "Video sem arquivo")
    return pipeline.processar(api, video, usar_ia).to_dict()


@app.post("/api/preparar")
def preparar(d: PrepararIn):
    """Poe varias sessoes na fila para serem baixadas e transcritas em segundo plano."""
    _need_login()
    mapa = {v["id"]: v for v in _cache["videos"]}
    videos = [mapa[i] for i in d.ids if i in mapa]
    return {"na_fila": pipeline.preparar_varios(api, videos, d.usar_ia)}


@app.get("/api/jobs")
def jobs():
    return {i: {"stage": j.stage, "progress": round(j.progress, 3), "error": j.error}
            for i, j in pipeline.JOBS.items()}


@app.get("/api/job/{vid}")
def job(vid: int):
    j = pipeline.JOBS.get(vid)
    if not j:
        raise HTTPException(404, "Nenhum processamento para este video")
    return j.to_dict()


@app.post("/api/sessoes/{vid}/enviar")
def enviar(vid: int, d: EnviarIn):
    """Cria os marcadores NO SISTEMA, como nao publicos. A publicacao e feita por voce, no Legis Videos."""
    _need_login()
    try:
        res = envio.executar(api, vid, [m.model_dump() for m in d.marcadores], d.modo)
    except ValueError as e:
        raise HTTPException(409, str(e))
    try:
        ESTADO["itens"][vid] = api.contagem(vid)
    except Exception:
        pass
    return res


@app.get("/api/video/{vid}")
def video_arquivo(vid: int):
    p = BASE_DIR / "data" / "videos" / f"{vid}.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


app.mount("/", StaticFiles(directory=str(Path(BASE_DIR) / "static"), html=True), name="static")
