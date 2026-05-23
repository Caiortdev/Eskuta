"""
Diarização de speakers via pyannote.audio.

Carrega o modelo `pyannote/speaker-diarization-3.1` do Hugging Face
Hub (gated — precisa aceitar termos e gerar token) e identifica
trechos de fala por speaker.

Singleton thread-safe: o modelo (~500MB) é carregado lazy na primeira
chamada e cacheado. Em testes, use `reset_pipeline_cache()` pra forçar
re-load.

Decisão de design — `HF_TOKEN` é APP-level, não user-level. Vem do
`.env` em dev e de build secret em prod. Diarização é opcional no
MVP: sem token, `is_available()` retorna False e a transcrição segue
normalmente sem rótulos de speaker (vide [`AUDIT-FASE-1.5`]).

**Workaround torchcodec:** pyannote.audio 4.x tenta usar torchcodec
pra decodificar áudio quando recebe path. Em ambientes onde o
torchcodec não tem DLLs compatíveis com o FFmpeg do sistema, isso
quebra. Nós contornamos passando `{'waveform': tensor, 'sample_rate': int}`
pré-carregado — o pyannote pula o decode. O áudio é lido via ffmpeg
(imageio_ffmpeg embutido) → numpy → torch.Tensor.

**Auto-detect GPU:** se `torch.cuda.is_available()`, joga o pipeline
na GPU (~5-10x mais rápido). Sem CUDA, fica em CPU.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Final

from loguru import logger

from app.core.settings import settings

# Suprime o warning verboso de torchcodec — usamos workaround in-memory.
warnings.filterwarnings(
    "ignore",
    message="torchcodec is not installed correctly",
    category=UserWarning,
)

PYANNOTE_MODEL: Final[str] = "pyannote/speaker-diarization-3.1"

# Sample rate que o pyannote espera (modelo é treinado em 16kHz).
PYANNOTE_SAMPLE_RATE: Final[int] = 16000

_pipeline: Any | None = None
_pipeline_lock = Lock()
_device: Any | None = None  # cache da decisão GPU/CPU


class DiarizationError(RuntimeError):
    """Erro genérico de diarização."""


class DiarizationUnavailableError(DiarizationError):
    """
    Pipeline não pode ser usado agora.

    Causas típicas: HF_TOKEN ausente, sem internet pra baixar modelo
    na primeira execução, ou termos do modelo no Hugging Face não
    aceitos pela conta do APP.
    """


@dataclass(frozen=True)
class SpeakerSegment:
    """Trecho contínuo de fala atribuído a um speaker pelo pyannote."""

    start_sec: float
    end_sec: float
    speaker_id: str  # Ex: "SPEAKER_00", "SPEAKER_01", ...

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def is_available() -> bool:
    """True se HF_TOKEN está configurado (não testa conexão de fato)."""
    return bool(settings.HF_TOKEN)


def reset_pipeline_cache() -> None:
    """Força re-load do pipeline na próxima chamada — útil pra testes."""
    global _pipeline, _device
    with _pipeline_lock:
        _pipeline = None
        _device = None


def _detect_device() -> Any:
    """
    Decide device pra rodar o pipeline: CUDA se disponível, senão CPU.
    Cacheado (logado uma vez no startup do pipeline).
    """
    global _device
    if _device is None:
        import torch

        if torch.cuda.is_available():
            _device = torch.device("cuda")
            gpu_name = torch.cuda.get_device_name(0)
            logger.info("Diarização vai usar GPU", device=str(_device), gpu=gpu_name)
        else:
            _device = torch.device("cpu")
            logger.info(
                "Diarização vai usar CPU (sem CUDA) — esperado ~3-5x mais lento que GPU",
                device=str(_device),
            )
    return _device


def _get_pipeline() -> Any:
    """Carrega o pipeline pyannote (singleton thread-safe + GPU detection)."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                token = settings.HF_TOKEN
                if not token:
                    raise DiarizationUnavailableError(
                        "HF_TOKEN não configurado — diarização desabilitada. "
                        "Defina ESKUTA_HF_TOKEN no .env (dev) ou build secret (prod)."
                    )
                # Import lazy — pyannote.audio puxa lightning, transformers, etc.
                from pyannote.audio import Pipeline

                logger.info("Carregando modelo pyannote", model=PYANNOTE_MODEL)
                # Pyannote 4.x renomeou `use_auth_token` → `token`. Tentamos
                # o nome novo e caímos pro antigo em fallback (compat com
                # qualquer versão 3.x que ainda use o nome legado).
                try:
                    pipeline_obj = Pipeline.from_pretrained(
                        PYANNOTE_MODEL,
                        token=token,
                    )
                except TypeError:
                    # Versão 3.x — usa kwarg antigo
                    try:
                        pipeline_obj = Pipeline.from_pretrained(
                            PYANNOTE_MODEL,
                            use_auth_token=token,
                        )
                    except Exception as exc:
                        raise DiarizationUnavailableError(
                            f"Falha ao carregar pipeline pyannote: {exc}",
                        ) from exc
                except Exception as exc:
                    raise DiarizationUnavailableError(
                        f"Falha ao carregar pipeline pyannote: {exc}",
                    ) from exc

                # Move pipeline pra GPU se disponível — speedup ~5-10x
                # em reuniões longas. Pipeline.to() é in-place mas retorna
                # self por convenção; aceitamos os dois.
                device = _detect_device()
                moved = pipeline_obj.to(device)
                _pipeline = moved if moved is not None else pipeline_obj
    return _pipeline


