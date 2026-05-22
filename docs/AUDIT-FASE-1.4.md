# Auditoria de integridade e segurança — Fase 1.4

> **Data:** 2026-05-21
> **Escopo:** Etapas 1.4.1 → 1.4.3 do `RELATORIO_TECNICO.md` — camada
> de transcrição com fallback Groq → AssemblyAI.
> **Resultado final:** ✅ aprovado para commit + PR

Este documento segue o mesmo template de [`AUDIT-FASE-0.md`](AUDIT-FASE-0.md).
Auditoria executada como parte do fluxo "tests → audit → PR" da Fase 1.4.

---

## 1. Vulnerabilidades de dependências

| Ecossistema                            | Ferramenta                      | Resultado                    |
| -------------------------------------- | ------------------------------- | ---------------------------- |
| Node (`package.json`)                  | `npm audit`                     | **0 vulnerabilidades**       |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities** |

### Novas dependências adicionadas nesta fase

| Pacote       | Versão pinned | Motivo                                                           |
| ------------ | ------------- | ---------------------------------------------------------------- |
| `groq`       | 1.2.0         | SDK oficial pro Groq Whisper Large v3 Turbo (provider primário). |
| `assemblyai` | 0.64.3        | SDK oficial do fallback (modelo Universal, suporta pt-BR).       |

Ambas são SDKs oficiais (Groq Inc. e AssemblyAI Inc.), com publishers
verificados no PyPI. Nenhuma puxa dependência transitiva com CVE
conhecida (verificado via `pip-audit`).

---

## 2. Secrets hardcoded

Grep cego de prefixos comuns (`sk-…`, `gsk_…`, `AIza…`, `ghp_…`,
`xoxb-…`) e de padrões `KEY|SECRET|PASSWORD|TOKEN = "<16+ chars>"`
nos arquivos novos (`app/services/transcription/*.py`,
`app/api/transcription.py`, `tests/test_transcription_*.py`,
`tests/test_api_transcription.py`):

**Nenhum match.** As únicas strings com prefixos sk-/gsk- estão em
**fixtures de teste** com valores não-funcionais (`"sk-test"`,
`"groq-do-not-leak-12345"`) usados pra exercer o caminho de
log-leakage e mock de keyring.

### Garantias de design

- **API keys nunca em log.** Validado por testes positivos
  (`test_transcribe_log_does_not_leak_api_key` no Groq e AssemblyAI)
  usando a nova fixture `loguru_messages` (captura sink Loguru
  real, com formato que inclui kwargs estruturados — não passa
  vacuamente). Sanity assert garante que a fixture capturou ≥1
  mensagem antes de assertar que o secret não está nela.
- **API keys vêm exclusivamente do keyring** (via
  `app.services.keys.get_api_key`). Nunca de `.env`, nunca
  hardcoded, nunca passadas como request body do FastAPI.
- **Exception messages dos providers nunca incluem chave.** Os
  SDKs (groq, assemblyai) levantam exceções que mencionam o tipo
  de erro, não credenciais — verificado em
  `test_transcribe_maps_*_exception`.

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação              | Configuração atual                                                                                                          | Status                         |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| Bind do socket           | `127.0.0.1` (default herdado da Fase 0)                                                                                     | ✅                             |
| CORS                     | Sem mudança — lista explícita herdada (`localhost:1420`, `tauri.localhost`, etc.); sem wildcard                             | ✅                             |
| Validação de inputs      | `StartTranscriptionRequest` exige `meeting_id` com `min_length=1, max_length=64`. 422 testado pra empty/missing             | ✅                             |
| Logging de payloads      | Endpoints novos NÃO logam corpo. Providers logam só metadados (duration, segments, elapsed) — nunca conteúdo de transcrição | ✅                             |
| Background tasks         | `process_meeting` (stub Fase 1.9) roda em BackgroundTask do FastAPI, sem queue persistente — não persiste estado            | ✅ (intencional pra esta fase) |
| Rate limiting de chamada | Router respeita `Retry-After` do Groq quando presente; backoff exponencial default 1s→2s→4s, max 3 tentativas por provider  | ✅                             |
| Paralelização            | `transcribe_chunks_parallel` usa `asyncio.Semaphore(settings.MAX_PARALLEL_CHUNKS=4)` — respeita rate limit free tier        | ✅                             |

### Endpoint novo

`POST /transcribe/start` — agendamento de `process_meeting` via
`BackgroundTasks` conforme RELATORIO_TECNICO §1.4.2. O handler
`process_meeting` é **stub** nesta fase (loga warning, não persiste
nada). A orquestração real (load meeting → chunk → transcribe →
persist) entra na Fase 1.9 (`Pipeline de Geração da Ata`).

Decisão documentada: implementamos o contrato do endpoint agora
porque (a) o relatório especifica explicitamente assim, e (b) ter o
endpoint definido cedo permite o frontend (Fase 1.10) começar a
integrar sem esperar 1.9.

---

## 4. Anti-alucinação (princípio do MAPA_PROJETO)

| Garantia                                  | Implementação                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `temperature=0.0` no Groq                 | Hard-coded em `GroqProvider.transcribe` — testado em `test_transcribe_passes_correct_args_to_sdk`          |
| `language="pt"` explícito                 | Default no `transcribe()`, propagado pros SDKs — não deixa o modelo "adivinhar" a língua                   |
| Timestamps absolutos preservados no merge | `merge_chunk_transcriptions` ajusta `chunk.start_sec + seg.start_sec` — testado contra 2 chunks com offset |
| Segments com confidence preservada        | Tanto Groq (`avg_logprob`) quanto AssemblyAI (`confidence`) propagam o sinal pra rastreio downstream       |

