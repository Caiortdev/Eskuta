"""
Testes do módulo de prompts (app.services.minutes.prompts).

Como prompts são strings constantes, os testes focam em:
1. Consistência prompt↔schema — o few-shot example DEVE bater com MinutesOutput
2. Presença de elementos-chave no prompt (regras anti-alucinação, schema,
   exemplo, anti-exemplo) — regressão "alguém deletou X sem querer"
3. Comportamento dos helpers build_*_user_prompt
"""

from __future__ import annotations

import json

import pytest

from app.services.minutes.prompts import (
    FEW_SHOT_EXAMPLE_MINUTES,
    FEW_SHOT_EXAMPLE_TRANSCRIPT,
    SYSTEM_PROMPT_MINUTES,
    VALIDATION_PROMPT,
    build_user_prompt,
    build_validation_user_prompt,
)
from app.services.minutes.schemas import MinutesOutput
from app.services.minutes.validator import validate_minutes

# ============================================================
# Consistência few-shot ↔ schema
# ============================================================


def test_few_shot_example_validates_against_minutes_output() -> None:
    """
    Garante que o exemplo embutido no system prompt é uma instância
    válida do schema oficial — protege contra deriva quando alguém
    mudar o schema sem atualizar o prompt (ou vice-versa).
    """
    parsed = MinutesOutput.model_validate(FEW_SHOT_EXAMPLE_MINUTES)
    assert parsed.title == "Alinhamento Projeto Alpha e Orçamento Design"
    assert "João" in parsed.participants
    assert "Maria" in parsed.participants
    assert len(parsed.topics) == 2
    assert len(parsed.decisions) == 1
    assert len(parsed.action_items) == 2
    assert parsed.open_questions == []


def test_few_shot_evidences_all_present_in_example_transcript() -> None:
    """
    Toda evidence do exemplo deve ser uma citação real do
    FEW_SHOT_EXAMPLE_TRANSCRIPT — caso contrário, o próprio exemplo
    contradiria a regra "evidence sempre real" que o prompt ensina.
    """
    minutes = MinutesOutput.model_validate(FEW_SHOT_EXAMPLE_MINUTES)
    report = validate_minutes(minutes, FEW_SHOT_EXAMPLE_TRANSCRIPT)
    assert report.is_valid, f"Few-shot example tem evidences inventadas: {report.problems!r}"


# ============================================================
# Conteúdo do SYSTEM_PROMPT_MINUTES
# ============================================================


def test_system_prompt_is_non_empty() -> None:
    assert SYSTEM_PROMPT_MINUTES.strip()
    assert len(SYSTEM_PROMPT_MINUTES) > 500  # prompts curtos demais perdem qualidade


def test_system_prompt_identifies_as_eskuta() -> None:
    assert "Eskuta" in SYSTEM_PROMPT_MINUTES


def test_system_prompt_specifies_portuguese_brazilian() -> None:
    """O tom precisa ser pt-BR — princípio do MAPA_PROJETO."""
    assert "português brasileiro" in SYSTEM_PROMPT_MINUTES.lower()


@pytest.mark.parametrize(
    "rule_keyword",
    [
        "NUNCA INVENTE",  # regra 1
        "EVIDÊNCIA",  # regra 2
        "PORTUGUÊS BRASILEIRO",  # regra 3
        "IGNORE RUÍDO",  # regra 4
        "PRESERVE NÚMEROS",  # regra 5
        "AÇÃO",  # regra 6 (ação vs decisão)
    ],
)
def test_system_prompt_contains_each_inviolable_rule(rule_keyword: str) -> None:
    """Cada uma das 6 regras invioláveis deve aparecer no prompt."""
    assert rule_keyword in SYSTEM_PROMPT_MINUTES


def test_system_prompt_has_chain_of_thought_section() -> None:
    """Princípio 6 do MAPA_PROJETO — LLM raciocina antes de responder."""
    assert "PROCESSO MENTAL" in SYSTEM_PROMPT_MINUTES


def test_system_prompt_has_few_shot_example_block() -> None:
    assert "EXEMPLO DE RESPOSTA BOA" in SYSTEM_PROMPT_MINUTES
    # Conteúdo do exemplo aparece literalmente
    assert "Alinhamento Projeto Alpha e Orçamento Design" in SYSTEM_PROMPT_MINUTES


