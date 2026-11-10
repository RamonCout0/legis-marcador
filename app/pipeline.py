"""Orquestra: baixar video -> transcrever -> detectar marcadores."""
import json
import threading
import time
import traceback

import requests

from . import detector, llm, transcribe
from .config import DATA_DIR, VIDEOS_DIR
from .legis_api import LegisAPI, LegisError, tempo_str

CACHE_REF = DATA_DIR / "cache_referencias.json"


class Job:
    def __init__(self, video_id: int):
        self.video_id = video_id
        self.stage = "fila"
        self.progress = 0.0
        self.error: str | None = None
        self.markers: list[dict] | None = None
        self.info: dict = {}

    def to_dict(self):
        return {"video_id": self.video_id, "stage": self.stage, "progress": round(self.progress, 3),
                "error": self.error, "markers": self.markers, "info": self.info}


JOBS: dict[int, Job] = {}
_lock = threading.Lock()


def _referencias(api: LegisAPI, job: Job) -> tuple[list[dict], list[dict]]:
    """Vereadores e fases. Busca no Legis Videos (com novas tentativas); se a rede falhar, usa a ultima copia salva."""
    ultimo = None
    for tentativa in range(4):
        try:
            deps, fases = api.deputados(), api.fases()
            CACHE_REF.write_text(json.dumps({"deputados": deps, "fases": fases}, ensure_ascii=False), encoding="utf-8")
            return deps, fases
        except (requests.RequestException, LegisError) as e:
            ultimo = e
            time.sleep(2 * (tentativa + 1))
    if CACHE_REF.exists():
        c = json.loads(CACHE_REF.read_text(encoding="utf-8"))
        job.info["aviso"] = "Sem conexão com o Legis Vídeos agora; usei a última lista de vereadores salva."
        return c["deputados"], c["fases"]
    raise ultimo


def _mensagem_amigavel(e: Exception, transcricao_pronta: bool) -> str:
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        resto = ("O vídeo e a transcrição já ficaram guardados, então ao tentar de novo é bem mais rápido."
                 if transcricao_pronta else "O que já foi baixado fica guardado e é retomado.")
        return ("Perdi a conexão com o Legis Vídeos (pode ser a internet, o antivírus ou uma VPN). "
                f"{resto} Clique em Voltar e depois em Marcar para tentar de novo.")
    return f"{type(e).__name__}: {e}"


def _executar(api: LegisAPI, video: dict, job: Job, usar_ia: bool):
    """Corpo do trabalho (um video de cada vez: transcrever em paralelo so deixa tudo mais lento)."""
    with _lock:
        pronta = False
        try:
            # primeiro o que e rapido e pode falhar (rede), para nao descobrir isso so depois de ~1 h de transcricao
            deps, fases = _referencias(api, job)
            job.stage, job.progress = "baixando video", 0.0
            media = api.baixar_video(video["hash"], VIDEOS_DIR / f"{video['id']}.mp4",
                                     progress=lambda p: setattr(job, "progress", p))
            job.stage, job.progress = "transcrevendo (pode demorar)", 0.0
            tr = transcribe.transcribe(video["id"], media, progress=lambda p: setattr(job, "progress", p))
            pronta = True
            job.info.update({"dispositivo": tr["device"], "modelo": tr["model"]})
            job.stage, job.progress = "identificando falas", 1.0
            found = detector.detect(tr["words"], deps, fases)
            if usar_ia:
                extra = llm.refinar(tr["words"], deps, fases, found)
                found = sorted(found + extra, key=lambda x: x["tempo_s"])
                job.info["nomes_ia"] = llm.resolver_nomes(found, deps)
            for m in found:
                m["tempo"] = tempo_str(m["tempo_s"])
            job.markers = found
            job.stage = "pronto"
        except Exception as e:
            job.error = _mensagem_amigavel(e, pronta)
            job.stage = "erro"
            traceback.print_exc()


def _reaproveitavel(video_id: int) -> Job | None:
    """Ja existe um trabalho em andamento ou pronto para este video? Reaproveita em vez de refazer."""
    j = JOBS.get(video_id)
    return j if j and j.stage != "erro" else None


def processar(api: LegisAPI, video: dict, usar_ia: bool = True) -> Job:
    ja = _reaproveitavel(video["id"])
    if ja:
        return ja
    job = Job(video["id"])
    JOBS[video["id"]] = job
    threading.Thread(target=_executar, args=(api, video, job, usar_ia), daemon=True).start()
    return job


def preparar_varios(api: LegisAPI, videos: list[dict], usar_ia: bool = True) -> list[int]:
    """Poe varias sessoes na fila; uma thread so as processa, na ordem pedida (para voce conferir as prontas enquanto isso)."""
    novos = []
    for v in videos:
        if not _reaproveitavel(v["id"]):
            j = Job(v["id"])
            j.stage = "na fila"
            JOBS[v["id"]] = j
            novos.append((v, j))

    def fila():
        for v, j in novos:
            if JOBS.get(v["id"]) is j:
                _executar(api, v, j, usar_ia)

    if novos:
        threading.Thread(target=fila, daemon=True).start()
    return [v["id"] for v, _ in novos]