---

## 5. Lock files e reprodutibilidade

| Arquivo                       | Estado                                         |
| ----------------------------- | ---------------------------------------------- |
| `src-python/requirements.txt` | ✅ pinned: `groq==1.2.0`, `assemblyai==0.64.3` |
| `package-lock.json`           | sem mudança intencional nesta fase             |
| `src-tauri/Cargo.lock`        | sem mudança nesta fase                         |

---

## 6. Cobertura de testes

**183 testes** totais (103 herdados + 80 novos), **94% de cobertura
total** (gate é 70%). Cobertura por arquivo novo:

| Arquivo                                             | Cobertura |
| --------------------------------------------------- | --------- |
| `app/services/transcription/__init__.py`            | 100%      |
| `app/services/transcription/base.py`                | 94%       |
| `app/services/transcription/groq_provider.py`       | 100%      |
| `app/services/transcription/assemblyai_provider.py` | 97%       |
| `app/services/transcription/router.py`              | 100%      |
| `app/services/transcription/parallel.py`            | 99%       |
| `app/api/transcription.py`                          | 100%      |

### Tipos de teste cobertos

- **Unidade** — cada provider mockado via `unittest.mock` (sem rede)
- **Mapeamento de erros** — exceções dos SDKs viram nossas exceptions tipadas
- **Backoff / fallback** — `asyncio.sleep` mockado, intervalos verificados
- **Concorrência** — provider com contador de inflight valida o semáforo
- **Merge de timestamps** — chunks com offsets diferentes, asserts em segs absolutos
- **Robustez** — chunk com exception não cancela os outros; merge pula falhas
- **Log-leakage** — fixture `loguru_messages` valida que API key NÃO aparece em log
- **Integração API** — `httpx.ASGITransport` chama o endpoint sem subir uvicorn

---

## 7. Permissões do Tauri

**Sem mudança nesta fase.** A camada de transcrição é puramente do
sidecar Python; não adiciona capability nova ao Tauri.

---

## 8. Critérios de aceite — RELATORIO_TECNICO §1.4

### 1.4.1 — Padrão Adapter pra providers

- [x] Ambos providers implementam a mesma interface (`TranscriptionProvider`)
- [x] Resultado normalizado idêntico independente do provider
- [x] `is_available()` retorna `False` quando API key faltando
- [x] Evolução: dataclass renomeado `TranscriptionSegment` (era
      `TranscriptSegment` no relatório) pra não colidir com o model
      SQLAlchemy `app.models.transcript.TranscriptSegment` da Fase 1.2.
      Documentado no docstring de `base.py`.

### 1.4.2 — Router com Fallback Inteligente

- [x] Com Groq disponível, sempre tenta Groq primeiro (ordem via `settings.PREFERRED_STT`)
- [x] Quando Groq retorna 429, retry com backoff exponencial (1s, 2s, 4s)
- [x] Se Groq falhar 3x, cai pra AssemblyAI
- [x] Resultado final guarda qual provider foi usado (`provider_used`)
- [x] Logs estruturados deixam claro o que aconteceu em cada tentativa
- [x] Evolução: a exception `AllProvidersFailedError` carrega um dict
      `failures` com motivo por provider — útil pra resposta de erro
      do endpoint na Fase 1.9 sem expor stacktrace.

### 1.4.3 — Paralelização de chunks

- [x] Semáforo respeitado (verificado por `_CountingProvider` com
      `peak_inflight`)
- [x] Timestamps absolutos batem com o áudio original
- [x] Falha em UM chunk não cancela os outros (`return_exceptions=True`)
- [x] `merge_chunk_transcriptions` exposto separadamente pra que a
      orquestração da Fase 1.9 controle o ponto de merge

---

## 9. Régua pré-PR — status local

| Comando                                    | Resultado                                                              |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `npm audit`                                | ✅ 0 vulnerabilidades                                                  |
| `pip_audit -r src-python/requirements.txt` | ✅ No known vulnerabilities                                            |
| `pytest` (183 testes)                      | ✅ 183 passed, cov 93.67%                                              |
| `ruff check .`                             | ✅ All checks passed                                                   |
| `ruff format --check`                      | ✅ 52 files already formatted                                          |
| `npm test`                                 | ⚠️ falha local por Node 24 + jsdom — CI usa Node 20 e passa            |
| `cargo fmt / clippy`                       | ⚠️ não rodado local (Rust não instalado nesta máquina); CI valida      |
| Pre-commit hooks                           | ✅ ruff, prettier, eslint passaram; cargo-fmt pulou por ausência local |

Os 2 itens marcados ⚠️ são limitações do ambiente local; ambos rodam
no CI (`.github/workflows/ci.yml` jobs "Frontend (typecheck + test)"
em Node 20 e "Rust (fmt + clippy)" em ubuntu-latest com rust stable).

---

## 10. Aprovação

✅ **Auditoria aprovada para commit + PR.**

Notas pra próxima fase:

1. **Fase 1.5 (Diarização):** vai precisar de `HF_TOKEN` da
   organização — adicionar nota no setup quando chegar lá.
2. **Fase 1.9 (Pipeline de Ata):** vai implementar `process_meeting`
   de verdade — substituir o stub atual, manter o contrato do endpoint.
3. **Fase 1.10 (Frontend):** o endpoint `POST /transcribe/start` já
   está disponível pra integração mesmo com o stub — o frontend pode
   adiantar o fluxo de upload + start.
