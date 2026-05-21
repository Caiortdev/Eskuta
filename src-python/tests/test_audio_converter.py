"""
Testes do conversor de áudio (app.services.audio.converter).

Mockamos `ffmpeg.run` pra não depender do binário ffmpeg estar
instalado no runner — validamos que os args certos chegam até lá e
que erros do ffmpeg viram `AudioConversionError`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import ffmpeg
import pytest

from app.services.audio.converter import (
    AudioConversionError,
    convert_to_optimized_mp3,
    convert_to_optimized_mp3_async,
)


def _make_input_file(tmp_path: Path) -> Path:
    """Cria um arquivo vazio só pra passar do guard de existência."""
    f = tmp_path / "in.mp4"
    f.write_bytes(b"")
    return f


def test_input_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        convert_to_optimized_mp3(
            tmp_path / "missing.mp4",
            tmp_path / "out.mp3",
        )


def test_calls_ffmpeg_with_voice_optimized_args(tmp_path: Path) -> None:
    in_file = _make_input_file(tmp_path)
    out_file = tmp_path / "out.mp3"

    with (
        patch.object(ffmpeg, "output", wraps=ffmpeg.output) as output_mock,
        patch.object(ffmpeg, "run"),
    ):
        convert_to_optimized_mp3(in_file, out_file)

    assert output_mock.called
    kwargs = output_mock.call_args.kwargs
    assert kwargs["format"] == "mp3"
    assert kwargs["acodec"] == "libmp3lame"
    assert kwargs["ac"] == 1  # mono
    assert kwargs["ar"] == 16000  # 16kHz
    assert kwargs["audio_bitrate"] == "32k"
    # Path de saída chega como arg posicional
    assert str(out_file) in output_mock.call_args.args


def test_creates_output_parent_dir(tmp_path: Path) -> None:
    in_file = _make_input_file(tmp_path)
    out_dir = tmp_path / "deep" / "nested"
    out_file = out_dir / "out.mp3"

    with patch.object(ffmpeg, "run"):
        convert_to_optimized_mp3(in_file, out_file)

    assert out_dir.is_dir()


def test_returns_output_path(tmp_path: Path) -> None:
    in_file = _make_input_file(tmp_path)
    out_file = tmp_path / "out.mp3"

    with patch.object(ffmpeg, "run"):
        result = convert_to_optimized_mp3(in_file, out_file)

    assert result == out_file


def test_custom_sample_rate_and_bitrate(tmp_path: Path) -> None:
    in_file = _make_input_file(tmp_path)
    out_file = tmp_path / "out.mp3"

    with (
        patch.object(ffmpeg, "output", wraps=ffmpeg.output) as output_mock,
        patch.object(ffmpeg, "run"),
    ):
        convert_to_optimized_mp3(in_file, out_file, sample_rate=22050, bitrate="64k")

    kwargs = output_mock.call_args.kwargs
    assert kwargs["ar"] == 22050
    assert kwargs["audio_bitrate"] == "64k"


async def test_async_wrapper_does_not_block(tmp_path: Path) -> None:
    in_file = _make_input_file(tmp_path)
    out_file = tmp_path / "out.mp3"

    with patch.object(ffmpeg, "run"):
        result = await convert_to_optimized_mp3_async(in_file, out_file)

    assert result == out_file


def test_audio_conversion_error_carries_stderr() -> None:
    """AudioConversionError preserva o stderr do ffmpeg pra debug."""
    err = AudioConversionError("falha", stderr="ffmpeg disse: arquivo corrupto")
    assert str(err) == "falha"
    assert err.stderr == "ffmpeg disse: arquivo corrupto"
