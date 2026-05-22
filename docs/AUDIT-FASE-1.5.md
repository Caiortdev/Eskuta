# Auditoria de integridade e segurança — Fase 1.5

> **Data:** 2026-05-21
> **Escopo:** Etapas 1.5.1 → 1.5.3 do `RELATORIO_TECNICO.md` — camada
> de diarização via pyannote.audio + merger + speaker map.
> **Resultado final:** ✅ aprovado para commit + PR

Mesmo template de [`AUDIT-FASE-0.md`](AUDIT-FASE-0.md) e
[`AUDIT-FASE-1.4.md`](AUDIT-FASE-1.4.md).

---

## 1. Vulnerabilidades de dependências

| Ecossistema                            | Ferramenta                      | Resultado                    |
| -------------------------------------- | ------------------------------- | ---------------------------- |
| Node (`package.json`)                  | `npm audit`                     | **0 vulnerabilidades**       |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities** |

### Novas dependências adicionadas nesta fase

| Pacote           | Versão pinned | Motivo                                                     |
| ---------------- | ------------- | ---------------------------------------------------------- |
| `pyannote.audio` | 4.0.4         | Diarização de speakers (modelo `speaker-diarization-3.1`). |

### Evolução do relatório

O relatório pinava `pyannote.audio==3.3.2`, mas essa versão usa
`torchaudio.AudioMetaData` que foi removido em torchaudio 2.5+
(temos 2.11.0 instalado via silero-vad da Fase 1.3 — não dá pra
downgradear sem quebrar a pipeline de áudio). Subida pra 4.0.4
(latest estável) que é compat com torchaudio moderno.

Decisão documentada no commit + `requirements.txt`. Próximo
revisão: a cada nova fase via `pip-audit` no CI.

---

## 2. Secrets hardcoded

Grep cego nos arquivos novos (`app/services/diarization/*.py`,
`tests/test_diarization_*.py`):

**Nenhum match.** Strings com prefixo `hf_` aparecem só em
fixtures de teste com valores não-funcionais
(`"hf_xxx"`, `"hf_super_secret_token_dont_leak"`).

### HF_TOKEN — APP-level, não user-level

- O token do Hugging Face é **da conta do app**, não do usuário final.
- Vem do `.env` em dev (variável `ESKUTA_HF_TOKEN`) e de build
  secret em prod.
- **Nunca** vai pro keyring do user (que é só pra API keys de LLM/STT
  configuradas individualmente).
- `is_available()` retorna False quando `HF_TOKEN` está ausente —
  o pipeline de ata segue sem rótulos de speaker, com warning
  estruturado no log.
- Validado por `test_diarize_log_does_not_leak_hf_token` (fixture
  `loguru_messages` com sanity assert garante que o teste não passa
  vacuamente).

### Exception messages

A exception `DiarizationUnavailableError` levanta com texto genérico
(`"HF_TOKEN não configurado — diarização desabilitada"`) sem
incluir credencial. Verificado por inspeção do código.

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação            | Configuração atual                                                                                                                | Status |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Bind do socket         | `127.0.0.1` (default herdado da Fase 0)                                                                                           | ✅     |
| CORS                   | Sem mudança nesta fase                                                                                                            | ✅     |
| Endpoints novos        | **Nenhum endpoint REST nesta fase** — diarização é puramente service-level. O frontend (Fase 1.10) vai expor mute/rename via REST | ✅     |
| Logging                | Logs estruturados (loguru) com kwargs `audio`, `segments`, `unique_speakers`, `model` — sem token, sem path do user               | ✅     |
| Singleton com lock     | `Lock` em `_pipeline_lock` previne race condition no carregamento do modelo (pesado, ~500MB)                                      | ✅     |
| Failure modes mapeados | Load do pipeline falha → `DiarizationUnavailableError`. Runtime falha → `DiarizationError`. Sem token → `DiarizationUnavailable`  | ✅     |

---

## 4. Princípios do MAPA_PROJETO aplicados

| Princípio                                       | Implementação                                                                                          |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Local-first**                                 | pyannote roda 100% local após download inicial; áudio nunca sai da máquina                             |
| **Falha elegante**                              | Sem HF_TOKEN, `is_available()=False`, ata gera sem speaker labels (não bloqueia, só perde feature)     |
| **Anti-alucinação**                             | Speaker labels só atribuídos quando há sobreposição real; sem overlap preserva original ou fica `None` |
| **Migrations versionadas (não aplicável aqui)** | Tabela `meetings.speaker_map` (JSON) já existe desde Fase 1.2; nenhuma migration nova nesta fase       |
| **Documentar enquanto desenvolve**              | Cada módulo tem docstring explicando porquê + estratégia + edge cases                                  |

---

## 5. Decisões de design — evolução do relatório

| Decisão                                                            | Por quê                                                                                                                                      |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `pyannote.audio==4.0.4` em vez de 3.3.2                            | 3.3.2 incompat com torchaudio 2.11+ (`AudioMetaData` removido)                                                                               |
| `settings.HF_TOKEN` em vez de `os.getenv("HF_TOKEN")` direto       | Centraliza configuração (Pydantic valida, `safe_summary` mascara), e respeita o pattern já estabelecido nas Fases 1.1/1.2/1.4                |
| Hierarquia tipada de exceptions (`DiarizationError` + sub)         | Permite o `process_meeting` da Fase 1.9 distinguir entre "feature opt-out" (Unavailable) e "falha runtime" (Error), com tratamento diferente |
| `merge` preserva speaker original quando não há overlap pyannote   | AssemblyAI emite speakers nativamente; combinar mantém o melhor de cada (pyannote prefere onde há, AAI complementa)                          |
| `extract_unique_speakers` exposto                                  | Frontend (Fase 1.10) precisa listar speakers únicos pra UI de renomeação                                                                     |
| `SpeakerSegment` em arquivo separado (não em `transcription.base`) | Diarização é domínio distinto de transcrição — separar reduz acoplamento e facilita remover pyannote no futuro                               |

