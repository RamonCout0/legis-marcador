import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

BASE_DIR = Path(__file__).resolve().parent.parent


def _carregar_env():
    """Le o arquivo .env (se existir): linhas CHAVE=valor. As variaveis do sistema tem prioridade."""
    arq = BASE_DIR / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()

DATA_DIR = Path(os.getenv("LEGIS_DATA", BASE_DIR / "data"))
VIDEOS_DIR = DATA_DIR / "videos"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
for _d in (VIDEOS_DIR, TRANSCRIPTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Enderecos do SEU Legis Videos. Ficam no arquivo .env (que nao vai para o Git) - veja .env.exemplo.
API_BASE = (os.getenv("LEGIS_API") or "").strip()
API_BASE = API_BASE.rstrip("/") + "/" if API_BASE else ""
ADMIN_URL = (os.getenv("LEGIS_ADMIN_URL") or "").strip()
ADMIN_URL = ADMIN_URL.rstrip("/") + "/" if ADMIN_URL else ""

# "auto": GPU -> medium, CPU -> small. Pode forcar: tiny, base, small, medium, large-v3
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "auto")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