def test_system_prompt_has_anti_example_block() -> None:
    assert "ANTI-EXEMPLO" in SYSTEM_PROMPT_MINUTES
    assert "NUNCA FAÇA ISSO" in SYSTEM_PROMPT_MINUTES


def test_system_prompt_has_schema_template() -> None:
    """O schema JSON deve estar visível no prompt — caso LLM ignore tools."""
    assert '"title"' in SYSTEM_PROMPT_MINUTES
    assert '"participants"' in SYSTEM_PROMPT_MINUTES
    assert '"executive_summary"' in SYSTEM_PROMPT_MINUTES
    assert '"action_items"' in SYSTEM_PROMPT_MINUTES
    assert '"evidence"' in SYSTEM_PROMPT_MINUTES
    assert '"open_questions"' in SYSTEM_PROMPT_MINUTES


def test_system_prompt_emphasizes_truthfulness_over_completeness() -> None:
    """Princípio crítico: poucos itens verdadeiros > muitos itens inventados."""
    assert "PREFIRO UMA ATA COM POUCOS ITENS VERDADEIROS" in SYSTEM_PROMPT_MINUTES


def test_system_prompt_example_json_is_valid_json() -> None:
    """O JSON do few-shot embutido no prompt deve ser sintaticamente válido."""
    # Extrai o bloco entre o primeiro ```json após "Resposta (saída)" e o próximo ```
    marker = "Resposta (saída):"
    start = SYSTEM_PROMPT_MINUTES.find(marker)
    assert start != -1
    json_start = SYSTEM_PROMPT_MINUTES.find("```json", start) + len("```json")
    json_end = SYSTEM_PROMPT_MINUTES.find("```", json_start)
    payload = SYSTEM_PROMPT_MINUTES[json_start:json_end].strip()
    parsed = json.loads(payload)
    # E também valida contra o schema oficial
    MinutesOutput.model_validate(parsed)


# ============================================================
# Conteúdo do VALIDATION_PROMPT
# ============================================================


def test_validation_prompt_is_non_empty() -> None:
    assert VALIDATION_PROMPT.strip()


def test_validation_prompt_describes_auditor_role() -> None:
    assert "auditor" in VALIDATION_PROMPT.lower()


def test_validation_prompt_mentions_inconsistencies() -> None:
    assert "INCONSISTÊNCIAS" in VALIDATION_PROMPT or "inconsistências" in VALIDATION_PROMPT


def test_validation_prompt_has_issues_schema() -> None:
    assert "issues" in VALIDATION_PROMPT
    assert "fabricated_evidence" in VALIDATION_PROMPT


# ============================================================
# Helpers build_*_user_prompt
# ============================================================


def test_build_user_prompt_embeds_transcript() -> None:
    transcript = "João: oi tudo bem? Maria: tudo, e você?"
    prompt = build_user_prompt(transcript)
    assert "TRANSCRIÇÃO" in prompt
    assert transcript in prompt


def test_build_user_prompt_instructs_json_only() -> None:
    prompt = build_user_prompt("qualquer transcrição")
    assert "JSON" in prompt


def test_build_user_prompt_strips_transcript_whitespace() -> None:
    prompt = build_user_prompt("  \n  texto da reunião  \n  ")
    assert "texto da reunião" in prompt
    # Não deve haver linhas em branco no topo do bloco
    assert "TRANSCRIÇÃO\n\ntexto da reunião" in prompt


def test_build_validation_user_prompt_includes_both_sections() -> None:
    transcript = "Maria disse algo"
    minutes_json = '{"title": "X"}'
    prompt = build_validation_user_prompt(transcript, minutes_json)
    assert "TRANSCRIÇÃO ORIGINAL" in prompt
    assert "ATA GERADA" in prompt
    assert transcript in prompt
    assert minutes_json in prompt


def test_build_validation_user_prompt_strips_both_inputs() -> None:
    prompt = build_validation_user_prompt("  oi  ", "  {}  ")
    assert "TRANSCRIÇÃO ORIGINAL\n\noi" in prompt
