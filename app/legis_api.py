"""Cliente da API do Legis Videos.

Obs.: de proposito NAO existe aqui nenhuma funcao para publicar marcadores
(marcador/publicar). A publicacao continua sendo feita por uma pessoa, na
tela do Legis Videos.
"""
from pathlib import Path

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import API_BASE


def _base() -> str:
    if not API_BASE:
        raise LegisError("Falta configurar o endereco do Legis Videos: copie .env.exemplo para .env e preencha (veja o README).")
    return API_BASE


def _nova_sessao() -> requests.Session:
    """Sessao que tenta de novo sozinha quando a conexao cai (antivirus, VPN, Wi-Fi) ou o servidor engasga."""
    # POST/PUT nao repetem em erro 5xx (evita criar marcador duplicado); falha de conexao e sempre repetida
    retry = Retry(total=5, connect=5, read=3, backoff_factor=1.5, status_forcelist=(502, 503, 504),
                  allowed_methods=frozenset({"GET", "HEAD", "DELETE"}), raise_on_status=False)
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


class LegisError(Exception):
    pass


def tempo_str(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def tempo_seg(t: str) -> int:
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


class LegisAPI:
    def __init__(self, token: str | None = None):
        self.token = token
        self.s = _nova_sessao()

    # -------- autenticacao
    def login(self, cpf: str, senha: str) -> str:
        # O site mostra o CPF com mascara (000.000.000-00). Tenta como digitado e, se o usuario
        # "nao existir", tenta o outro formato (so numeros <-> com pontos e traco).
        digitos = "".join(c for c in cpf if c.isdigit())
        mascarado = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}" if len(digitos) == 11 else digitos
        tentativas = [cpf.strip()] + [x for x in (digitos, mascarado) if x and x != cpf.strip()]
        msg = "Login recusado"
        for login in tentativas:
            try:
                r = self.s.post(_base() + "seguranca/autenticar", json={"login": login, "senha": senha}, timeout=30)
                data = r.json() if r.content else {}
            except Exception as e:
                raise LegisError(f"Nao consegui falar com o Legis Videos: {e}")
            token = data.get("token")
            if token:
                self.token = token
                return token
            msg = data.get("message") or msg
            if "existe" not in msg.lower():  # usuario existe mas a senha esta errada: nao insiste
                break
        raise LegisError(msg)

    def _h(self):
        if not self.token:
            raise LegisError("Nao autenticado")
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, path: str):
        r = self.s.get(_base() + path, headers=self._h(), timeout=60)
        if r.status_code == 409:
            raise LegisError("Sessao expirada, entre novamente")
        r.raise_for_status()
        return r.json()

    # -------- leitura
    def videos(self) -> list[dict]:
        return self._get("video").get("dados", [])

    def video(self, video_id: int) -> dict:
        d = self._get(f"video/{video_id}")
        return d.get("dados", d)

    def marcadores(self, video_id: int) -> list[dict]:
        return self._get(f"marcador?video={video_id}").get("dados", [])

    def deputados(self) -> list[dict]:
        return self._get("deputado").get("dados", [])

    def fases(self) -> list[dict]:
        # No sistema as "fases" (Abertura, Aparte...) ficam no endpoint "evento"
        return self._get("evento").get("dados", [])

    # -------- escrita (somente marcadores NAO publicos)
    def criar_marcador(self, video_id: int, fase_id: int, tempo: str, fase_titulo: str,
                       deputado_id: int | None = None) -> dict:
        body = {"fase": fase_id, "tempo": tempo, "descricao": fase_titulo, "video.id": video_id}
        if deputado_id:
            body["deputado.id"] = deputado_id
        r = self.s.post(_base() + "marcador", json=body, headers=self._h(), timeout=60)
        r.raise_for_status()
        return r.json()

    def contagem(self, video_id: int) -> dict:
        """Quantos marcadores o video tem e quantos ja estao publicos (chamada independente: pode rodar em paralelo)."""
        r = self.s.get(_base() + f"marcador?video={video_id}", headers=self._h(), timeout=60)
        r.raise_for_status()
        ms = r.json().get("dados", [])
        return {"n": len(ms), "publicos": sum(1 for m in ms if m.get("publico"))}

    def excluir_marcador(self, marcador_id: int) -> None:
        r = self.s.delete(_base() + f"marcador/{marcador_id}", headers=self._h(), timeout=60)
        r.raise_for_status()

    # -------- arquivo de video (endereco publico)
    @staticmethod
    def video_url(hash_: str) -> str:
        return f"{_base()}video/show/{hash_}.mp4"

    def baixar_video(self, hash_: str, destino: Path, progress=None) -> Path:
        """Baixa o video. Se a conexao cair no meio, retoma de onde parou (ate 6 tentativas)."""
        destino = Path(destino)
        if destino.exists() and destino.stat().st_size > 0:
            return destino
        tmp = destino.with_suffix(".part")
        ultimo_erro = None
        for tentativa in range(6):
            feito = tmp.stat().st_size if tmp.exists() else 0
            try:
                cab = {"Range": f"bytes={feito}-"} if feito else {}
                with self.s.get(self.video_url(hash_), headers=cab, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    if feito and r.status_code != 206:  # servidor ignorou o pedido de retomada: recomeca
                        feito = 0
                    total = feito + int(r.headers.get("Content-Length") or 0)
                    with open(tmp, "ab" if feito else "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                            feito += len(chunk)
                            if progress and total:
                                progress(min(1.0, feito / total))
                tmp.replace(destino)
                return destino
            except requests.RequestException as e:
                ultimo_erro = e
                time.sleep(2 * (tentativa + 1))
        raise ultimo_erro
