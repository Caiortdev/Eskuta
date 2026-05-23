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
    purge_invalid_items,
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


# ============================================================
# purge_invalid_items — última defesa anti-alucinação
# ============================================================


def test_purge_keeps_only_valid_items() -> None:
    """Items com evidence inválida são REMOVIDOS, items válidos ficam."""
    m = _minutes(
        topics=[
            Topic(title="Valido", summary="ok", evidence=_evidence("projeto Alpha")),
            Topic(title="Inventado", summary="nope", evidence=_evidence("nada disso")),
        ],
        decisions=[
            Decision(description="OK", evidence=_evidence("eu falo com ele até sexta")),
            Decision(description="Hallucinated", evidence=_evidence("xyz fake")),
        ],
        action_items=[
            ActionItem(description="OK", evidence=_evidence("Eu mando email pra ele hoje")),
            ActionItem(description="Fake", evidence=_evidence("aaaa zzzzz")),
        ],
    )
    purged, report = purge_invalid_items(m, TRANSCRIPT)
    assert len(purged.topics) == 1 and purged.topics[0].title == "Valido"
    assert len(purged.decisions) == 1 and purged.decisions[0].description == "OK"
    assert len(purged.action_items) == 1 and purged.action_items[0].description == "OK"
    assert report.removed_topics == 1
    assert report.removed_decisions == 1
    assert report.removed_action_items == 1
    assert report.total_removed == 3


def test_purge_no_op_when_all_valid() -> None:
    m = _minutes(
        action_items=[
            ActionItem(description="OK", evidence=_evidence("eu falo com ele até sexta")),
        ],
    )
    purged, report = purge_invalid_items(m, TRANSCRIPT)
    assert len(purged.action_items) == 1
    assert report.total_removed == 0


def test_purge_preserves_other_fields() -> None:
    """title, executive_summary, participants, open_questions ficam intactos."""
    m = _minutes()
    m_dict = m.model_dump()
    m_dict["title"] = "Reunião importante"
    m_dict["executive_summary"] = "Resumo da reunião."
    m_dict["participants"] = ["João", "Maria"]
    m_dict["open_questions"] = ["Sobrou X?"]
    m = MinutesOutput.model_validate(m_dict)

    purged, _ = purge_invalid_items(m, TRANSCRIPT)
    assert purged.title == "Reunião importante"
    assert purged.executive_summary == "Resumo da reunião."
    assert purged.participants == ["João", "Maria"]
    assert purged.open_questions == ["Sobrou X?"]


def test_purge_removes_few_shot_leak_scenario() -> None:
    """
    Cenário REAL que motivou o purge: o LLM vazou o exemplo do few-shot
    numa reunião que NÃO menciona Projeto Alpha. O purge tem que remover.
    """
    real_transcript = (
        "Renan: A gente precisa discutir o plano de governo. "
        "Junior: Concordo, prioridade é segurança pública."
    )
    m = _minutes(
        decisions=[
            # Item LEGÍTIMO da reunião
            Decision(
                description="Foco em segurança pública",
                evidence=_evidence("prioridade é segurança pública"),
            ),
            # Item LEAKED do few-shot
            Decision(
                description="Adiar o projeto Alpha para a próxima sprint",
                evidence=_evidence("eu acho que a gente deveria adiar pra próxima sprint"),
            ),
        ],
    )
    purged, report = purge_invalid_items(m, real_transcript)
    assert len(purged.decisions) == 1
    assert purged.decisions[0].description == "Foco em segurança pública"
    assert report.removed_decisions == 1
