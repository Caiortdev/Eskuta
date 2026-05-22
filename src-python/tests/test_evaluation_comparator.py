"""Testes do comparator (evaluation.comparator)."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.comparator import (
    MetricDelta,
    _improved_higher_is_better,
    _improved_lower_is_better,
    _safe_delta,
    compare_reports,
    main,
)
from evaluation.runner import EvaluationReport, GoldenResult


def _report(name: str, results: list[GoldenResult]) -> EvaluationReport:
    return EvaluationReport(
        manifest_name=name,
        run_at="2026-05-22T00:00:00+00:00",
        results=results,
    )


# ============================================================
# Helpers
# ============================================================


def test_safe_delta_with_nones_returns_none() -> None:
    assert _safe_delta(None, 1.0) is None
    assert _safe_delta(1.0, None) is None
    assert _safe_delta(None, None) is None


def test_safe_delta_numeric() -> None:
    assert _safe_delta(0.1, 0.05) == -0.05


def test_improved_lower_is_better_true_when_decreased() -> None:
    assert _improved_lower_is_better(0.2, 0.1) is True
    assert _improved_lower_is_better(0.1, 0.2) is False
    assert _improved_lower_is_better(0.1, 0.1) is False  # estritamente menor


def test_improved_higher_is_better_true_when_increased() -> None:
    assert _improved_higher_is_better(80.0, 90.0) is True
    assert _improved_higher_is_better(90.0, 80.0) is False


def test_improved_with_none_returns_none() -> None:
    assert _improved_lower_is_better(None, 0.1) is None
    assert _improved_higher_is_better(80.0, None) is None


# ============================================================
# compare_reports
# ============================================================


def test_compare_identical_reports_all_neutral() -> None:
    results = [GoldenResult(golden_id="g1", wer=0.1, der=0.2, ata_score=80.0)]
    a = _report("a", results)
    b = _report("b", [GoldenResult(golden_id="g1", wer=0.1, der=0.2, ata_score=80.0)])

    cmp = compare_reports(a, b)
    assert len(cmp.comparisons) == 1
    c = cmp.comparisons[0]
    # WER/DER iguais → não melhorou (estritamente menor é falso) → improved=False
    assert c.wer.improved is False
    assert c.wer.delta == 0.0


def test_compare_wer_improved() -> None:
    baseline = _report("base", [GoldenResult(golden_id="g1", wer=0.2)])
    current = _report("cur", [GoldenResult(golden_id="g1", wer=0.1)])
    cmp = compare_reports(baseline, current)
    assert cmp.comparisons[0].wer.improved is True
    assert cmp.comparisons[0].wer.delta == -0.1


def test_compare_wer_regressed() -> None:
    baseline = _report("base", [GoldenResult(golden_id="g1", wer=0.1)])
    current = _report("cur", [GoldenResult(golden_id="g1", wer=0.2)])
    cmp = compare_reports(baseline, current)
    assert cmp.comparisons[0].wer.improved is False


def test_compare_ata_score_higher_is_better() -> None:
    baseline = _report("base", [GoldenResult(golden_id="g1", ata_score=70.0)])
    current = _report("cur", [GoldenResult(golden_id="g1", ata_score=90.0)])
    cmp = compare_reports(baseline, current)
    assert cmp.comparisons[0].ata_score.improved is True
    assert cmp.comparisons[0].ata_score.delta == 20.0


def test_compare_handles_goldens_only_in_one_report() -> None:
    baseline = _report("base", [GoldenResult(golden_id="g1", wer=0.1)])
    current = _report("cur", [GoldenResult(golden_id="g2", wer=0.2)])
    cmp = compare_reports(baseline, current)
    # Tanto g1 quanto g2 aparecem (union)
    ids = {c.golden_id for c in cmp.comparisons}
    assert ids == {"g1", "g2"}
    # g1 só tem baseline → delta None pra wer
    g1 = next(c for c in cmp.comparisons if c.golden_id == "g1")
    assert g1.wer.baseline == 0.1
    assert g1.wer.current is None
    assert g1.wer.delta is None
    assert g1.wer.improved is None


def test_compare_summary_counts() -> None:
    baseline = _report(
        "b",
        [
            GoldenResult(golden_id="g1", wer=0.2),
            GoldenResult(golden_id="g2", wer=0.1),
        ],
    )
    current = _report(
        "c",
        [
            GoldenResult(golden_id="g1", wer=0.1),  # improved
            GoldenResult(golden_id="g2", wer=0.2),  # regressed
        ],
    )
    cmp = compare_reports(baseline, current)
    assert cmp.summary["wer"] == {"improved": 1, "regressed": 1, "no_data": 0}
    assert cmp.summary["total_goldens"] == 2


def test_compare_metric_delta_dataclass() -> None:
    md = MetricDelta(baseline=0.1, current=0.05, delta=-0.05, improved=True)
    assert md.improved is True


def test_compare_report_to_dict() -> None:
    baseline = _report("b", [GoldenResult(golden_id="g1", wer=0.1)])
    current = _report("c", [GoldenResult(golden_id="g1", wer=0.05)])
    cmp = compare_reports(baseline, current)
    d = cmp.to_dict()
    assert d["baseline_name"] == "b"
    assert d["current_name"] == "c"
    assert d["comparisons"][0]["wer"]["delta"] == -0.05


# ============================================================
# CLI
# ============================================================


def test_cli_prints_json_to_stdout(tmp_path: Path, capsys) -> None:
    base_path = tmp_path / "base.json"
    cur_path = tmp_path / "cur.json"
    _report("b", [GoldenResult(golden_id="g1", wer=0.2)]).save(base_path)
    _report("c", [GoldenResult(golden_id="g1", wer=0.1)]).save(cur_path)

    exit_code = main([str(base_path), str(cur_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["baseline_name"] == "b"
    assert data["comparisons"][0]["wer"]["improved"] is True


def test_cli_writes_output_file(tmp_path: Path) -> None:
    base_path = tmp_path / "base.json"
    cur_path = tmp_path / "cur.json"
    out_path = tmp_path / "diff.json"
    _report("b", [GoldenResult(golden_id="g1", wer=0.2)]).save(base_path)
    _report("c", [GoldenResult(golden_id="g1", wer=0.1)]).save(cur_path)

    exit_code = main([str(base_path), str(cur_path), "--out", str(out_path)])
    assert exit_code == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["comparisons"][0]["wer"]["delta"] == -0.1
