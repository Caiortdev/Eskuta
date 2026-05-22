"""Testes do runner (evaluation.runner)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from app.services.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.services.llm.router import LLMRouter
from evaluation.runner import (
    EvaluationReport,
    GoldenResult,
    main,
    run_evaluation,
)


def _fake_llm_router() -> LLMRouter:
    class _Provider(LLMProvider):
        @property
        def name(self) -> str:
            return "fake"

        @property
        def default_model(self) -> str:
            return "fake-model"

        def is_available(self) -> bool:
            return True

        async def complete(
            self,
            messages: Sequence[LLMMessage],
            **kwargs,
        ) -> LLMResponse:
            return LLMResponse(
                content=json.dumps({"issues": []}),
                provider="fake",
                model="fake-model",
                tokens_input=10,
                tokens_output=5,
                cost_usd=0.0001,
            )

    return LLMRouter({"fake": _Provider()})


# ============================================================
# GoldenResult / EvaluationReport — serialização
# ============================================================


def test_golden_result_to_dict() -> None:
    r = GoldenResult(golden_id="x", wer=0.1, der=0.2, ata_score=90.0)
    d = r.to_dict()
    assert d["wer"] == 0.1
    assert d["der"] == 0.2
    assert d["ata_score"] == 90.0


def test_evaluation_report_save_and_load_roundtrip(tmp_path: Path) -> None:
    report = EvaluationReport(
        manifest_name="test-suite",
        run_at="2026-05-22T10:00:00+00:00",
        results=[
            GoldenResult(golden_id="g1", wer=0.05),
            GoldenResult(golden_id="g2", wer=0.10, der=0.20),
        ],
    )
    out = tmp_path / "report.json"
    report.save(out)
    loaded = EvaluationReport.load(out)
    assert loaded.manifest_name == "test-suite"
    assert len(loaded.results) == 2
    assert loaded.results[0].wer == 0.05
    assert loaded.results[1].der == 0.20


# ============================================================
# run_evaluation — manifest vazio
# ============================================================


async def test_run_evaluation_empty_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"name": "empty", "goldens": []}),
        encoding="utf-8",
    )
    report = await run_evaluation(manifest_path, llm_router=_fake_llm_router())
    assert report.manifest_name == "empty"
    assert report.results == []


# ============================================================
# run_evaluation — golden com transcript hypothesis presente
# ============================================================


async def test_run_evaluation_computes_wer_when_hypothesis_exists(
    tmp_path: Path,
) -> None:
    # Setup: cria reference + hypothesis
    ref = tmp_path / "ref.txt"
    ref.write_text("olá mundo", encoding="utf-8")
    hyp = tmp_path / "g1.transcript.hyp.txt"
    hyp.write_text("olá mundo", encoding="utf-8")  # match perfeito → WER 0

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "test",
                "goldens": [
                    {
                        "id": "g1",
                        "audio_path": "no.mp3",
                        "reference_transcript_path": "ref.txt",
                        "duration_sec": 60.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = await run_evaluation(
        manifest_path,
        llm_router=_fake_llm_router(),
        skip_ata_score=True,
    )
    assert len(report.results) == 1
    assert report.results[0].wer == 0.0


async def test_run_evaluation_skips_wer_when_hypothesis_missing(
    tmp_path: Path,
) -> None:
    ref = tmp_path / "ref.txt"
    ref.write_text("olá mundo", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "test",
                "goldens": [
                    {
                        "id": "g1",
                        "audio_path": "no.mp3",
                        "reference_transcript_path": "ref.txt",
                        "duration_sec": 60.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = await run_evaluation(
        manifest_path,
        llm_router=_fake_llm_router(),
        skip_ata_score=True,
    )
    assert report.results[0].wer is None  # sem hypothesis → não calcula


# ============================================================
# run_evaluation — DER
# ============================================================


async def test_run_evaluation_computes_der_when_both_present(tmp_path: Path) -> None:
    ref_txt = tmp_path / "ref.txt"
    ref_txt.write_text("oi", encoding="utf-8")
    ref_diar = tmp_path / "ref.diar.json"
    ref_diar.write_text(
        json.dumps([{"start_sec": 0.0, "end_sec": 5.0, "speaker_id": "A"}]),
        encoding="utf-8",
    )
    hyp_diar = tmp_path / "g1.diarization.hyp.json"
    hyp_diar.write_text(
        json.dumps([{"start_sec": 0.0, "end_sec": 5.0, "speaker_id": "A"}]),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "test",
                "goldens": [
                    {
                        "id": "g1",
                        "audio_path": "no.mp3",
                        "reference_transcript_path": "ref.txt",
                        "reference_diarization_path": "ref.diar.json",
                        "duration_sec": 60.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = await run_evaluation(
        manifest_path,
        llm_router=_fake_llm_router(),
        skip_ata_score=True,
    )
    assert report.results[0].der == 0.0  # diarizações idênticas


# ============================================================
# run_evaluation — ata_score
# ============================================================


async def test_run_evaluation_computes_ata_score_when_hypothesis_exists(
    tmp_path: Path,
) -> None:
    ref_txt = tmp_path / "ref.txt"
    ref_txt.write_text("oi", encoding="utf-8")
    minutes_hyp = tmp_path / "g1.minutes.hyp.json"
    minutes_hyp.write_text(json.dumps({"title": "X"}), encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "test",
                "goldens": [
                    {
                        "id": "g1",
                        "audio_path": "no.mp3",
                        "reference_transcript_path": "ref.txt",
                        "duration_sec": 60.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = await run_evaluation(manifest_path, llm_router=_fake_llm_router())
    # Fake LLM devolve {"issues":[]} → score 100
    assert report.results[0].ata_score == 100.0


async def test_run_evaluation_continues_on_per_golden_error(tmp_path: Path) -> None:
    """Erro numa golden NÃO para o run das outras."""
    # Golden 1 quebra (ref file missing); Golden 2 OK
    ref2 = tmp_path / "ref2.txt"
    ref2.write_text("oi", encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "test",
                "goldens": [
                    {
                        "id": "broken",
                        "audio_path": "no.mp3",
                        "reference_transcript_path": "DOES_NOT_EXIST.txt",
                        "duration_sec": 60.0,
                    },
                    {
                        "id": "ok",
                        "audio_path": "no.mp3",
                        "reference_transcript_path": "ref2.txt",
                        "duration_sec": 60.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = await run_evaluation(
        manifest_path,
        llm_router=_fake_llm_router(),
        skip_ata_score=True,
    )
    assert len(report.results) == 2
    assert report.results[0].error is not None
    assert report.results[1].error is None


# ============================================================
# CLI
# ============================================================


def test_cli_writes_output_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "m.json"
    manifest_path.write_text(
        json.dumps({"name": "x", "goldens": []}),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    exit_code = main([str(manifest_path), "--out", str(out), "--skip-ata-score"])
    assert exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["manifest_name"] == "x"
