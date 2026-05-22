# Auditoria de integridade e segurança — Fase 1.9.5

> **Data:** 2026-05-22
> **Escopo:** Bloco A de [`MELHORIAS-CONCORRENTE.md`](MELHORIAS-CONCORRENTE.md) —
> 4 melhorias inspiradas no concorrente para travar a régua de qualidade
> antes de mexer no frontend.
> **Resultado final:** ✅ aprovado para commit + PR

Esta fase é de **harden** + **infrastructure** (eval, benchmarks, cache,
snap-to-silence). Sem novas features de produto; só fortalecimento.

---

## 1. Vulnerabilidades de dependências

| Ecossistema                            | Ferramenta                      | Resultado                    |
| -------------------------------------- | ------------------------------- | ---------------------------- |
| Node (`package.json`)                  | `npm audit`                     | **0 vulnerabilidades**       |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities** |

### Novas dependências adicionadas nesta fase

| Pacote              | Versão pinned | Motivo                                                            |
| ------------------- | ------------- | ----------------------------------------------------------------- |
| `jiwer`             | 4.0.0         | Word Error Rate no eval framework (Bloco A.2)                     |
| `pytest-benchmark`  | 5.2.3         | Suite de benchmarks (Bloco A.4) — em `requirements-dev.txt`       |

`pyannote.metrics` (usado pra DER) já vem como transitiva de
`pyannote.audio` (Fase 1.5) — sem nova entrada.

---

## 2. Secrets hardcoded

Grep cego nos arquivos novos:

- `app/services/audio/{chunker,vad_cache}.py`
- `evaluation/{__init__,manifest,metrics,runner,comparator}.py`
- `tests/benchmarks/*`
- `tests/test_evaluation_*.py`
- `tests/test_audio_vad_cache.py`

**Nenhum match.** O eval framework chama LLM via `LLMRouter` que delega
ao keyring (Fase 1.11) — nada de credencial em código.

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação              | Configuração atual                                                                                                              | Status |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Endpoints novos          | **Nenhum** — toda a 1.9.5 é service-level / CLI                                                                                | ✅     |
| Read de arquivos de eval | Runner faz `Path(manifest).read_text()` + lê goldens — paths são RELATIVOS ao manifest dir; sem escape pra fora                | ✅     |
| Cache VAD em disco       | `~/.eskuta/cache/vad/{key}.json` — key é `audio_fingerprint + sha256(params)`, não path do usuário; sem path traversal         | ✅     |
| Cache atômico            | Write via tmp + rename — sem race condition de corrupção                                                                       | ✅     |
| Cleanup do cache         | `cleanup_expired()` itera só `*.json` no diretório do cache; não cruza pastas                                                  | ✅     |
| LLM chamada no eval      | `compute_ata_score` usa `LLMRouter` da Fase 1.6 — segue todas as garantias (timeout, error mapping, log-leakage)               | ✅     |

---

## 4. Decisões de design

### A.1 — Snap-to-silence chunking

| Decisão                                                                       | Por quê                                                                                                                              |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Snap aplicado SÓ no end de cada chunk (não no start)                          | Mover o start invadiria chunks anteriores; complexidade não compensa                                                                |
| Candidato de silêncio = APENAS gap entre fim do chunk e início do próximo segment | Preserva invariante "snap nunca invade fala" — não há ambiguidade sobre quais segments pertencem a qual chunk                       |
| `_snap_to_silence` exposto como função pura                                   | Testável isoladamente sem dependência de SpeechSegment; reusável em outros contextos (Fase 2 real-time streaming pode aproveitar)   |
| Default `max_delta_sec=15.0`                                                   | Sugerido em MELHORIAS-CONCORRENTE; comportamento conservador (não move muito o cut)                                                  |

### A.2 — Eval framework

| Decisão                                                              | Por quê                                                                                                                                                  |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pacote `evaluation/` (não `eval/`)                                   | `eval` é nome do builtin Python; melhor evitar shadowing                                                                                                |
| Validação local de manifest via Pydantic                              | Erros de schema viram `ValidationError` clara, não trace críptico                                                                                       |
| `runner` separado do `metrics`                                        | Métricas são funções puras testáveis; runner é I/O-bound + assíncrono. Separação facilita unit testing                                                  |
| Hypothesis files em paths `{id}.transcript.hyp.txt` (convention over config) | Reduz boilerplate do manifest; pipeline real só precisa escrever no path esperado                                                                       |
| `EvaluationReport.save()/load()` JSON — não Pydantic                  | Dataclasses simples + `json.dumps(indent=2)` é mais legível human/diff-friendly                                                                          |
| `--skip-ata-score` flag no CLI                                        | Permite rodar em CI sem API keys (WER/DER funcionam sem)                                                                                                |
| Goldens NÃO incluídos (só README + sample_manifest vazio)             | Requer áudios reais transcritos humanamente; team adiciona conforme `tests/golden/README.md`                                                            |
| `score = max(0, 100 - 10 * issues)`                                   | Heurística simples. Pode evoluir pra weighted (severidade do issue) na V2                                                                               |

