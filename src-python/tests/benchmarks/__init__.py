"""
Suite de benchmarks (Fase 1.9.5 / Bloco A.4).

Roda com `pytest-benchmark`. O objetivo principal é **detecção de
regressão** — comparamos contra o `baseline.json` committado pra
flagear quando uma mudança piora performance.

Como rodar local:
    pytest src-python/tests/benchmarks/ --benchmark-only
    pytest src-python/tests/benchmarks/ --benchmark-only --benchmark-compare=baseline

Como atualizar o baseline (após mudança intencional):
    pytest src-python/tests/benchmarks/ --benchmark-only --benchmark-save=baseline

Nota importante: a maior parte dos benchmarks abaixo MOCKA o trabalho
pesado (ffmpeg, silero, Groq). Os números medem **overhead da nossa
orquestração** (parsing, dispatch, copy de dados), não o tempo real
de cada operação externa. Pra benchmarks end-to-end com audio real,
ver `eval/run_evaluation.py` (Bloco A.2).
"""
