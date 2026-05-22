"""
Testes do generator (app.services.minutes.generator).

Usa provider fake controlável (sem SDK real) pra exercer prompt
construction, parsing do JSON e propagação de ValidationError.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from app.services.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
)
from app.services.llm.router import LLMRouter
from app.services.minutes.generator import (
    DEFAULT_TEMPERATURE,
    GenerationResult,
    generate_minutes,
    regenerate_with_correction,
)
from app.services.minutes.prompts import FEW_SHOT_EXAMPLE_MINUTES
from app.services.minutes.schemas import MinutesOutput
from app.services.minutes.validator import (
    EvidenceProblem,
    ValidationReport,
    validate_minutes,
)


class _RecordingProvider(LLMProvider):
    """LLM fake: salva a chamada e devolve resposta pré-configurada."""

    def __init__(self, json_payload: str) -> None:
        self.json_payload = json_payload
        self.last_call: dict | None = None

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
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        self.last_call = {
            "messages": list(messages),
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": response_format,
        }
        return LLMResponse(
            content=self.json_payload,
            provider=self.name,
            model=model or self.default_model,
            tokens_input=1000,
            tokens_output=500,
            cost_usd=0.01,
        )


def _router_with_payload(payload: str | dict) -> LLMRouter:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return LLMRouter({"fake": _RecordingProvider(body)})


# ============================================================
# generate_minutes — happy path
# ============================================================


async def test_generate_minutes_returns_parsed_output() -> None:
    router = _router_with_payload(FEW_SHOT_EXAMPLE_MINUTES)
    result = await generate_minutes(router, "qualquer transcript")
    assert isinstance(result, GenerationResult)
    assert isinstance(result.minutes, MinutesOutput)
    assert result.minutes.title == "Alinhamento Projeto Alpha e Orçamento Design"
    assert result.llm_response.provider == "fake"
    assert result.llm_response.tokens_input == 1000


async def test_generate_minutes_uses_system_and_user_prompts() -> None:
    provider = _RecordingProvider(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    router = LLMRouter({"fake": provider})

    await generate_minutes(router, "minha transcrição aqui")

    messages = provider.last_call["messages"]
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "Eskuta" in messages[0].content
    assert messages[1].role == "user"
    assert "minha transcrição aqui" in messages[1].content


async def test_generate_minutes_default_temperature_is_anti_hallucination() -> None:
    provider = _RecordingProvider(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    router = LLMRouter({"fake": provider})
    await generate_minutes(router, "qq transcript")
    assert provider.last_call["temperature"] == DEFAULT_TEMPERATURE == 0.2


async def test_generate_minutes_forces_json_response_format() -> None:
    provider = _RecordingProvider(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    router = LLMRouter({"fake": provider})
    await generate_minutes(router, "qq")
    assert provider.last_call["response_format"] == {"type": "json_object"}


async def test_generate_minutes_custom_max_tokens_and_temperature() -> None:
    provider = _RecordingProvider(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    router = LLMRouter({"fake": provider})
    await generate_minutes(router, "qq", temperature=0.5, max_tokens=8000)
    assert provider.last_call["temperature"] == 0.5
    assert provider.last_call["max_tokens"] == 8000


async def test_generate_minutes_invalid_json_raises_validation_error() -> None:
    router = _router_with_payload("{ not json at all")
    with pytest.raises(ValidationError):
        await generate_minutes(router, "qq")


async def test_generate_minutes_missing_required_field_raises() -> None:
    # `executive_summary` é obrigatório no schema
    router = _router_with_payload({"title": "Reunião"})
    with pytest.raises(ValidationError):
        await generate_minutes(router, "qq")


# ============================================================
# regenerate_with_correction
# ============================================================


async def test_regenerate_with_correction_injects_problems_in_prompt() -> None:
    report = ValidationReport(
        problems=[
            EvidenceProblem(
                field_path="action_items[0].evidence",
                item_description="Fazer X",
                quote="texto inventado",
            ),
        ]
    )
    provider = _RecordingProvider(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    router = LLMRouter({"fake": provider})

    await regenerate_with_correction(router, "transcript original", report)

    user_msg = provider.last_call["messages"][1].content
    assert "CORREÇÕES NECESSÁRIAS" in user_msg
    assert "action_items[0].evidence" in user_msg
    assert "Fazer X" in user_msg
    assert "texto inventado" in user_msg
    assert "transcript original" in user_msg


async def test_regenerate_with_correction_preserves_system_prompt() -> None:
    """System prompt deve continuar IDÊNTICO pra preservar prompt cache."""
    report = ValidationReport(
        problems=[
            EvidenceProblem(field_path="decisions[0].evidence", item_description="X", quote="Y"),
        ]
    )
    provider = _RecordingProvider(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    router = LLMRouter({"fake": provider})

    await regenerate_with_correction(router, "qq", report)

    system_msg = provider.last_call["messages"][0]
    assert system_msg.role == "system"
    assert "Eskuta" in system_msg.content


async def test_regenerate_with_correction_rejects_valid_report() -> None:
    """Chamar regen com report.is_valid=True é programming error."""
    router = _router_with_payload(json.dumps(FEW_SHOT_EXAMPLE_MINUTES))
    with pytest.raises(ValueError):
        await regenerate_with_correction(router, "qq", ValidationReport())


async def test_regenerate_returns_new_generation_result() -> None:
    report = ValidationReport(
        problems=[
            EvidenceProblem(field_path="topics[0].evidence", item_description="A", quote="B"),
        ]
    )
    router = _router_with_payload(FEW_SHOT_EXAMPLE_MINUTES)
    result = await regenerate_with_correction(router, "qq", report)
    assert isinstance(result, GenerationResult)
    assert result.minutes.title == "Alinhamento Projeto Alpha e Orçamento Design"


# ============================================================
# Smoke: integração com validator real (mesma transcript do exemplo)
# ============================================================


async def test_generate_minutes_output_passes_validator_with_example_transcript() -> None:
    """
    Smoke: se o LLM devolver o exemplo, validate_minutes deve passar
    quando o transcript é o FEW_SHOT_EXAMPLE_TRANSCRIPT.
    """
    from app.services.minutes.prompts import FEW_SHOT_EXAMPLE_TRANSCRIPT

    router = _router_with_payload(FEW_SHOT_EXAMPLE_MINUTES)
    result = await generate_minutes(router, FEW_SHOT_EXAMPLE_TRANSCRIPT)
    report = validate_minutes(result.minutes, FEW_SHOT_EXAMPLE_TRANSCRIPT)
    assert report.is_valid
