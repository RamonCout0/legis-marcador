"""Transcricao com tempo por palavra (faster-whisper).

Funciona em qualquer PC: usa a placa NVIDIA se conseguir, senao cai para CPU.
"""
import json
import os
from pathlib import Path

from .config import TRANSCRIPTS_DIR, WHISPER_MODEL


def _cuda_ok() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _add_nvidia_dll_dirs():
    """No Windows, bibliotecas CUDA instaladas por pip (nvidia-*) precisam estar no PATH das DLLs."""
    if os.name != "nt":
        return
    try:
        import nvidia  # type: ignore
        for base in nvidia.__path__:
            for sub in Path(base).glob("*/bin"):
                os.add_dll_directory(str(sub))
                os.environ["PATH"] = str(sub) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def _load_model(name: str, device: str):
    from faster_whisper import WhisperModel
    if device == "cuda":
        return WhisperModel(name, device="cuda", compute_type="int8_float16")
    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)


def cache_path(video_id: int) -> Path:
    return TRANSCRIPTS_DIR / f"{video_id}.json"


def load_cached(video_id: int):
    p = cache_path(video_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def transcribe(video_id: int, media: Path, progress=None, model_name: str | None = None) -> dict:
    """Retorna {"words": [{"w","s","e"}], "device", "model", "duration"} e guarda em cache."""
    cached = load_cached(video_id)
    if cached:
        return cached

    _add_nvidia_dll_dirs()
    device = "cuda" if _cuda_ok() else "cpu"
    name = model_name or WHISPER_MODEL
    if name == "auto":
        name = "medium" if device == "cuda" else "small"

    try:
        model = _load_model(name, device)
        segments, info = model.transcribe(
            str(media), language="pt", beam_size=1 if device == "cpu" else 5,
            vad_filter=True, word_timestamps=True, condition_on_previous_text=False,
        )
        words = _collect(segments, info.duration, progress)
    except Exception as e:  # falha de CUDA/cuDNN -> tenta de novo no processador
        if device != "cuda":
            raise
        device = "cpu"
        name = model_name or ("small" if WHISPER_MODEL == "auto" else WHISPER_MODEL)
        model = _load_model(name, device)
        segments, info = model.transcribe(
            str(media), language="pt", beam_size=1, vad_filter=True,
            word_timestamps=True, condition_on_previous_text=False,
        )
        words = _collect(segments, info.duration, progress)

    out = {"words": words, "device": device, "model": name, "duration": info.duration}
    cache_path(video_id).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _collect(segments, duration, progress):
    words = []
    for seg in segments:
        for w in (seg.words or []):
            t = w.word.strip()
            if t:
                words.append({"w": t, "s": round(w.start, 2), "e": round(w.end, 2)})
        if progress and duration:
            progress(min(1.0, seg.end / duration))
    return words
