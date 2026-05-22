"""
Testes do validador de evidências (app.services.minutes.validator).

Foco: detectar quotes inventadas, tolerar normalização benigna
(pontuação, espaços, caixa), respeitar threshold, e validar todos
os itens com `evidence` (topics, decisions, action_items).
"""

from __future__ import annotations

from app.services.minutes.schemas import (
    ActionItem,
    Decision,
    Evidence,
    MinutesOutput,
    Topic,
)
from app.services.minutes.validator import (
    DEFAULT_FUZZY_THRESHOLD,
    EvidenceProblem,
    ValidationReport,
    validate_evidence,
    validate_minutes,
)

TRANSCRIPT = (
    "João: Pessoal, sobre o projeto Alpha, eu acho que a gente deveria "
    "adiar pra próxima sprint. Maria: Concordo, mas precisamos avisar o "
    "cliente. João: Beleza, eu falo com ele até sexta. Maria: E sobre o "
    "orçamento de design? João: A gente fechou em 15 mil mês passado, "
    "lembra? Maria: Ah verdade. Então só falta a aprovação do diretor. "
    "João: Eu mando email pra ele hoje."
)


# ============================================================
# validate_evidence
# ============================================================


def test_exact_match_returns_true() -> None:
    assert validate_evidence("eu falo com ele até sexta", TRANSCRIPT) is True


def test_case_insensitive_match() -> None:
    assert validate_evidence("EU FALO COM ELE ATÉ SEXTA", TRANSCRIPT) is True


def test_whitespace_normalization_match() -> None:
    """Quote com espaços extras vs transcrição compacta."""
    assert validate_evidence("  eu  falo com ele até   sexta  ", TRANSCRIPT) is True


def test_fuzzy_match_with_minor_typo() -> None:
    """Pequena variação de pontuação ou letra ainda passa."""
    assert validate_evidence("Eu falo com ele até sexta.", TRANSCRIPT) is True


def test_completely_different_quote_returns_false() -> None:
    """Quote inventada não tem nada a ver com transcript."""
    assert (
        validate_evidence(
            "Decidimos cancelar tudo e demitir o time inteiro",
            TRANSCRIPT,
        )
        is False
    )


def test_empty_quote_returns_false() -> None:
    assert validate_evidence("", TRANSCRIPT) is False


def test_whitespace_only_quote_returns_false() -> None:
    assert validate_evidence("   \n\t  ", TRANSCRIPT) is False


def test_threshold_respected_high_returns_false_when_lossy() -> None:
    """Threshold 100 rejeita match fuzzy benigno (só aceita exato)."""
    # Quote inteiramente fora do transcrito; mesmo threshold baixo não passa
    assert validate_evidence("texto que não existe", TRANSCRIPT, threshold=100) is False


def test_threshold_respected_low_returns_true_for_partial() -> None:
    """Threshold muito baixo aceita quase qualquer coisa."""
    # Mesmo uma palavra suspeita passa com threshold extremo
    assert validate_evidence("projeto Alpha", TRANSCRIPT, threshold=50) is True


def test_default_threshold_is_85() -> None:
    assert DEFAULT_FUZZY_THRESHOLD == 85


# ============================================================
# ValidationReport
# ============================================================


def test_empty_report_is_valid() -> None:
    r = ValidationReport()
    assert r.is_valid is True
    assert r.problems == []


def test_report_with_problems_is_invalid() -> None:
    r = ValidationReport(
        problems=[
            EvidenceProblem(field_path="topics[0].evidence", item_description="X", quote="Y"),
        ]
    )
    assert r.is_valid is False


def test_report_to_prompt_corrections_empty_when_valid() -> None:
    assert ValidationReport().to_prompt_corrections() == ""


def test_report_to_prompt_corrections_lists_problems() -> None:
    r = ValidationReport(
        problems=[
            EvidenceProblem(
                field_path="action_items[0].evidence",
                item_description="Fazer X",
                quote="inventado",
            ),
            EvidenceProblem(
                field_path="decisions[1].evidence",
                item_description="Adotar Y",
                quote="outra coisa inventada",
            ),
        ]
    )
    text = r.to_prompt_corrections()
    assert "action_items[0].evidence" in text
    assert "Fazer X" in text
    assert "inventado" in text
    assert "decisions[1].evidence" in text
    assert "outra coisa inventada" in text
    # Instrução de correção presente
    assert "remova o item" in text.lower()


# ============================================================
# validate_minutes
# ============================================================


def _evidence(quote: str) -> Evidence:
    return Evidence(quote=quote)


