# Auditoria de integridade e segurança — Fase 1.6

> **Data:** 2026-05-21
> **Escopo:** Etapas 1.6.1 → 1.6.2 do `RELATORIO_TECNICO.md` — camada
> de LLM (Claude/GPT/Gemini) com adapter pattern + router.
> **Resultado final:** ✅ aprovado para commit + PR

Mesmo template das auditorias anteriores.

---

## 1. Vulnerabilidades de dependências

| Ecossistema                            | Ferramenta                      | Resultado                    |
| -------------------------------------- | ------------------------------- | ---------------------------- |
| Node (`package.json`)                  | `npm audit`                     | **0 vulnerabilidades**       |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities** |

### Novas dependências adicionadas nesta fase

| Pacote         | Versão pinned | Motivo                                                                            |
| -------------- | ------------- | --------------------------------------------------------------------------------- |
| `anthropic`    | 0.104.0       | SDK oficial pro Claude (Anthropic).                                               |
| `openai`       | 2.38.0        | SDK oficial pro GPT (OpenAI).                                                     |
| `google-genai` | 2.5.0         | SDK oficial pro Gemini (Google) — substitui `google-generativeai` **deprecated**. |

### Mudanças transitivas pinadas

| Pacote  | Antes  | Depois | Motivo                                                                 |
| ------- | ------ | ------ | ---------------------------------------------------------------------- |
| `httpx` | 0.27.0 | 0.28.1 | `google-genai` requer `>=0.28`. Validado: 286 testes continuam verdes. |

### Evolução do relatório

O `RELATORIO_TECNICO` lista `google-generativeai` como SDK do Gemini.
Esse pacote está **deprecated desde 2024** (o próprio import emite
warning apontando pra repo deprecated). Substituído por `google-genai`
(API moderna, single client `genai.Client()`, suporte async via
`.aio`). Mudança documentada no commit + requirements.txt.

---

## 2. Secrets hardcoded

Grep cego nos arquivos novos (`app/services/llm/*.py`,
`tests/test_llm_*.py`) por prefixos comuns (`sk-`, `sk-ant-`, `AIza`,
etc.) e padrões `KEY|SECRET|PASSWORD|TOKEN = "<16+ chars>"`:

**Nenhum match.** Strings com prefixos só em fixtures de teste com
valores não-funcionais (`"sk-test"`, `"sk-ant-test"`, `"AIza-test"`,
`"sk-ant-do-not-leak-99999"`, etc.) usados pra exercer log-leakage
e mock de keyring.

### Garantias de design

- **API keys vêm exclusivamente do keyring** (via `keys_service.get_api_key`
  com providers `"anthropic"`, `"openai"`, `"google"` da allow-list de 1.11).
- **Logs nunca contêm valor da key.** Validado por testes positivos
  em **cada** provider (`test_complete_log_does_not_leak_api_key` com
  fixture `loguru_messages` e sanity assert — não passa vacuamente).
- **Exception messages** referenciam o provider name (`"claude"`, `"gpt"`,
  `"gemini"`), nunca a chave — verificado por inspeção do código.

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação            | Configuração atual                                                                                                                                | Status |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Endpoints novos        | **Nenhum endpoint REST nesta fase** — LLM é puramente service-level. Vai ser consumido pelo `process_meeting` (1.9) e pelo frontend (1.10).       | ✅     |
| Bind do socket         | `127.0.0.1` (herdado da Fase 0)                                                                                                                   | ✅     |
| CORS                   | Sem mudança                                                                                                                                       | ✅     |
| Outbound HTTPS         | SDKs oficiais (anthropic/openai/google-genai) — todos usam `httpx` com TLS, validação de cert default                                             | ✅     |
| Logging de prompts     | **Não logamos prompts nem outputs.** Logamos só `provider`, `model`, `tokens_input`, `tokens_output`, `cost_usd`                                  | ✅     |
| Mapeamento de exceções | `LLMRateLimitError`, `LLMTimeoutError`, `LLMAPIError`, `LLMProviderUnavailableError` — hierarquia tipada igual a `TranscriptionError` da Fase 1.4 | ✅     |
| JSON mode              | Validado por teste em cada provider (Claude via system prompt, OpenAI via `response_format` nativo, Gemini via `response_mime_type`)              | ✅     |

---

## 4. Princípios anti-alucinação (preparação pra Fase 1.7)

| Princípio                               | Implementação                                                                                                     |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `temperature=0.3` default               | Baixo o suficiente pra reduzir invenção; alto o suficiente pra fluidez na escrita (vide RELATORIO_TECNICO §1.7.1) |
| JSON mode em **todos** os providers     | Necessário pra ata estruturada (schemas previsíveis em vez de prosa livre)                                        |
| Cost tracking por chamada               | `LLMResponse.cost_usd` permite enforcement de orçamento na Fase 1.9 (cortar geração se exceder limite)            |
| Provider/model preservados no resultado | `LLMResponse.provider` e `.model` rastreiam qual gerou — auditável                                                |
| Sem fallback automático de prompt       | Router troca **provider** se preferido indisponível, mas NÃO reescreve prompt — comportamento previsível          |

---

## 5. Decisões de design — evolução do relatório