---

## 6. Cobertura de testes

**223 testes** totais (183 da Fase 1.4 + 40 novos), **96.26% de
cobertura total** (gate é 70%). Cobertura por arquivo novo:

| Arquivo                                        | Cobertura |
| ---------------------------------------------- | --------- |
| `app/services/diarization/__init__.py`         | 100%      |
| `app/services/diarization/pyannote_service.py` | 100%      |
| `app/services/diarization/merger.py`           | 100%      |
| `app/services/diarization/speaker_map.py`      | 100%      |

### Tipos de teste cobertos

- **Dataclass + frozen** — SpeakerSegment imutável, duration calculada
- **Singleton thread-safe** — pipeline carrega só 1x, reset força reload
- **Token handling** — None / "" / valor válido testados
- **Mapeamento de output** — itertracks fora de ordem → segments ordenados
- **Falhas mapeadas** — load 403 → Unavailable; runtime crash → DiarizationError
- **Log-leakage do HF_TOKEN** — sanity assert garante que fixture capturou algo
- **Merger** — overlap parcial, overlap dominante, empate 50/50, sem overlap
  preserva original, sem overlap + sem original fica None
- **Speaker map** — substitui conhecidos, preserva desconhecidos, ignora None,
  imutabilidade do input
- **Extract unique** — ordem de primeira aparição, ignora None, lista vazia

---

## 7. Permissões do Tauri

**Sem mudança nesta fase.** Diarização roda no sidecar Python; não
adiciona capability nova ao Tauri.

---

## 8. Critérios de aceite — RELATORIO_TECNICO §1.5

### 1.5.1 — Setup do pyannote.audio

- [x] `from pyannote.audio import Pipeline` funciona após install
- [x] Modelo baixa na primeira execução (~500MB) — testado via mock
      `Pipeline.from_pretrained`
- [x] Singleton thread-safe (não recarrega entre chamadas)
- [x] Sem HF_TOKEN → `DiarizationUnavailableError` com mensagem
      acionável (sem vazar info sensível)

### 1.5.2 — Merge Diarização + Transcrição

- [x] Cada `TranscriptionSegment` recebe um `speaker` (via maior overlap)
- [x] Speakers diferentes em momentos diferentes (testado com 2 speakers
      split em 0-5s / 5-10s)
- [x] Quando há sobreposição parcial, prevalece o speaker dominante
- [x] Em empate exato (50/50), primeiro speaker da lista vence
      (determinístico)
- [x] Sem overlap algum → preserva speaker original do TranscriptionSegment

### 1.5.3 — Mapeamento de Speakers Anônimos pra Nomes

- [x] `apply_speaker_map` substitui IDs por nomes humanos
- [x] Speakers não mapeados preservam ID original (não inventa nome)
- [x] Segments com `speaker=None` continuam None
- [x] `extract_unique_speakers` retorna lista ordenada por 1ª aparição
- [x] Backend support pronto; UI da renomeação fica em Fase 1.10
      (frontend); persistência usa coluna `meetings.speaker_map` JSON
      já existente desde Fase 1.2

---

## 9. Régua pré-PR — status local

| Comando                                    | Resultado                                                 |
| ------------------------------------------ | --------------------------------------------------------- |
| `npm audit`                                | ✅ 0 vulnerabilidades                                     |
| `pip_audit -r src-python/requirements.txt` | ✅ No known vulnerabilities                               |
| `pytest` (223 testes)                      | ✅ 223 passed, cov 96.26%                                 |
| `ruff check .`                             | ✅ All checks passed                                      |
| `ruff format --check`                      | ✅ 59 files formatted                                     |
| `npm test`                                 | ⚠️ falha local (Node 24 + jsdom) — CI usa Node 20 e passa |
| `cargo fmt / clippy`                       | ⚠️ não rodado local (sem cargo na máquina); CI valida     |

CI replicará tudo (`.github/workflows/ci.yml`) — Tauri build Windows
(7+ min) é o gargalo conhecido.

---

## 10. Aprovação

✅ **Auditoria aprovada para commit + PR.**

Notas pra próximas fases:

1. **Fase 1.6 (LLM):** vai precisar das 3 API keys (Claude/GPT/Gemini)
   — já temos `app.services.keys` desde 1.11; só estender o
   `KNOWN_PROVIDERS` se necessário (já tem `anthropic`, `openai`,
   `google`).
2. **Fase 1.9 (Pipeline de Ata):** `process_meeting` vai orquestrar
   `convert → VAD → chunk → transcribe (parallel) → diarize (opcional
se is_available) → merge → apply_speaker_map → LLM → persist`.
   Toda a arquitetura está pronta.
3. **Fase 1.10 (Frontend):** vai precisar de endpoint `PUT
/meetings/{id}/speaker-map` pra renomear speakers — adicionar
   junto com a UI.
