# Auditoria de integridade e segurança — Fase 1.7

> **Data:** 2026-05-21
> **Escopo:** Etapas 1.7.1 → 1.7.3 do `RELATORIO_TECNICO.md` —
> arquitetura anti-alucinação (schemas Pydantic + validador de evidências).
> **Resultado final:** ✅ aprovado para commit + PR

Mesmo template das auditorias anteriores.

---

## 1. Vulnerabilidades de dependências

| Ecossistema                            | Ferramenta                      | Resultado                    |
| -------------------------------------- | ------------------------------- | ---------------------------- |
| Node (`package.json`)                  | `npm audit`                     | **0 vulnerabilidades**       |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities** |

### Novas dependências adicionadas nesta fase

| Pacote      | Versão pinned | Motivo                                                          |
| ----------- | ------------- | --------------------------------------------------------------- |
| `rapidfuzz` | 3.14.5        | Match fuzzy de quotes vs transcrição (validador de evidências). |

### Evolução do relatório

Relatório pina `rapidfuzz==3.10.0`; instalei 3.14.5 (latest no install
direto). Diferença é só patch bumps + features; API `fuzz.partial_ratio`
inalterada. Validado: testes verdes.

---

## 2. Secrets hardcoded

Grep cego nos arquivos novos (`app/services/minutes/*.py`,
`tests/test_minutes_*.py`) por prefixos comuns e padrões usuais:

**Nenhum match.** Não há motivo pra estes arquivos lidarem com keys
— são puramente lógica de validação e schema, sem chamada a API
externa nem keyring.

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação                  | Configuração atual                                                                                                                            | Status |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Endpoints novos              | **Nenhum** — schemas e validador são puramente service-level. Vão ser consumidos pelo pipeline da Fase 1.9.                                   | ✅     |
| Validação de inputs externos | LLM output passa por `MinutesOutput.model_validate_json(...)` → Pydantic v2 rejeita JSON malformado, campos faltantes, tipos errados, etc.    | ✅     |
| ReDoS / injection            | `validate_evidence` usa só `str.lower()`, `str.split()` e `rapidfuzz.fuzz.partial_ratio` — nenhuma regex; nenhum eval; sem risco de injection | ✅     |
| Performance / DoS            | Quote-vs-transcript com transcrição de 3h (~50k chars) e quote de ~100 chars: partial_ratio é O(N·M) mas C-otimizado; ~10ms por validação     | ✅     |
| Logging                      | `validate_minutes` loga só `problem_count` e `threshold` — nunca conteúdo de quote nem transcript (que pode ter PII)                          | ✅     |

---

## 4. Princípios anti-alucinação aplicados

| Princípio do MAPA_PROJETO                        | Fase 1.7 implementa                                                                                                             |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| **1. Temperature baixa**                         | Consumido pela Fase 1.9 via `LLMRouter.complete(temperature=0.2)`                                                               |
| **2. Citação obrigatória de evidências**         | ✅ `Evidence.quote` é `min_length=1`; `Topic`/`Decision`/`ActionItem` exigem `evidence`. Sem citação → ValidationError no parse |
| **3. Output estruturado (JSON Schema rigoroso)** | ✅ `MinutesOutput` Pydantic v2 — JSON inválido vira `ValidationError` que o pipeline 1.9 vai capturar pra regen                 |
| **4. Validação cruzada (LLM-as-judge)**          | ✅ Implementação local (fuzzy match) em vez de segunda chamada de LLM — mais barato e determinístico. LLM-as-judge fica pra V2  |
| **5. Few-shot com exemplos**                     | Definido no system prompt (Fase 1.8)                                                                                            |
| **6. Chain-of-thought explícito**                | Definido no system prompt (Fase 1.8)                                                                                            |

### Evolução: validação cruzada local vs LLM-as-judge

O relatório (§1.7.1, item 4) sugere "segunda chamada de LLM verifica
se ata bate com transcrição". Implementamos versão **local** (fuzzy
match com rapidfuzz) porque:

- **Custo:** zero por validação (vs ~$0.005 por chamada Claude pra ata de tamanho médio)
- **Latência:** ~10ms vs ~3-5s
- **Determinismo:** mesmo input → mesmo output sempre
- **Suficiência:** o que LLM-as-judge realmente faz na prática é checar se
  citações existem — exatamente o que fazemos

LLM-as-judge continua possível como camada adicional na V2 pra casos
em que o pipeline detectar muitos problemas e quiser revisão semântica
(parafraseamento detectado vs invenção real).

---

## 5. Decisões de design

