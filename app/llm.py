"""Segunda passada (opcional) com um modelo pequeno do Ollama.

So olha trechos que parecem "alguem deu a palavra a um vereador" e que as regras
nao pegaram. A resposta do modelo e SEMPRE validada contra a lista oficial de
fases e de vereadores: o modelo nunca inventa nome nem categoria.
"""
import json
import re

import requests

from .config import OLLAMA_MODEL, OLLAMA_URL
from .detector import VER, Doc, Roster, norm

FASES_LLM = ["Uso da tribuna", "Aparte", "Tribuna Livre", "Questão de Ordem"]

CUE = re.compile(r"(?:palavra|aparte|parte|tribuna|convido|concedo|concedeu)(?: \w+){0,8} " + VER + r" ")


def disponivel() -> bool:
    try:
        return requests.get(OLLAMA_URL + "/api/tags", timeout=3).ok
    except Exception:
        return False


def _perguntar(trecho: str) -> dict | None:
    prompt = (
        "Trecho de uma sessao de camara municipal (transcricao automatica, com erros). "
        "Diga se, neste trecho, o presidente ou um vereador DA A PALAVRA a um vereador "
        "(e em que modalidade).\n"
        f"Modalidades possiveis: {', '.join(FASES_LLM)}.\n"
        'Responda so JSON: {"fase": "<modalidade ou null>", "vereador": "<nome como aparece no trecho ou null>"}\n\n'
        f"Trecho: {trecho}"
    )
    try:
        r = requests.post(
            OLLAMA_URL + "/api/chat",
            json={"model": OLLAMA_MODEL, "stream": False, "format": "json",
                  "options": {"temperature": 0}, "messages": [{"role": "user", "content": prompt}]},
            timeout=90,
        )
        return json.loads(r.json()["message"]["content"])
    except Exception:
        return None


def refinar(words: list[dict], deputados: list[dict], fases: list[dict], achados: list[dict], limite: int = 40) -> list[dict]:
    if not disponivel():
        return []
    doc = Doc.build(words)
    roster = Roster(deputados)
    F = {norm(f["titulo"]): f for f in fases}
    ja = [a["tempo_s"] for a in achados]
    novos: list[dict] = []
    for m in CUE.finditer(doc.text):
        if len(novos) >= limite:
            break
        i = doc.idx_at(m.end() - 1)
        t = doc.end[i]
        if any(abs(t - x) < 25 for x in ja + [n["tempo_s"] for n in novos]):
            continue
        trecho = " ".join(doc.toks[max(0, i - 12): i + 10])
        res = _perguntar(trecho)
        if not res or not res.get("fase") or not res.get("vereador"):
            continue
        fase = F.get(norm(str(res["fase"])))
        dep, n = roster.match(norm(str(res["vereador"])).split())
        if not fase or not dep or norm(fase["titulo"]) not in {norm(x) for x in FASES_LLM}:
            continue
        novos.append({
            "tempo_s": round(float(doc.end[min(len(doc.toks) - 1, i + n)]), 1), "fase_id": fase["id"],
            "fase": fase["titulo"], "deputado_id": dep["id"], "deputado": dep["nome"].strip(),
            "origem": "ia", "trecho": " ".join(doc.toks[max(0, i - 6): i + 14]),
        })
    return novos


def resolver_nomes(achados: list[dict], deputados: list[dict], limite: int = 40) -> int:
    """Para marcadores SEM vereador (Em Discussao, Aparte, Tribuna), pergunta ao modelo local quem foi chamado,
    olhando o trecho dito logo antes. A resposta so vale se for um nome EXATO da lista oficial; o marcador
    fica com origem "ia" (laranja na tela) para voce conferir. Retorna quantos nomes foram preenchidos."""
    if not disponivel():
        return 0
    ativos = [d for d in deputados if d.get("ativo", True)]
    por_nome = {norm(d["nome"]): d for d in ativos}
    lista = "; ".join(d["nome"].strip() for d in ativos)
    preenchidos = 0
    for a in achados:
        if preenchidos >= limite:
            break
        if a.get("deputado_id") or a["fase"] not in ("Em Discussão", "Aparte", "Uso da tribuna") or not a.get("contexto"):
            continue
        prompt = (
            "Trecho de uma sessão de câmara municipal, transcrito automaticamente (os NOMES saem com erros de grafia, "
            "ex.: 'Mara Cabales' = 'Marina Cavalcanti'). No fim do trecho, um vereador começa a falar. "
            "A presidente costuma chamá-lo pelo nome pouco antes. Quem é?\n"
            f"Vereadores possíveis: {lista}.\n"
            'Responda só JSON: {"vereador": "<nome EXATO da lista, ou null se o trecho não deixar claro>"}\n\n'
            f"Trecho: {a['contexto']}"
        )
        try:
            r = requests.post(OLLAMA_URL + "/api/chat",
                              json={"model": OLLAMA_MODEL, "stream": False, "format": "json", "options": {"temperature": 0},
                                    "messages": [{"role": "user", "content": prompt}]}, timeout=120)
            nome = json.loads(r.json()["message"]["content"]).get("vereador")
        except Exception:
            continue
        dep = por_nome.get(norm(str(nome))) if nome else None
        if dep:
            a["deputado_id"], a["deputado"], a["origem"] = dep["id"], dep["nome"].strip(), "ia"
            preenchidos += 1
    return preenchidos
