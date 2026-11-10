"""Envio de marcadores ao Legis Videos: novo / completar / substituir.

Seguranca:
  - antes de apagar qualquer coisa, os marcadores antigos sao gravados em data/backups/;
  - no modo "substituir" os NOVOS sao criados primeiro e so depois os antigos sao apagados
    (se algo falhar no meio, voce fica com marcadores duplicados, nunca com a sessao vazia);
  - nada e publicado aqui: marcadores criados entram como nao publicos.
"""
import json
import time

from .config import DATA_DIR
from .legis_api import LegisAPI, tempo_seg

MODOS = ("novo", "completar", "substituir")
JANELA_S = 45  # mesma fase a menos de 45 s de distancia = mesmo marcador


def _igual(existente: dict, novo: dict) -> bool:
    return (existente["fase_id"] == novo["fase_id"]
            and abs(existente["seg"] - tempo_seg(novo["tempo"])) <= JANELA_S)


def normalizar_existentes(brutos: list[dict]) -> list[dict]:
    return [{
        "id": m["id"], "tempo": m["tempo"], "seg": tempo_seg(m["tempo"]),
        "fase_id": (m.get("fase") or {}).get("id"), "fase": (m.get("fase") or {}).get("titulo"),
        "deputado_id": (m.get("deputado") or {}).get("id"), "deputado": (m.get("deputado") or {}).get("nome"),
        "publico": bool(m.get("publico")),
    } for m in brutos]


def planejar(existentes: list[dict], novos: list[dict], modo: str) -> dict:
    if modo not in MODOS:
        raise ValueError(f"modo invalido: {modo}")
    if modo == "novo":
        if existentes:
            raise ValueError("Este video ja tem marcadores. Escolha 'completar' ou 'substituir'.")
        return {"criar": novos, "excluir": [], "pulados": 0}
    if modo == "completar":
        criar = [n for n in novos if not any(_igual(e, n) for e in existentes)]
        return {"criar": criar, "excluir": [], "pulados": len(novos) - len(criar)}
    return {"criar": novos, "excluir": [e["id"] for e in existentes], "pulados": 0}


def _backup(video_id: int, existentes: list[dict]):
    if not existentes:
        return None
    pasta = DATA_DIR / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"video{video_id}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    arq.write_text(json.dumps(existentes, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(arq)


def executar(api: LegisAPI, video_id: int, novos: list[dict], modo: str) -> dict:
    existentes = normalizar_existentes(api.marcadores(video_id))
    plano = planejar(existentes, novos, modo)
    res = {"criados": 0, "excluidos": 0, "pulados": plano["pulados"], "backup": None, "avisos": []}

    if plano["excluir"]:
        res["backup"] = _backup(video_id, existentes)
        if any(e["publico"] for e in existentes):
            res["avisos"].append("Havia marcadores publicos; os novos entram nao publicos (publique de novo no Legis Videos).")

    falhas = 0
    for n in plano["criar"]:
        try:
            api.criar_marcador(video_id, n["fase_id"], n["tempo"], n["fase"], n.get("deputado_id"))
            res["criados"] += 1
        except Exception as e:
            falhas += 1
            res["avisos"].append(f"Nao consegui criar {n['tempo']} {n['fase']}: {e}")

    if falhas:
        if plano["excluir"]:
            res["avisos"].append("Como houve falhas ao criar, NADA foi apagado. Os marcadores antigos continuam la.")
        return res

    for mid in plano["excluir"]:
        try:
            api.excluir_marcador(mid)
            res["excluidos"] += 1
        except Exception as e:
            res["avisos"].append(f"Nao consegui apagar o marcador antigo {mid}: {e}")
    return res