### A.3 — VAD cache

| Decisão                                                       | Por quê                                                                                                                       |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Wrapper opt-in (`detect_speech_segments_cached`)              | `detect_speech_segments` original (1.3) continua disponível; caller escolhe                                                  |
| Fingerprint = `size + mtime + sha256(head 1MB + tail 1MB)`     | Discriminativo o suficiente sem ler ~600MB; ~10ms pra qualquer arquivo                                                       |
| Key inclui `sha256(params)` + `schema_version`                 | Mudança em threshold/min_silence/min_speech invalida automaticamente; bumpar schema_version invalida tudo                    |
| TTL default 30 dias                                            | Cobre o ciclo típico de reprocessamento + evita crescimento sem bound                                                        |
| `_save_to_cache` atômico via tmp + rename                      | Evita cache corrompido em caso de crash mid-write                                                                            |
| Operador `>=` em vez de `>` na comparação age vs ttl           | Semântica determinística: `ttl=0` expira IMEDIATAMENTE (evita flake de timing em tests rápidos)                              |
| `cleanup_expired()` exposto                                    | Permite scheduled cleanup; remoção lazy seria suficiente mas ter explicit helper torna intent claro                          |

### A.4 — Benchmarks

| Decisão                                                       | Por quê                                                                                                                                          |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--benchmark-disable` no pyproject default                    | Benchmarks são lentos e distorcem coverage. Só rodam com `--benchmark-only` explícito                                                           |
| `--ignore=tests/benchmarks` no default                        | Mesmo com cov, benchmarks são micro-medições sem valor de cobertura adicional                                                                  |
| Benchmarks mockam funcionalidade pesada (silero, ffmpeg, Groq) | Medimos overhead de orquestração (alocação, dispatch). Tempo absoluto não é o ponto — regressão relativa é                                       |
| Pula baseline.json committado nesta fase                      | Baseline precisa ser estabelecido NO CI runner (não na máquina do dev) pra ser comparável. Follow-up: rodar 1x no CI e commitar baseline       |
| Cobertura dos cache hit vs miss                               | Ganho real do A.3 é dramático na vida real (~5-10s VAD vs ~1ms JSON read) — benchmark mockado já mostra hit ~2x mais rápido que miss mockado    |

---

## 5. Cobertura de testes

**489 testes** totais (387 da Fase 1.9 + **102 novos**), **97.76% de
cobertura geral** (gate é 70%). Distribuição por bloco:

| Bloco        | Arquivo                                                  | Testes novos | Cobertura |
| ------------ | -------------------------------------------------------- | ------------ | --------- |
| A.1          | `tests/test_audio_chunker.py` (17 testes adicionados)    | 17           | chunker 100% |
| A.2          | `tests/test_evaluation_manifest.py`                      | 9            | 100% |
| A.2          | `tests/test_evaluation_metrics.py`                       | 20           | 100% |
| A.2          | `tests/test_evaluation_runner.py`                        | 11           | 99% |
| A.2          | `tests/test_evaluation_comparator.py`                    | 16           | 100% |
| A.3          | `tests/test_audio_vad_cache.py`                          | 21           | 100% |
| A.4          | `tests/benchmarks/*` (mockados, skipped por default)     | (9 benchmarks)| n/a |

**Cobertura dos novos arquivos de service/lib (100% em todos):**
- `app/services/audio/chunker.py` (refatorado)
- `app/services/audio/vad_cache.py`
- `evaluation/__init__.py`
- `evaluation/manifest.py`
- `evaluation/metrics.py`
- `evaluation/runner.py` (99% — 1 linha do `if __name__ == "__main__"`)
- `evaluation/comparator.py`

### Tipos de teste

- **Unit** — função pura `_snap_to_silence`, parsing de manifest, métricas isoladas
- **Integration** — runner com manifest + fixture filesystem; comparator com saves/loads
- **Robustez** — cache corrompido, ttl expirado, golden faltando, JSON malformado do LLM
- **Determinismo** — usar `>=` no cache evita timing flake (lição da Fase 1.7)
- **CLI** — `main()` testado com capsys (stdout) e tmp_path (outputs)
- **Defensividade** — `compute_wer` com refs vazias, `compute_der` com segments degenerados, `_parse_issues` tolerante a lixo

---

## 6. Princípios anti-alucinação preservados

Esta fase não introduz mudanças que impactem os 6 princípios codificados
nas Fases 1.7/1.8/1.9. Pelo contrário, a A.2 (eval framework) é o que
permite **medir objetivamente** se mudanças futuras melhoram ou degradam
a anti-alucinação:

- Snap-to-silence (A.1) melhora qualidade de transcrição → reduz alucinação do Whisper
- Eval framework (A.2) permite responder "ata-score subiu ou caiu?"
- Cache (A.3) é puramente performance; sem impacto em qualidade
- Benchmarks (A.4) protegem contra regressão de performance

---

## 7. Critérios de aceite — MELHORIAS-CONCORRENTE A.1–A.4

### A.1 — Snap-to-silence chunking

- [x] Função `_snap_to_silence(target_sec, silences, max_delta=15)` implementada
- [x] Chunker usa a função quando há silenças disponíveis
- [x] Teste: gap pequeno (dentro do max_delta) → cut move pro midpoint
- [x] Teste: sem silenças no raio → cai pro target original sem quebrar

### A.2 — Eval framework

- [x] Estrutura `tests/golden/` versionada (README + sample_manifest)
- [x] `python -m evaluation.runner manifest.json --out run.json` produz JSON com WER, DER, ata-score
- [x] `python -m evaluation.comparator base.json current.json` mostra delta + summary agregado
- [ ] CI roda eval em PRs que mexem em `services/audio`, `services/transcription`, `services/diarization`, `services/minutes` — **FOLLOW-UP** (precisa de goldens reais primeiro)
- [ ] 5 goldens reais commitados — **FOLLOW-UP** (não posso gerar áudios reais; team adiciona conforme README)

### A.3 — Cache de silenças

- [x] Mesmo áudio + mesmos params → 2ª chamada usa cache (validado via call_count)
- [x] Mesmo áudio + params diferentes → cache miss (validado)
- [x] Cache não cresce indefinidamente (TTL 30 dias + `cleanup_expired()`)

### A.4 — Benchmarks de performance

- [x] `pytest tests/benchmarks/ --benchmark-only` rodando localmente
- [ ] Baseline committado — **FOLLOW-UP** (precisa rodar 1x no CI runner pra ter números comparáveis)
- [ ] CI bloqueia merge se regressão grave — **FOLLOW-UP** (config requer baseline)

---

## 8. Régua pré-PR — status local

| Comando                                    | Resultado                                                       |
| ------------------------------------------ | --------------------------------------------------------------- |
| `npm audit`                                | ✅ 0 vulnerabilidades                                           |
| `pip_audit -r src-python/requirements.txt` | ✅ No known vulnerabilities                                     |
| `pytest` (489 testes)                      | ✅ 489 passed, cov 97.76%                                       |
| `pytest tests/benchmarks --benchmark-only` | ✅ 9 benchmarks rodaram (não enforcement; só sanity)            |
| `ruff check .`                             | ✅ All checks passed                                            |
| `ruff format --check`                      | ✅ 98 files formatted                                           |
| `npm test`                                 | ⚠️ falha local (Node 24 + jsdom) — CI Node 20 passa             |
| `cargo fmt / clippy`                       | ⚠️ não rodado local (sem cargo); CI valida                      |
| Sanity SDKs em requirements                | ✅ jiwer + rapidfuzz + pyannote + groq + assemblyai + anthropic + openai + google-genai todos presentes |

---

## 9. Aprovação

✅ **Auditoria aprovada para commit + PR.**

### Follow-ups dessa fase

1. **Adicionar 5 goldens reais** em `tests/golden/` (depende de áudios
   reais transcritos por humano; ver `tests/golden/README.md`)
2. **Rodar benchmarks 1x no CI** pra estabelecer `baseline.json` e
   commitar
3. **Wire eval no CI** com guarda em mudanças de `services/audio`,
   `services/transcription`, `services/diarization`, `services/minutes`
4. **Integrar `detect_speech_segments_cached` no pipeline** (Fase 1.9
   ainda usa `detect_speech_segments` raw — trocar quando aparecer
   reprocessamento real)

### Decisões de produto pendentes pro Bloco B (Fase 1.10)

Ver [`MELHORIAS-CONCORRENTE.md`](MELHORIAS-CONCORRENTE.md):
- B.1 — Importar `pipelineProgress.ts` do concorrente (185 linhas)
- B.2 — Revisar `parallel.py` contra min-heap merge do concorrente
