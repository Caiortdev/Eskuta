"""
Testes dos schemas Pydantic da ata (app.services.minutes.schemas).

Foco: validar que campos obrigatórios são exigidos, opcionais aceitam
null, listas default vazias, evidence é obrigatório em topics/
decisions/action_items, e que JSON inválido é rejeitado de forma
limpa pelo Pydantic.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.services.minutes.schemas import (
    ActionItem,
    Decision,
    Evidence,
    MinutesOutput,
    Topic,
)


def _make_evidence(quote: str = "trecho qualquer") -> Evidence:
    return Evidence(quote=quote)


# ============================================================
# Evidence
# ============================================================


def test_evidence_minimal_valid() -> None:
    e = Evidence(quote="oi mundo")
    assert e.quote == "oi mundo"
    assert e.speaker is None
    assert e.timestamp_sec is None


def test_evidence_with_all_fields() -> None:
    e = Evidence(quote="oi", speaker="João", timestamp_sec=12.5)
    assert e.speaker == "João"
    assert e.timestamp_sec == 12.5


def test_evidence_empty_quote_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(quote="")


def test_evidence_negative_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(quote="oi", timestamp_sec=-1.0)


# ============================================================
# Topic / Decision / ActionItem
# ============================================================


def test_topic_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Topic.model_validate({"title": "X", "summary": "Y"})


def test_topic_valid() -> None:
    t = Topic(title="X", summary="Y", evidence=_make_evidence())
    assert t.title == "X"
    assert t.evidence.quote == "trecho qualquer"


def test_decision_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Decision.model_validate({"description": "Decidir"})


def test_action_item_optional_fields_default_none() -> None:
    a = ActionItem(description="Fazer X", evidence=_make_evidence())
    assert a.assigned_to is None
    assert a.deadline is None


def test_action_item_with_all_fields() -> None:
    a = ActionItem(
        description="Fazer X",
        assigned_to="Maria",
        deadline="sexta",
        evidence=_make_evidence(),
    )
    assert a.assigned_to == "Maria"
    assert a.deadline == "sexta"


def test_action_item_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        ActionItem.model_validate({"description": "Fazer X"})


# ============================================================
# MinutesOutput
# ============================================================


def _minimal_minutes() -> MinutesOutput:
    return MinutesOutput(
        title="Reunião X",
        executive_summary="Resumo curto",
    )


def test_minutes_output_minimal_valid() -> None:
    m = _minimal_minutes()
    assert m.title == "Reunião X"
    assert m.date is None
    assert m.participants == []
    assert m.topics == []
    assert m.decisions == []
    assert m.action_items == []
    assert m.open_questions == []


def test_minutes_output_full_roundtrip() -> None:
    data = {
        "title": "Planning Sprint 12",
        "date": "2026-05-21",
        "participants": ["João", "Maria"],
        "executive_summary": "Definido escopo, dividido tarefas.",
        "topics": [
            {
                "title": "Escopo",
                "summary": "Discutido o escopo da sprint.",
                "evidence": {
                    "quote": "vamos focar no escopo essencial",
                    "speaker": "João",
                    "timestamp_sec": 12.0,
                },
            }
        ],
        "decisions": [
            {
                "description": "Adotar Postgres",
                "evidence": {"quote": "decidimos usar Postgres", "speaker": "Maria"},
            }
        ],
        "action_items": [
            {
                "description": "Configurar CI",
                "assigned_to": "João",
                "deadline": "sexta",
                "evidence": {"quote": "João vai configurar o CI até sexta"},
            }
        ],
        "open_questions": ["Quem vai fazer o deploy?"],
    }
    m = MinutesOutput.model_validate(data)
    assert m.title == "Planning Sprint 12"
    assert len(m.topics) == 1
    assert m.topics[0].evidence.timestamp_sec == 12.0
    assert m.action_items[0].assigned_to == "João"


def test_minutes_output_validate_from_json_string() -> None:
    payload = json.dumps(
        {
            "title": "X",
            "executive_summary": "Y",
        }
    )
    m = MinutesOutput.model_validate_json(payload)
    assert m.title == "X"


def test_minutes_output_missing_required_fields_raises() -> None:
    with pytest.raises(ValidationError):
        MinutesOutput.model_validate({"executive_summary": "sem título"})
    with pytest.raises(ValidationError):
        MinutesOutput.model_validate({"title": "sem resumo"})


def test_minutes_output_empty_title_rejected() -> None:
    with pytest.raises(ValidationError):
        MinutesOutput(title="", executive_summary="resumo")


def test_minutes_output_ignores_extra_fields() -> None:
    """LLM pode adicionar campos extras; não devemos quebrar."""
    data = {
        "title": "X",
        "executive_summary": "Y",
        "notes": "campo extra que LLM inventou",
        "metadata": {"foo": "bar"},
    }
    m = MinutesOutput.model_validate(data)
    assert m.title == "X"
    # Os campos extras simplesmente não viram atributos
    assert not hasattr(m, "notes")


def test_minutes_output_invalid_nested_evidence_propagates() -> None:
    """Se um action_item tem evidence inválida, a validação inteira falha."""
    data = {
        "title": "X",
        "executive_summary": "Y",
        "action_items": [
            {
                "description": "Fazer X",
                # evidence faltando
            }
        ],
    }
    with pytest.raises(ValidationError):
        MinutesOutput.model_validate(data)


def test_minutes_output_dump_then_reload_is_idempotent() -> None:
    m = MinutesOutput(
        title="X",
        executive_summary="Y",
        action_items=[ActionItem(description="Z", evidence=_make_evidence("citação"))],
    )
    payload = m.model_dump_json()
    m2 = MinutesOutput.model_validate_json(payload)
    assert m2.action_items[0].description == "Z"
    assert m2.action_items[0].evidence.quote == "citação"