| Decisão                                        | Por quê                                                                                                                        |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `google-genai` em vez de `google-generativeai` | `google-generativeai` deprecated em 2024; novo SDK tem API moderna unificada com async nativo via `.aio`                       |
| `LLMRouter` sem retry/backoff inter-provider   | Diferente do `TranscriptionRouter` (1.4) — aqui o pipeline da Fase 1.9 decide a estratégia (regen, fallback) com mais contexto |
| Hierarquia tipada de exceptions                | Permite pipeline distinguir rate limit (retry) de auth error (alerta usuário) de timeout (fallback ou regen)                   |
| `response_format` como `dict` portátil         | `{"type": "json_object"}` mapeia pra: Claude (instrução no system), OpenAI (campo nativo), Gemini (`response_mime_type`)       |
| Cost tracking pinado em constantes por arquivo | Facilita auditoria de preços; comentário "revisar trimestralmente" sinaliza manutenção                                         |
| `httpx` upgrade 0.27→0.28                      | Necessário pra `google-genai`; backward-compat verificada pelos 286 testes existentes                                          |

---

## 6. Cobertura de testes

**286 testes** totais (223 da Fase 1.5 + 63 novos), **96.92% de
cobertura geral** (gate é 70%). Cobertura por arquivo novo:

| Arquivo                               | Cobertura |
| ------------------------------------- | --------- |
| `app/services/llm/__init__.py`        | 100%      |
| `app/services/llm/base.py`            | 100%      |
| `app/services/llm/claude_provider.py` | 100%      |
| `app/services/llm/gpt_provider.py`    | 100%      |
| `app/services/llm/gemini_provider.py` | 100%      |
| `app/services/llm/router.py`          | 100%      |

### Tipos de teste cobertos

- **Dataclass + frozen** — LLMMessage e LLMResponse imutáveis
- **Exception hierarchy** — todas subclasses herdam de LLMError
- **Separação system/messages** — Claude separa, OpenAI não, Gemini vai pra config
- **Role mapping** — Gemini: assistant → model
- **JSON mode** — instrução injetada (Claude), response_format (OpenAI),
  response_mime_type (Gemini); cada caminho testado
- **Cost calculation** — assert por provider com numbers exatos via approx
- **Error mapping** — rate limit / timeout / api error → exceptions nossas
- **Robustez** — content `None`, usage_metadata `None`, múltiplos blocks
- **Custom model override** — `model=` passado por chamada
- **Log-leakage** — API key NÃO aparece em log (sanity assert garante captura)
- **Router** — preferred wins, fallback to PREFERRED_LLM, fallback to any,
  raise quando nenhum, complete delega corretamente

---

## 7. Permissões do Tauri

**Sem mudança.** LLM é puramente sidecar Python; não adiciona capability
ao Tauri.

---

## 8. Critérios de aceite — RELATORIO_TECNICO §1.6

### 1.6.1 — Interface base e adapters

- [x] Os 3 providers implementam a mesma interface (`LLMProvider`)
- [x] Cada um retorna `LLMResponse` normalizado
- [x] JSON mode funciona em todos os 3 (necessário pra ata estruturada)
- [x] Modelos default pinados: `claude-sonnet-4-5`, `gpt-4.1`, `gemini-2.5-flash`

### 1.6.2 — Router de LLM

- [x] Usuário consegue escolher provider via `preferred=` ou `settings.PREFERRED_LLM`
- [x] Se escolhido não tem key, sistema usa fallback pra outro disponível
      (com warning estruturado no log identificando preferred e picked)
- [x] Troca de provider é transparente pro resto do código (mesma `LLMResponse`)
- [x] Sem nenhum provider disponível → `LLMProviderUnavailableError` com
      mensagem acionável apontando pra endpoint `/api/keys`

---

## 9. Régua pré-PR — status local

| Comando                                    | Resultado                                                 |
| ------------------------------------------ | --------------------------------------------------------- |
| `npm audit`                                | ✅ 0 vulnerabilidades                                     |
| `pip_audit -r src-python/requirements.txt` | ✅ No known vulnerabilities                               |
| `pytest` (286 testes)                      | ✅ 286 passed, cov 96.92%                                 |
| `ruff check .`                             | ✅ All checks passed                                      |
| `ruff format --check`                      | ✅ 70 files formatted                                     |
| `npm test`                                 | ⚠️ falha local (Node 24 + jsdom) — CI usa Node 20 e passa |
| `cargo fmt / clippy`                       | ⚠️ não rodado local (sem cargo na máquina); CI valida     |

---

## 10. Aprovação

✅ **Auditoria aprovada para commit + PR.**

Notas pra próximas fases:

1. **Fase 1.7 (Arquitetura anti-alucinação):** vai estender o LLMRouter
   com técnicas como LLM-as-judge (2ª chamada validando a 1ª) e
   citation enforcement (toda afirmação na ata referencia trecho da
   transcrição). A interface atual já suporta esses padrões sem
   mudança quebrando.
2. **Fase 1.8 (System prompts):** vai definir os prompts em arquivos
   versionados (`app/services/minutes/prompts/`). LLMMessage(role="system")
   já é o input certo.
3. **Fase 1.9 (Pipeline de geração da ata):** vai orquestrar
   `transcribe → diarize → merge → speaker_map → llm.complete(json) →
validate → persist`. Toda a base está pronta.