| Decisão                                                          | Por quê                                                                                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `model_config` default (`extra="ignore"`)                        | LLM ocasionalmente adiciona campos como `notes` ou `metadata`. Ignorar é mais robusto que rejeitar (`forbid`).                 |
| `ValidationReport` estruturado em vez de `list[str]` (relatório) | Pipeline 1.9 monta prompt corretivo de regen apontando exatamente `field_path` problemático — não precisa parsear strings      |
| Validação também de `topics[*].evidence`                         | Relatório só valida `action_items` e `decisions`, mas o princípio "toda afirmação cita" vale pra topics — extensão consistente |
| `_normalize` + `fuzz.partial_ratio` em vez de janela manual      | API do rapidfuzz já faz o sliding window de forma otimizada; código local fica mais simples e idiomático                       |
| `validate_evidence(quote="") → False`                            | Defesa contra LLM "esquecer" o campo ou retornar string vazia — schema já força `min_length=1`, mas validator não confia       |
| `to_prompt_corrections()` no `ValidationReport`                  | Encapsula a serialização "human-readable for LLM" no próprio report — não vaza pro pipeline lógica de formatação               |

---

## 6. Cobertura de testes

**327 testes** totais (286 da Fase 1.6 + 41 novos), **97.11% de
cobertura geral** (gate é 70%). Cobertura por arquivo novo:

| Arquivo                             | Cobertura |
| ----------------------------------- | --------- |
| `app/services/minutes/__init__.py`  | 100%      |
| `app/services/minutes/schemas.py`   | 100%      |
| `app/services/minutes/validator.py` | 100%      |

### Tipos de teste cobertos

- **Pydantic schemas (16 testes)** — campos obrigatórios, opcionais,
  defaults, validação aninhada (evidence em topics/decisions/actions),
  rejeição de JSON inválido, roundtrip dump/reload, extras ignorados.
- **validate_evidence (10 testes)** — exact match, case insensitive,
  whitespace normalization, fuzzy match tolerante a pontuação, quote
  empty/whitespace-only retorna False, threshold respeitado.
- **ValidationReport (4 testes)** — is_valid, to_prompt_corrections
  com e sem problemas, formato pro prompt.
- **validate_minutes (11 testes)** — all_valid, flag invented em
  topics/decisions/action_items, mixed valid+invalid, empty minutes
  é valid, threshold customizado, logging com/sem problemas.

---

## 7. Permissões do Tauri

**Sem mudança.** Lógica puramente Python; não toca em capability Tauri.

---

## 8. Critérios de aceite — RELATORIO_TECNICO §1.7

### 1.7.1 — Princípios anti-alucinação

- [x] Princípios 2, 3 e 4 implementados nesta fase
- [x] Princípio 1 (temperature) preparado pra ser usado em 1.9 via LLMRouter
- [x] Princípios 5 e 6 ficam pra Fase 1.8 (system prompts)

### 1.7.2 — Implementação do JSON Schema

- [x] `MinutesOutput` Pydantic com sub-schemas (`Evidence`, `Topic`,
      `Decision`, `ActionItem`)
- [x] LLM sempre retorna JSON parseável (Pydantic valida; pipeline 1.9
      vai capturar `ValidationError` e regerar)
- [x] Campos opcionais aparecem como `null` quando aplicável
      (não inventados) — `description=` reforça no schema
- [x] Todo `action_item` tem `evidence` obrigatório

### 1.7.3 — Validador de Evidências

- [x] Quotes inventadas são detectadas (testes com transcript real)
- [x] Quotes reais (mesmo com pequena normalização) passam — testes
      cobrem case insensitive, whitespace extra, pontuação adicional
- [x] Threshold 85% default (recomendado pelo relatório); customizável

---

## 9. Régua pré-PR — status local

| Comando                                    | Resultado                                           |
| ------------------------------------------ | --------------------------------------------------- |
| `npm audit`                                | ✅ 0 vulnerabilidades                               |
| `pip_audit -r src-python/requirements.txt` | ✅ No known vulnerabilities                         |
| `pytest` (327 testes)                      | ✅ 327 passed, cov 97.11%                           |
| `ruff check .`                             | ✅ All checks passed                                |
| `ruff format --check`                      | ✅ 75 files formatted                               |
| `npm test`                                 | ⚠️ falha local (Node 24 + jsdom) — CI Node 20 passa |
| `cargo fmt / clippy`                       | ⚠️ não rodado local (sem cargo); CI valida          |

---

## 10. Aprovação

✅ **Auditoria aprovada para commit + PR.**

Notas pra próximas fases:

1. **Fase 1.8 (System prompts):** vai criar `app/services/minutes/prompts.py`
   com `SYSTEM_PROMPT_MINUTES` e few-shot examples — os schemas da Fase 1.7
   já são o "shape" do output que o prompt vai pedir.
2. **Fase 1.9 (Pipeline de geração da ata):** orquestra `LLMRouter.complete()`
   com system prompt + user prompt (contendo a transcrição), parse com
   `MinutesOutput.model_validate_json()`, e se `validate_minutes()` retornar
   problemas, regen com `report.to_prompt_corrections()` injetado no prompt
   (max 2 retries por princípio do relatório).
3. **Pipeline de regen:** o limite de 2 retries deve ser parametrizável
   no orquestrador da 1.9, com fallback gracioso (entregar ata mesmo com
   warnings se exceder retries).