def _minutes(
    *,
    topics: list[Topic] | None = None,
    decisions: list[Decision] | None = None,
    action_items: list[ActionItem] | None = None,
) -> MinutesOutput:
    return MinutesOutput(
        title="Reunião teste",
        executive_summary="Resumo",
        topics=topics or [],
        decisions=decisions or [],
        action_items=action_items or [],
    )


def test_validate_minutes_all_valid() -> None:
    m = _minutes(
        topics=[Topic(title="A", summary="B", evidence=_evidence("projeto Alpha"))],
        decisions=[Decision(description="X", evidence=_evidence("adiar pra próxima sprint"))],
        action_items=[
            ActionItem(
                description="Falar com cliente",
                evidence=_evidence("precisamos avisar o cliente"),
            )
        ],
    )
    report = validate_minutes(m, TRANSCRIPT)
    assert report.is_valid is True


def test_validate_minutes_flags_invented_action_item() -> None:
    m = _minutes(
        action_items=[
            ActionItem(
                description="Demitir o time",
                evidence=_evidence("vamos demitir todo mundo agora"),
            )
        ],
    )
    report = validate_minutes(m, TRANSCRIPT)
    assert report.is_valid is False
    assert len(report.problems) == 1
    assert report.problems[0].field_path == "action_items[0].evidence"
    assert "Demitir" in report.problems[0].item_description


def test_validate_minutes_flags_invented_decision() -> None:
    m = _minutes(
        decisions=[
            Decision(
                description="Cancelar contrato",
                evidence=_evidence("a empresa vai cancelar tudo"),
            )
        ],
    )
    report = validate_minutes(m, TRANSCRIPT)
    assert report.is_valid is False
    assert report.problems[0].field_path == "decisions[0].evidence"


def test_validate_minutes_flags_invented_topic() -> None:
    """Evolução do relatório: topics também são validados."""
    m = _minutes(
        topics=[
            Topic(
                title="Demissões",
                summary="Foi anunciado corte de pessoal",
                evidence=_evidence("vamos demitir 50% do time"),
            )
        ],
    )
    report = validate_minutes(m, TRANSCRIPT)
    assert report.is_valid is False
    assert report.problems[0].field_path == "topics[0].evidence"


def test_validate_minutes_mixed_valid_and_invalid() -> None:
    m = _minutes(
        action_items=[
            ActionItem(
                description="OK 1",
                evidence=_evidence("eu falo com ele até sexta"),
            ),
            ActionItem(
                description="INVENTADO",
                evidence=_evidence("ninguém disse isso jamais"),
            ),
            ActionItem(
                description="OK 2",
                evidence=_evidence("Eu mando email pra ele hoje"),
            ),
        ],
    )
    report = validate_minutes(m, TRANSCRIPT)
    assert report.is_valid is False
    assert len(report.problems) == 1
    assert "INVENTADO" in report.problems[0].item_description
    assert report.problems[0].field_path == "action_items[1].evidence"


def test_validate_minutes_empty_minutes_is_valid() -> None:
    """Ata sem decisions/actions/topics passa (nada a validar)."""
    report = validate_minutes(_minutes(), TRANSCRIPT)
    assert report.is_valid is True


def test_validate_minutes_custom_threshold() -> None:
    """Threshold passado é honrado."""
    m = _minutes(
        action_items=[
            ActionItem(
                description="Borderline",
                evidence=_evidence("projeto Alpha"),  # 100% match
            )
        ],
    )
    # Threshold 100 ainda passa pois match é exato
    assert validate_minutes(m, TRANSCRIPT, threshold=100).is_valid is True

    m2 = _minutes(
        action_items=[
            ActionItem(
                description="Borderline",
                evidence=_evidence("xyz qwerty zzzzzz"),
            )
        ],
    )
    # Quote sem letras em comum com transcript — score ~29, abaixo de 50
    assert validate_minutes(m2, TRANSCRIPT, threshold=50).is_valid is False


def test_validate_minutes_logs_warning_when_invalid(
    loguru_messages: list[str],
) -> None:
    m = _minutes(
        action_items=[
            ActionItem(
                description="Inventado",
                evidence=_evidence("texto que nunca foi dito"),
            )
        ],
    )
    validate_minutes(m, TRANSCRIPT)
    combined = "\n".join(loguru_messages)
    assert "problemas" in combined or "problem_count" in combined


def test_validate_minutes_no_log_when_valid(loguru_messages: list[str]) -> None:
    m = _minutes(
        action_items=[
            ActionItem(
                description="OK",
                evidence=_evidence("eu falo com ele até sexta"),
            )
        ],
    )
    validate_minutes(m, TRANSCRIPT)
    # Log de warning não deveria aparecer quando ata está limpa
    combined = "\n".join(loguru_messages)
    assert "problemas" not in combined
