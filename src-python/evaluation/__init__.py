"""
Eval framework do Eskuta (Fase 1.9.5 / Bloco A.2 de MELHORIAS-CONCORRENTE).

Permite responder objetivamente perguntas como:
- "Trocar Groq por AssemblyAI degrada a transcrição?" → comparar WER
- "O novo prompt 1.8 está melhor?" → ata-score via LLM-as-judge
- "Snap-to-silence ajudou?" → comparar WER antes/depois

Estrutura:
- `metrics`: WER (jiwer), DER (pyannote.metrics), ata_score (LLM-as-judge)
- `manifest`: schema Pydantic dos "goldens" (reuniões de referência)
- `runner`: roda o pipeline em cada golden + calcula métricas
- `comparator`: diff entre 2 runs (regressão? melhoria?)

**Como adicionar goldens reais:** ver `tests/golden/README.md`.

**CLI:**
    python -m evaluation.runner tests/golden/manifest.json --out eval-run.json
    python -m evaluation.comparator baseline.json current.json
"""

from evaluation.comparator import ComparisonReport, compare_reports
from evaluation.manifest import BenchmarkManifest, GoldenManifest
from evaluation.metrics import (
    AtaScore,
    compute_ata_score,
    compute_der,
    compute_wer,
)
from evaluation.runner import (
    EvaluationReport,
    GoldenResult,
    run_evaluation,
)

__all__ = [
    "AtaScore",
    "BenchmarkManifest",
    "ComparisonReport",
    "EvaluationReport",
    "GoldenManifest",
    "GoldenResult",
    "compare_reports",
    "compute_ata_score",
    "compute_der",
    "compute_wer",
    "run_evaluation",
]