def _load_audio_for_pyannote(audio_path: Path) -> Any:
    """
    Pré-carrega áudio em memória pra evitar o torchcodec quebrado.

    Pyannote 4.x tenta usar torchcodec quando recebe path/file. Quando
    o ambiente não tem DLLs compatíveis (caso típico do nosso bundle),
    isso quebra. Workaround oficial documentado pelo pyannote: passar
    `{'waveform': tensor (channel, time), 'sample_rate': int}`.

    Reusa `_read_audio_as_tensor` do VAD (que decoda via ffmpeg embutido,
    sem depender de torchcodec/torchaudio).
    """
    import torch

    from app.services.audio.vad import _read_audio_as_tensor

    # _read_audio_as_tensor devolve tensor 1-D (samples,). Pyannote exige
    # (channel, time) — adiciona dimensão de channel.
    wav_1d = _read_audio_as_tensor(audio_path, sampling_rate=PYANNOTE_SAMPLE_RATE)
    waveform = wav_1d.unsqueeze(0)  # (1, samples) mono

    # Move pro mesmo device do pipeline pra evitar copy implícito.
    device = _detect_device()
    if isinstance(device, torch.device) and device.type == "cuda":
        waveform = waveform.to(device)

    return {"waveform": waveform, "sample_rate": PYANNOTE_SAMPLE_RATE}


def diarize(audio_path: Path) -> list[SpeakerSegment]:
    """
    Identifica trechos de fala por speaker em `audio_path`.

    O áudio deve estar em formato suportado pelo pyannote — usar saída
    de `app.services.audio.converter.convert_to_optimized_mp3` (16kHz
    mono MP3) garante compat. Retorna lista ordenada por `start_sec`,
    com `speaker_id` no padrão "SPEAKER_00", "SPEAKER_01", ...

    Levanta `DiarizationUnavailableError` se HF_TOKEN faltar, ou
    `DiarizationError` em falhas runtime do pipeline.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

    pipeline = _get_pipeline()
    audio_input = _load_audio_for_pyannote(audio_path)

    try:
        diarization = pipeline(audio_input)
    except Exception as exc:
        raise DiarizationError(f"pyannote falhou ao diarizar: {exc}") from exc

    # Pyannote 4.x retorna `DiarizeOutput` com:
    #   - .speaker_diarization (Annotation com overlap)
    #   - .exclusive_speaker_diarization (Annotation sem overlap) ← preferido
    # Pyannote 3.x retorna `Annotation` direto (com .itertracks).
    # Detectamos e extraímos o annotation certo.
    if hasattr(diarization, "exclusive_speaker_diarization"):
        # 4.x — usa o sem-overlap (mais limpo pra merge com transcript)
        annotation = diarization.exclusive_speaker_diarization
    elif hasattr(diarization, "speaker_diarization"):
        # 4.x sem exclusive — fallback pro com overlap
        annotation = diarization.speaker_diarization
    else:
        # 3.x — já é Annotation
        annotation = diarization

    segments = sorted(
        (
            SpeakerSegment(
                start_sec=float(turn.start),
                end_sec=float(turn.end),
                speaker_id=str(speaker),
            )
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ),
        key=lambda s: s.start_sec,
    )

    logger.info(
        "Diarização concluída",
        audio=str(audio_path),
        segments=len(segments),
        unique_speakers=len({s.speaker_id for s in segments}),
    )
    return segments
