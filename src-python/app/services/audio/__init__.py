"""Pipeline de áudio do Eskuta — converter, VAD e chunker."""

from app.services.audio.chunker import AudioChunk, chunk_audio_smart
from app.services.audio.converter import (
    AudioConversionError,
    convert_to_optimized_mp3,
    convert_to_optimized_mp3_async,
)
from app.services.audio.vad import (
    NoSpeechDetectedError,
    SpeechSegment,
    compute_volume_db,
    detect_speech_segments,
)

__all__ = [
    "AudioChunk",
    "AudioConversionError",
    "NoSpeechDetectedError",
    "SpeechSegment",
    "chunk_audio_smart",
    "compute_volume_db",
    "convert_to_optimized_mp3",
    "convert_to_optimized_mp3_async",
    "detect_speech_segments",
]
