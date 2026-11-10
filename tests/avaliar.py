"""Teste de precisao: roda o detector num video que JA tem marcadores feitos pela equipe
e compara. Uso (a partir da pasta do projeto):

    .venv\\Scripts\\python.exe tests\\avaliar.py 441            # baixa, transcreve e compara
    .venv\\Scripts\\python.exe tests\\avaliar.py 441 --sem-ia   # so regras
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app import detector, llm, transcribe  # noqa: E402
from app.config import DATA_DIR, VIDEOS_DIR  # noqa: E402
from app.legis_api import LegisAPI, tempo_seg, tempo_str  # noqa: E402

TOL = 45  # segundos: a equipe marca "a olho", com folga de ate ~40 s em relacao a fala


def main():
    vid = int(sys.argv[1])
    usar_ia = "--sem-ia" not in sys.argv
    ref_arq = Path(sys.argv[sys.argv.index("--ref") + 1]) if "--ref" in sys.argv else DATA_DIR / "fixtures" / "ref.json"
    ref = json.loads(ref_arq.read_text(encoding="utf-8"))
    extra = DATA_DIR / "fixtures" / "gt_extra.json"
    if extra.exists():
        ref["gt"].update(json.loads(extra.read_text(encoding="utf-8")))
    gt = ref["gt"][str(vid)]

    api = LegisAPI()
    media = api.baixar_video(gt["hash"], VIDEOS_DIR / f"{vid}.mp4",
                             progress=lambda p: print(f"\rbaixando {p:4.0%}", end="", flush=True))
    print()
    tr = transcribe.transcribe(vid, media, progress=lambda p: print(f"\rtranscrevendo {p:4.0%}", end="", flush=True))
    print(f"\n{len(tr['words'])} palavras | {tr['device']} | modelo {tr['model']}")

    found = detector.detect(tr["words"], ref["deputados"], ref["fases"])
    if usar_ia:
        found = sorted(found + llm.refinar(tr["words"], ref["deputados"], ref["fases"], found), key=lambda x: x["tempo_s"])
        n_ia = llm.resolver_nomes(found, ref["deputados"])
        print(f"IA preencheu {n_ia} nomes")

    print("\n--- ENCONTRADOS ---")
    for f in found:
        print(f"{tempo_str(f['tempo_s'])}  {f['fase']:<22} {f['deputado'] or '-':<20} [{f['origem']}]  ...{f['trecho'][:70]}")

    print("\n--- COMPARACAO COM A EQUIPE ---")
    ok = 0
    usados = set()
    for g in gt["marcadores"]:
        gs = tempo_seg(g["tempo"])
        cand = [(abs(f["tempo_s"] - gs), i, f) for i, f in enumerate(found)
                if i not in usados and f["fase"] == g["fase"]]
        cand.sort(key=lambda x: x[0])
        if cand:
            d, i, f = cand[0]
            usados.add(i)
            dep_ok = (f["deputado"] or "") == (g["deputado"] or "") or not g["deputado"]
            cert = d <= TOL and dep_ok
            ok += cert
            print(f"{'OK ' if cert else '~  '} {g['tempo']} {g['fase']:<22} {g['deputado'] or '-':<18} -> {tempo_str(f['tempo_s'])} "
                  f"(dif {f['tempo_s'] - gs:+.0f}s) {f['deputado'] or '-'}")
        else:
            print(f"-- {g['tempo']} {g['fase']:<22} {g['deputado'] or '-':<18} -> NAO ENCONTRADO")
    extras = [f for i, f in enumerate(found) if i not in usados]
    print(f"\nacertos: {ok}/{len(gt['marcadores'])} | marcadores a mais (revisar): {len(extras)}")
    cob = sum(any(abs(f["tempo_s"] - tempo_seg(g["tempo"])) <= TOL for f in found) for g in gt["marcadores"])
    resto = [g for g in gt["marcadores"] if g["fase"] != "Abertura"]
    certos = sum(any(abs(f["tempo_s"] - tempo_seg(g["tempo"])) <= TOL and f["fase"] == g["fase"]
                     and (f["deputado"] or "") == (g["deputado"] or "") for f in found) for g in resto)
    print(f"momento encontrado (qualquer fase, +-{TOL}s): {cob}/{len(gt['marcadores'])} | "
          f"fase+vereador+tempo certos (sem a Abertura): {certos}/{len(resto)}")
    for f in extras:
        print(f"   + {tempo_str(f['tempo_s'])} {f['fase']} {f['deputado'] or '-'}")


if __name__ == "__main__":
    main()
