"""Detecta, na fala da sessao, os momentos que viram marcadores.

Entrada: lista de palavras com tempo (saida do Whisper) + lista de vereadores.
Saida: marcadores {tempo, fase, vereador}.

Parte 1 (regras): o presidente anuncia cada fala ("convido a vereadora Fulana...",
"concedo o aparte ao vereador..."). Frases fixas + casamento aproximado do nome.
Parte 2 (opcional, Ollama): so para trechos duvidosos que as regras nao pegaram.

O marcador fica no instante em que a pessoa COMECA a falar (palavra seguinte ao anuncio).
"""
import json
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from .config import DATA_DIR

TITULOS = ("doutor", "doutora", "dr", "dra", "professor", "professora", "prof")
# tolera erros do Whisper: vereador, vereadora, veriador, verador, variadores...
VER = r"v[ae][a-z]{0,4}d[oa]r(?:a|es)?"
VER_RE = re.compile(VER)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def carregar_apelidos() -> dict[str, int]:
    """data/apelidos.json: {"como a transcricao escreve": id_do_vereador}. Editavel pela equipe."""
    p = DATA_DIR / "apelidos.json"
    try:
        return {norm(k): int(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except Exception:
        return {}


# --------------------------------------------------------------------- vereadores
class Roster:
    def __init__(self, deputados: list[dict], apelidos: dict[str, int] | None = None):
        apelidos = carregar_apelidos() if apelidos is None else apelidos
        self.items = []
        for d in deputados:
            nome = norm(d.get("nome", ""))
            if not nome:
                continue
            toks = [t for t in nome.split() if t not in TITULOS]
            keys = {nome, " ".join(toks)}
            if len(toks) >= 2:
                keys.add(f"{toks[0]} {toks[-1]}")
            for a, did in apelidos.items():
                if did == d["id"]:
                    keys.add(a)
            self.items.append({"dep": d, "keys": keys, "toks": toks, "ativo": d.get("ativo", True)})

    def match(self, toks: list[str]):
        """toks: palavras normalizadas logo apos 'vereador(a)'. Retorna (deputado, n_palavras_do_nome)."""
        dep, n, _ = self.match_score(toks)
        return dep, n

    def match_score(self, toks: list[str]):
        """Como match(), mas devolve tambem a pontuacao (0-100) para comparar candidatos."""
        skip = 0
        while toks and (toks[0] in TITULOS or toks[0] in ("o", "a", "os", "as", "do", "da")):
            toks, skip = toks[1:], skip + 1
        best, best_n, best_score = None, 0, 0
        for n in (4, 3, 2, 1):
            if len(toks) < n:
                continue
            gram = " ".join(toks[:n])
            junto = "".join(toks[:n])  # o Whisper cola nomes: "marianosilva" = "Mariano Silva"
            for it in self.items:
                sc = max(fuzz.ratio(gram, k) for k in it["keys"]) if n > 1 else 0
                if len(junto) >= 7:
                    sc = max(sc, max(fuzz.ratio(junto, k.replace(" ", "")) for k in it["keys"] if " " in k) - 3, 0) \
                        if any(" " in k for k in it["keys"]) else sc
                sc -= 0 if it["ativo"] else 3
                if sc > best_score:
                    best, best_n, best_score = it["dep"], n, sc
        if best and best_score >= 80:
            return best, best_n + skip, best_score
        # sobrenome parecido + primeiro nome vagamente parecido (ex.: "Joan Costa" ~ "João Costa")
        if len(toks) >= 2:
            c = [it for it in self.items if len(it["toks"]) >= 2
                 and fuzz.ratio(toks[1], it["toks"][-1]) >= 88 and fuzz.ratio(toks[0], it["toks"][0]) >= 45]
            if len(c) == 1:
                return c[0]["dep"], 2 + skip, 78
        # so o primeiro nome (ex.: "vereador Paulo") - precisa ser inequivoco
        if toks:
            c = [it for it in self.items if it["toks"] and fuzz.ratio(toks[0], it["toks"][0]) >= 88]
            if len(c) == 1:
                return c[0]["dep"], 1 + skip, 70
        return None, 0, 0


# --------------------------------------------------------------------- texto com tempo
@dataclass
class Doc:
    toks: list[str]
    start: list[float]
    end: list[float]
    text: str
    off: list[int]

    @classmethod
    def build(cls, words: list[dict]):
        toks, st, en = [], [], []
        for w in words:
            for part in norm(w["w"]).split():
                toks.append(part)
                st.append(w["s"])
                en.append(w["e"])
        off, pos = [], 0
        for t in toks:
            off.append(pos)
            pos += len(t) + 1
        return cls(toks, st, en, " ".join(toks), off)

    def idx_at(self, char_pos: int) -> int:
        lo, hi = 0, len(self.off) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.off[mid] <= char_pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def excerpt(self, i: int, before=6, after=14) -> str:
        return " ".join(self.toks[max(0, i - before): i + after])

    def comeca_a_falar(self, i: int) -> float:
        """Instante da palavra seguinte ao anuncio (quando a pessoa chamada comeca)."""
        return self.start[min(i + 1, len(self.start) - 1)]


def _name_after(doc: Doc, roster: Roster, start_idx: int, window: int = 12):
    """Primeiro 'vereador X' nas proximas `window` palavras. Se o nome nao casar, desiste (nao pula para o proximo)."""
    for j in range(start_idx, min(len(doc.toks) - 1, start_idx + window)):
        if VER_RE.fullmatch(doc.toks[j]):
            dep, n = roster.match(doc.toks[j + 1: j + 6])
            if dep:
                return dep, min(len(doc.toks) - 1, j + n)
            return None, None
    return None, None


def _name_before(doc: Doc, roster: Roster, end_idx: int, window: int = 12):
    for j in range(end_idx, max(-1, end_idx - window), -1):
        if VER_RE.fullmatch(doc.toks[j]):
            dep, _ = roster.match(doc.toks[j + 1: j + 6])
            return dep
    return None


def _name_before_cue(doc: Doc, roster: Roster, cue_idx: int, window: int = 14):
    """Nome logo antes de 'para fazer uso da...': aceita 'vereador X', 'professor X' ou so 'convido o X'."""
    achados = []
    for j in range(cue_idx - 1, max(-1, cue_idx - window), -1):
        if doc.toks[j] in ("para", "fazer", "uso", "os", "pro", "pra"):
            continue
        dep, n, sc = roster.match_score(doc.toks[j: j + 5])
        if dep:
            achados.append((sc, j, dep))  # melhor pontuacao; entre iguais, o mais proximo do cue
    if not achados:
        return None
    seguros = [a for a in achados if a[0] >= 85]  # nome claro: vale o mais proximo do cue
    return max(seguros or achados, key=lambda x: (x[1] if seguros else x[0], x[1]))[2]


# --------------------------------------------------------------------- regras
def detect(words: list[dict], deputados: list[dict], fases: list[dict], apelidos: dict[str, int] | None = None,
           incluir_ordem_do_dia: bool = False, retornos: bool = True, em_discussao: bool = True) -> list[dict]:
    doc = Doc.build(words)
    if not doc.toks:
        return []
    roster = Roster(deputados, apelidos)
    F = {norm(f["titulo"]): f for f in fases}
    out: list[dict] = []
    text = doc.text

    def add(titulo, idx, dep, t, origem="regra"):
        f = F.get(norm(titulo))
        if f:
            out.append({
                "tempo_s": round(float(t), 1), "fase_id": f["id"], "fase": f["titulo"],
                "deputado_id": dep["id"] if dep else None, "deputado": dep["nome"].strip() if dep else None,
                "origem": origem, "trecho": doc.excerpt(idx), "contexto": doc.excerpt(idx, 34, 6),
            })

    # --- Abertura: o marcador fica no comeco da fala de abertura ("Sob a protecao de Deus...")
    # tolera erros do Whisper ("declara Berta a presente sessao") e cai para a frase de abertura
    m = re.search(r"declar\w+ \w+ (?:a )?(?:presente )?sess\w+|sob a protecao de deus|em nome do povo", text)
    if m:
        i = doc.idx_at(m.start())
        if doc.start[i] < 120:
            add("Abertura", i, None, doc.start[0])

    # --- Leituras anunciadas (so a primeira ocorrencia de cada uma)
    verbo = r"(?:pass\w+|convid\w+|vamos|iniciar\w*|palavra)"
    simples = [
        ("Mensagem Bíblica", r"leitura d[ae] (?:uma )?(?:mensagem|palavra|passagem|texto) b[ií]blic\w+", "antes"),
        ("Leitura da ata", verbo + r"(?: \w+){0,9} leitura d[ao] at+a", "depois"),
        ("Leitura de expediente", verbo + r"(?: \w+){0,9} leitura d[oe] expediente", "depois"),
    ]
    for titulo, rx, onde in simples:
        m = re.search(rx, text)
        if not m or "dispens" in text[max(0, m.start() - 30): m.end()]:
            continue
        fim = doc.idx_at(max(m.end() - 1, 0))
        dep, ate = None, fim
        if onde == "depois":
            dep, idx_dep = _name_after(doc, roster, m.start() and doc.idx_at(m.start()), fim - doc.idx_at(m.start()) + 12)
            ate = max(idx_dep or fim, fim)
        else:
            dep = _name_before(doc, roster, fim, 12)
            if not dep:
                dep, idx_dep = _name_after(doc, roster, fim + 1, 8)
                ate = idx_dep or fim
        add(titulo, ate, dep, doc.comeca_a_falar(ate))

    # --- Ordem do dia
    ordem_idx = None
    m = re.search(r"(?:pass\w+|inici\w+|vamos)(?: \w+){0,4} ordem do dia", text)
    if m:
        ordem_idx = doc.idx_at(m.start())
        if incluir_ordem_do_dia:
            add("Ordem do dia", ordem_idx, None, doc.start[ordem_idx])
    if ordem_idx is None:  # o Whisper pode errar a frase de transicao; usa a 1a mencao depois dos 10 min
        for mo in re.finditer(r"ordem do dia", text):
            k = doc.idx_at(mo.start())
            if doc.start[k] > 600:
                ordem_idx = k
                break
    limite = ordem_idx if ordem_idx is not None else len(doc.toks)

    # --- Uso da tribuna: "convido o vereador X para fazer uso da tribuna/palavra/tempo regimental"
    inicio_fala = {"presidente", "bom", "obrigado", "obrigada", "senhor", "senhora", "excelentissimo",
                   "excelentissima", "gostaria", "quero", "antes"}
    tribuna_t: list[float] = []
    # (o Whisper escreve "uso" como "os"/"o": "para fazer os da tribuna")
    for m in re.finditer(r"(?:(?:uso |os |o )?d[ao]s? |usar (?:a )?|ocupar (?:a )?)a?(?:tribuna|palavra)|uso no tempo \w+|tempo reg\w+", text):
        i0, i1 = doc.idx_at(m.start()), doc.idx_at(max(m.end() - 1, 0))
        if i1 >= limite or not {"para", "fazer", "convido", "convidou", "chamo", "pro", "pra"}.intersection(doc.toks[max(0, i0 - 4): i0 + 1]):
            continue
        if doc.toks[i1 + 1: i1 + 2] and doc.toks[i1 + 1] in ("pelos", "pelas", "dos", "das", "pelo"):
            continue  # anuncio da fase ("uso da palavra pelos senhores vereadores")
        dep = _name_before_cue(doc, roster, i0)
        if not dep:
            continue
        t = doc.comeca_a_falar(i1)
        for k in range(i1 + 1, min(len(doc.toks), i1 + 11)):
            if doc.toks[k] in inicio_fala:
                t = doc.start[k]
                break
        tribuna_t.append(t)
        add("Uso da tribuna", i1, dep, t)

    # --- "passo a palavra ao vereador X" / "com a palavra o vereador X": depois de uma tribuna = Aparte
    for m in re.finditer(r"(?:pass\w+(?: \w+){0,3} palavra|com a palavra|tem a palavra|concedo a palavra)(?: \w+){0,4} " + VER + r" ", text):
        i = doc.idx_at(m.end() - 1)
        if i >= limite:
            continue
        dep, last = _name_after(doc, roster, i, 1)
        if dep and "leitura" in doc.toks[last + 1: last + 8]:
            continue  # "passo a palavra ao secretario ... para a leitura da ata"
        if dep:
            t = doc.comeca_a_falar(last)
            if any(x < t for x in tribuna_t):
                add("Aparte", last, dep, t, origem="regra?")
            else:
                add("Uso da tribuna", last, dep, t, origem="regra?")
                tribuna_t.append(t)

    # --- Aparte ("concedeu a parte ao vereador X", "passa a parte do professor X"; o Whisper escreve 'parte' com frequencia)
    for m in re.finditer(r"\b(?:aparte|a parte|uma parte|um aparte)\b", text):
        i = doc.idx_at(m.end() - 1)
        if i + 1 >= limite:
            continue
        if any(w.startswith("obrigad") for w in doc.toks[max(0, i - 3): i]):
            continue  # "obrigado pelo aparte, vereador X" e agradecimento, nao concessao
        dep = last = None
        for k in range(i + 1, min(i + 8, len(doc.toks) - 1)):
            dep, last = _nome_forte(doc, roster, k, _parece_vereador(doc.toks[k - 1]) or doc.toks[k - 1] in TITULOS)
            if dep:
                break
        if dep:
            add("Aparte", last, dep, doc.comeca_a_falar(last))

    out.sort(key=lambda x: x["tempo_s"])
    out = _dedup(out)

    if retornos:
        _retornos_a_tribuna(doc, roster, out, add)
    if em_discussao:
        inicio = ordem_idx
        if inicio is None:  # sem a frase de transicao: comeca 30 s depois do ultimo orador/aparte
            fim_tribuna = max((x["tempo_s"] for x in out if x["fase"] in ("Uso da tribuna", "Aparte")), default=600.0)
            inicio = next((k for k, t in enumerate(doc.start) if t >= fim_tribuna + 30), None)
        if inicio is not None:
            _em_discussao(doc, roster, inicio, out, add)
    out.sort(key=lambda x: x["tempo_s"])
    return out


def _retornos_a_tribuna(doc: Doc, roster: Roster, out: list[dict], add):
    """Depois de um Aparte, quem estava na tribuna volta a falar quando agradece ao autor do aparte
    ("Obrigado, vereador Fulano. Lembrando que..."). Marca esse retorno como Uso da tribuna."""
    base = sorted(out, key=lambda x: x["tempo_s"])
    for a_idx, a in enumerate(base):
        if a["fase"] != "Aparte" or not a["deputado_id"]:
            continue
        orador = next((x for x in reversed(base[:a_idx]) if x["fase"] == "Uso da tribuna" and x["deputado_id"]), None)
        if not orador:
            continue
        proximo = next((x["tempo_s"] for x in base[a_idx + 1:] if x["fase"] in ("Uso da tribuna", "Aparte")), a["tempo_s"] + 900)
        for k in range(len(doc.toks)):
            t = doc.start[k]
            if t < a["tempo_s"] + 20:
                continue
            if t > min(a["tempo_s"] + 900, proximo + 5):
                break
            if not doc.toks[k].startswith("obrigad"):
                continue
            dep, last = _name_after(doc, roster, k + 1, 6)
            if not dep or dep["id"] != a["deputado_id"]:
                continue
            # se logo em seguida ja concede outro aparte, o orador nao chegou a retomar
            if any(w in ("parte", "aparte") for w in doc.toks[last + 1: last + 14]):
                break
            add("Uso da tribuna", last, {"id": orador["deputado_id"], "nome": orador["deputado"]},
                doc.comeca_a_falar(last), origem="retorno")
            break


def _parece_vereador(tok: str) -> bool:
    """'vereador' escrito de qualquer jeito pelo Whisper (variadora, alveiadora, veiador...) ou palavra de ligacao."""
    return bool(VER_RE.fullmatch(tok)) or tok.endswith(("dor", "dora", "dores")) or tok in ("o", "a", "de", "do", "da", "unica")


def _nome_forte(doc: Doc, roster: Roster, k: int, anterior_ok: bool):
    """Nome de vereador comecando na palavra k. Nome completo/colado (>=80) vale sozinho; so o primeiro nome
    (70) exige que a palavra anterior seja 'vereador' (ou parecida)."""
    dep, n, sc = roster.match_score(doc.toks[k: k + 5])
    if dep and (sc >= 80 or (sc >= 70 and anterior_ok)):
        return dep, min(len(doc.toks) - 1, k + n - 1)
    return None, None


def _em_discussao(doc: Doc, roster: Roster, ordem_idx: int, out: list[dict], add):
    """Na Ordem do dia cada vereador que fala "em discussao" vira um marcador. A presidente costuma dizer o nome
    logo antes ou logo depois ("em discussao, vereador X" / "Vamos para o vereador X... em discussao, senhor
    presidente"); quando o Whisper atrapalha o nome, o marcador sai SEM vereador, para voce escolher."""
    cands: list[tuple[float, int, dict | None]] = []
    n_tok = len(doc.toks)
    pedido = ("senhor", "senhora", "sr", "sra", "seu", "presidente", "presidenta", "excelencia")
    for i in range(max(ordem_idx, 2), n_tok - 2):
        if not doc.toks[i].startswith("discuss") or not {"em", "e", "a"}.intersection(doc.toks[i - 2: i]):
            continue
        # 1) nome logo DEPOIS: "em discussao, vereador X" / "e a discussao de Diego" / "em unica discussao, o vereador X"
        achou = None
        for k in range(i + 1, min(i + 6, n_tok - 1)):
            dep, last = _nome_forte(doc, roster, k, _parece_vereador(doc.toks[k - 1]) and k > i + 1)
            if dep:
                achou = (dep, last)
                break
            if doc.toks[k] in pedido:
                break
        if achou:
            cands.append((doc.comeca_a_falar(achou[1]), achou[1], achou[0]))
            continue
        # 2) pedido da palavra ("em discussao, senhor presidente"): o nome costuma ter sido dito logo ANTES
        if doc.toks[i + 1] in pedido:
            fim = min(n_tok - 1, i + 2)
            dep = None
            for k in range(i - 1, max(ordem_idx, i - 14), -1):
                if doc.toks[k].startswith("discuss"):
                    break
                dep, _ = _nome_forte(doc, roster, k, k > 0 and _parece_vereador(doc.toks[k - 1]))
                if dep:
                    break
            cands.append((doc.comeca_a_falar(fim), fim, dep))
    # 3) quem comeca a falar costuma abrir com "Obrigado, senhor presidente" (o encerramento diz "MUITO obrigado"):
    #    o audio nao diz o nome, mas diz QUANDO a pessoa comecou -> marcador sem vereador para voce escolher
    for i in range(max(ordem_idx, 1), n_tok - 3):
        if doc.toks[i].startswith("obrigad") and doc.toks[i - 1] != "muito":
            for k in range(i + 1, min(i + 4, n_tok - 1)):
                if doc.toks[k] in ("presidente", "presidenta"):
                    cands.append((doc.comeca_a_falar(k), k, None))
                    break
    ultimo = -999.0
    for t, idx, dep in sorted(cands, key=lambda c: c[0]):
        if t - ultimo < 30:          # "em discussao, em discussao, senhor presidente..." = um pedido so
            if dep and out and out[-1].get("fase") == "Em Discussão" and out[-1]["deputado_id"] is None:
                out.pop()            # prefere a versao com nome
            else:
                continue
        add("Em Discussão", idx, dep, t, origem="regra" if dep else "revisar")
        ultimo = t


def _dedup(items: list[dict], janela: float = 20.0) -> list[dict]:
    res: list[dict] = []
    for it in items:
        dup = next((r for r in res if r["fase_id"] == it["fase_id"] and r["deputado_id"] == it["deputado_id"]
                    and abs(r["tempo_s"] - it["tempo_s"]) < janela), None)
        if not dup:
            res.append(it)
    return res
