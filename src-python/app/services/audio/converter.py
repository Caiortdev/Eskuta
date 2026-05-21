"""
Conversão de áudio/vídeo para MP3 otimizado pra voz.

Pipeline padrão pra Eskuta:
- 16kHz (taxa interna do Whisper — não adianta amostrar mais)
- Mono (voz não precisa estéreo)
- 32kbps (suficiente pra fala inteligível)

Reduz drasticamente o tamanho: 3h MP4 (~1.5GB) → ~40MB MP3.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import ffmpeg
from loguru import logger


class AudioConversionError(RuntimeError):
    """ffmpeg falhou ao converter o arquivo. `stderr` contém detalhes."""

    def __init__(self, message: str, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


def convert_to_optimized_mp3(
    input_path: Path,
    output_path: Path,
    *,
    sample_rate: int = 16000,
    bitrate: str = "32k",
    overwrite: bool = True,
) -> Path:
    """
    Converte `input_path` (qualquer formato suportado pelo ffmpeg) num
    MP3 mono 16kHz 32kbps escrito em `output_path`. Retorna o
    `output_path` por conveniência.

    Bloqueia até o ffmpeg terminar — pra chamar do event loop, use
    `convert_to_optimized_mp3_async`.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stream = ffmpeg.input(str(input_path))
    stream = ffmpeg.output(
        stream,
        str(output_path),
        format="mp3",
        acodec="libmp3lame",
        ac=1,  # mono
        ar=sample_rate,  # 16kHz
        audio_bitrate=bitrate,  # 32kbps
        loglevel="error",
    )
    if overwrite:
        stream = ffmpeg.overwrite_output(stream)

    try:
        ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as exc:  # pragma: no cover — depende de ffmpeg binário
        stderr_text = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else None
        logger.error(
            "Falha no ffmpeg",
            input=str(input_path),
            output=str(output_path),
            stderr=stderr_text,
        )
        raise AudioConversionError(
            f"Falha ao converter {input_path.name}",
            stderr=stderr_text,
        ) from exc

    logger.info(
        "Áudio convertido",
        input=str(input_path),
        output=str(output_path),
        sample_rate=sample_rate,
        bitrate=bitrate,
    )
    return output_path


async def convert_to_optimized_mp3_async(
    input_path: Path,
    output_path: Path,
    **kwargs: object,
) -> Path:
    """
    Wrapper async de `convert_to_optimized_mp3`. O ffmpeg é blocking,
    então rodamos no executor padrão do asyncio.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: convert_to_optimized_mp3(input_path, output_path, **kwargs),  # type: ignore[arg-type]
    )
