"""
Comparator de runs do eval framework (Fase 1.9.5 / Bloco A.2).

Recebe dois `EvaluationReport` (baseline + current) e produz um
`ComparisonReport` com delta por golden + por métrica. Permite
responder objetivamente "essa mudança melhorou ou piorou?".

CLI:
    python -m evaluation.comparator baseline.json current.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.runner import EvaluationReport, GoldenResult


@dataclass(frozen=True)
class MetricDelta:
    """Delta de uma métrica entre dois runs."""

    baseline: float | None
    current: float | None
    delta: float | None  # current - baseline (positive = "value got higher")
    improved: bool | None  # True se ficou melhor (depende da métrica)


@dataclass(frozen=True)
class GoldenComparison:
    golden_id: str
    wer: MetricDelta
    der: MetricDelta
    ata_score: MetricDelta


@dataclass(frozen=True)
class ComparisonReport:
    baseline_name: str
    current_name: str
    comparisons: list[GoldenComparison]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        def _md(d: MetricDelta) -> dict[str, Any]:
            return {
                "baseline": d.baseline,
                "current": d.current,
                "delta": d.delta,
                "improved": d.improved,
            }

        return {
            "baseline_name": self.baseline_name,
            "current_name": self.current_name,
            "comparisons": [
                {
                    "golden_id": c.golden_id,
                    "wer": _md(c.wer),
                    "der": _md(c.der),
                    "ata_score": _md(c.ata_score),
                }
                for c in self.comparisons
            ],
            "summary": self.summary,
        }


def _safe_delta(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None:
        return None
    return current - baseline


def _improved_lower_is_better(baseline: float | None, current: float | None) -> bool | None:
    """Pra WER/DER — current < baseline = melhor."""
    if baseline is None or current is None:
        return None
    return current < baseline


def _improved_higher_is_better(baseline: float | None, current: float | None) -> bool | None:
    """Pra ata_score — current > baseline = melhor."""
    if baseline is None or current is None:
        return None
    return current > baseline


def compare_reports(
    baseline: EvaluationReport,
    current: EvaluationReport,
) -> ComparisonReport:
    """Junta ambos por `golden_id` e calcula deltas."""
    baseline_by_id = {r.golden_id: r for r in baseline.results}
    current_by_id = {r.golden_id: r for r in current.results}
    all_ids = sorted(set(baseline_by_id) | set(current_by_id))

    comparisons: list[GoldenComparison] = []
    for gid in all_ids:
        b = baseline_by_id.get(gid)
        c = current_by_id.get(gid)
        comparisons.append(_compare_one(gid, b, c))

    summary = _build_summary(comparisons)
    return ComparisonReport(
        baseline_name=baseline.manifest_name,
        current_name=current.manifest_name,
        comparisons=comparisons,
        summary=summary,
    )


def _compare_one(
    golden_id: str,
    baseline: GoldenResult | None,
    current: GoldenResult | None,
) -> GoldenComparison:
    b_wer = baseline.wer if baseline else None
    c_wer = current.wer if current else None
    b_der = baseline.der if baseline else None
    c_der = current.der if current else None
    b_ata = baseline.ata_score if baseline else None
    c_ata = current.ata_score if current else None

    return GoldenComparison(
        golden_id=golden_id,
        wer=MetricDelta(
            baseline=b_wer,
            current=c_wer,
            delta=_safe_delta(b_wer, c_wer),
            improved=_improved_lower_is_better(b_wer, c_wer),
        ),
        der=MetricDelta(
            baseline=b_der,
            current=c_der,
            delta=_safe_delta(b_der, c_der),
            improved=_improved_lower_is_better(b_der, c_der),
        ),
        ata_score=MetricDelta(
            baseline=b_ata,
            current=c_ata,
            delta=_safe_delta(b_ata, c_ata),
            improved=_improved_higher_is_better(b_ata, c_ata),
        ),
    )


def _build_summary(comparisons: list[GoldenComparison]) -> dict[str, Any]:
    """Estatísticas agregadas — quantos melhoraram, pioraram, neutros."""

    def _count(metric_name: str) -> dict[str, int]:
        improved = sum(1 for c in comparisons if _get_metric(c, metric_name).improved is True)
        regressed = sum(1 for c in comparisons if _get_metric(c, metric_name).improved is False)
        no_data = sum(1 for c in comparisons if _get_metric(c, metric_name).improved is None)
        return {"improved": improved, "regressed": regressed, "no_data": no_data}

    return {
        "wer": _count("wer"),
        "der": _count("der"),
        "ata_score": _count("ata_score"),
        "total_goldens": len(comparisons),
    }


def _get_metric(comparison: GoldenComparison, name: str) -> MetricDelta:
    return getattr(comparison, name)


# ============================================================
# CLI
# ============================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.comparator",
        description="Compara dois EvaluationReports (baseline vs current).",
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Salva diff JSON em.")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    baseline = EvaluationReport.load(args.baseline)
    current = EvaluationReport.load(args.current)
    report = compare_reports(baseline, current)

    text = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Diff salvo em {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
