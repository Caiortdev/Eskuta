"""
Runner do eval framework (Fase 1.9.5 / Bloco A.2).

Lê um `BenchmarkManifest`, roda o pipeline em cada golden, calcula
WER + DER + ata_score, e produz um `EvaluationReport` serializável.

Uso CLI:
    python -m evaluation.runner tests/golden/manifest.json --out run.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.services.llm.router import LLMRouter
from evaluation.manifest import BenchmarkManifest, GoldenManifest
from evaluation.metrics import (
    compute_ata_score,
    compute_der,
    compute_wer,
)


@dataclass
class GoldenResult:
    """Resultado de avaliação pra UMA golden."""

    golden_id: str
    wer: float | None = None
    der: float | None = None
    ata_score: float | None = None
    ata_issues: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationReport:
    """Resultado consolidado de um run sobre um manifest."""

    manifest_name: str
    run_at: str  # ISO 8601 UTC
    results: list[GoldenResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_name": self.manifest_name,
            "run_at": self.run_at,
            "results": [r.to_dict() for r in self.results],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> EvaluationReport:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = [GoldenResult(**r) for r in data.get("results", [])]
        return cls(
            manifest_name=data["manifest_name"],
            run_at=data["run_at"],
            results=results,
        )


async def run_evaluation(
    manifest_path: Path,
    *,
    llm_router: LLMRouter | None = None,
    skip_ata_score: bool = False,
) -> EvaluationReport:
    """
    Roda o eval em todos os goldens do manifest. Retorna o report.

    Args:
        manifest_path: path pra BenchmarkManifest JSON.
        llm_router: usado pra ata_score; default cria novo.
        skip_ata_score: pula a chamada de LLM (útil em CI sem API keys).
    """
    manifest = BenchmarkManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    router = llm_router or LLMRouter()

    results: list[GoldenResult] = []
    for golden in manifest.goldens:
        logger.info("Avaliando golden", id=golden.id)
        try:
            result = await _evaluate_one(
                golden,
                base_dir=base_dir,
                llm_router=router,
                skip_ata_score=skip_ata_score,
            )
        except Exception as exc:
            logger.exception("Erro avaliando golden", id=golden.id)
            result = GoldenResult(golden_id=golden.id, error=str(exc)[:300])
        results.append(result)

    return EvaluationReport(
        manifest_name=manifest.name,
        run_at=datetime.now(UTC).isoformat(),
        results=results,
    )


async def _evaluate_one(
    golden: GoldenManifest,
    *,
    base_dir: Path,
    llm_router: LLMRouter,
    skip_ata_score: bool,
) -> GoldenResult:
    """
    Roda pipeline na golden e calcula métricas.

    Esta função é o ponto de integração com o pipeline real
    (`process_meeting`). Como o pipeline grava no DB, o eval cria
    uma Meeting temp, processa, e lê os artefatos do DB. Por
    simplicidade do MVP, esta versão APENAS calcula métricas a
    partir do `hypothesis` que assumimos já existir num path
    paralelo a `reference_*_path` (com `.hyp.json` no final).

    Quando rodar de fato (com pipeline executado antes), as
    hypothesis files devem estar em:
      - `<base>/<id>.transcript.hyp.txt`
      - `<base>/<id>.diarization.hyp.json`
      - `<base>/<id>.minutes.hyp.json`
    """
    result = GoldenResult(golden_id=golden.id)
    base = base_dir

    # ---- WER ----
    ref_transcript = (base / golden.reference_transcript_path).read_text(encoding="utf-8")
    hyp_transcript_path = base / f"{golden.id}.transcript.hyp.txt"
    if hyp_transcript_path.exists():
        hyp_transcript = hyp_transcript_path.read_text(encoding="utf-8")
        result.wer = compute_wer(ref_transcript, hyp_transcript)

    # ---- DER ----
    if golden.reference_diarization_path:
        ref_diar = _load_speaker_segments(base / golden.reference_diarization_path)
        hyp_diar_path = base / f"{golden.id}.diarization.hyp.json"
        if hyp_diar_path.exists() and ref_diar:
            hyp_diar = _load_speaker_segments(hyp_diar_path)
            result.der = compute_der(ref_diar, hyp_diar)

    # ---- Ata score ----
    if not skip_ata_score:
        hyp_minutes_path = base / f"{golden.id}.minutes.hyp.json"
        if hyp_minutes_path.exists():
            minutes_json = hyp_minutes_path.read_text(encoding="utf-8")
            score = await compute_ata_score(minutes_json, ref_transcript, llm_router)
            result.ata_score = score.score
            result.ata_issues = score.issues

    return result


def _load_speaker_segments(path: Path) -> list:
    """Lê JSON com list de {start_sec, end_sec, speaker_id} → SpeakerSegment."""
    from app.services.diarization.pyannote_service import SpeakerSegment

    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        SpeakerSegment(
            start_sec=float(s["start_sec"]),
            end_sec=float(s["end_sec"]),
            speaker_id=str(s["speaker_id"]),
        )
        for s in data
    ]


# ============================================================
# CLI
# ============================================================


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.runner",
        description="Roda eval Eskuta sobre um manifest de goldens.",
    )
    parser.add_argument("manifest", type=Path, help="Path pro BenchmarkManifest JSON.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("eval-run.json"),
        help="Onde salvar o EvaluationReport (default: eval-run.json).",
    )
    parser.add_argument(
        "--skip-ata-score",
        action="store_true",
        help="Pula chamada de LLM-as-judge (útil em CI sem API keys).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    report = asyncio.run(run_evaluation(args.manifest, skip_ata_score=args.skip_ata_score))
    report.save(args.out)
    print(f"Eval done — {len(report.results)} goldens. Output: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
