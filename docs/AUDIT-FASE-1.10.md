# Auditoria de integridade e segurança — Fase 1.10

> **Data:** 2026-05-22
> **Escopo:** Fase 1.10 do `RELATORIO_TECNICO.md` — Frontend React (1.10.1
> Roteamento + 1.10.2 Cliente HTTP + 1.10.3 Upload + 1.10.4 Detalhes) +
> endpoints REST de meetings (foundation pro frontend) + Bloco B.1 de
> `MELHORIAS-CONCORRENTE.md` (pipelineProgress).
> **Resultado final:** ✅ aprovado para commit + PR

Esta fase fecha o MVP utilizável: do upload do áudio até a ata
renderizada na tela. PR único conforme acordado (sem commits
intermediários).

---

## 1. Vulnerabilidades de dependências

| Ecossistema                            | Ferramenta                      | Resultado                    |
| -------------------------------------- | ------------------------------- | ---------------------------- |
| Node (`package.json`)                  | `npm audit`                     | **0 vulnerabilidades**       |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities** |

### Novas dependências adicionadas nesta fase

| Pacote             | Versão | Motivo                                                              |
| ------------------ | ------ | ------------------------------------------------------------------- |
| `react-router-dom` | latest | Roteamento client-side (1.10.1)                                     |
| `react-dropzone`   | latest | Drag-and-drop de áudio (1.10.3)                                     |

**Backend: nenhuma nova dep** — endpoints REST usam stack já presente
(FastAPI, Pydantic, SQLAlchemy, `python-multipart` que já vinha da Fase 0).

---

## 2. Secrets hardcoded

Grep cego em arquivos novos:
- `src/types/meeting.ts`
- `src/lib/{api,pipelineProgress}.ts` + tests
- `src/components/*` + `src/pages/*`
- `src-python/app/api/meetings.py` + `src-python/tests/test_api_meetings.py`

**Nenhum match.** API keys continuam exclusivamente no keyring via
`app.services.keys` (Fase 1.11). Frontend NUNCA armazena keys — só
manda direto pro endpoint `PUT /api/keys/:provider` que delega ao
keyring.

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação                | Configuração atual                                                                                                                | Status |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Bind do socket             | `127.0.0.1` (default herdado)                                                                                                     | ✅     |
| CORS                       | Sem mudança — lista explícita herdada da Fase 0                                                                                  | ✅     |
| POST /meetings/upload      | Multipart com whitelist de extensões (.mp3, .mp4, .m4a, .wav); max 500MB enforced via leitura por chunks; UUID-based filename     | ✅     |
| Path traversal             | Filename original sanitizado via regex `[^A-Za-z0-9_.-]+`; path real usa UUID hex — nunca o filename do usuário                  | ✅     |
| Resource exhaustion        | `_save_upload_streaming` lê chunks de 4MB e aborta + remove arquivo parcial assim que estoura — não enche memória nem disco       | ✅     |
| Pagination                 | `GET /meetings?limit=N&offset=N` com Query validation (`ge=1, le=200, ge=0`); evita "carregar tudo"                              | ✅     |
| Soft delete                | `DELETE /meetings/{id}` preenche `deleted_at`; lista exclui via `WHERE deleted_at IS NULL` — sem cleanup de arquivo (deliberado) | ✅     |
| Status leak                | `GET /meetings/{id}/status` retorna apenas `{id, status, error, error_type}` — não vaza paths, queries, etc                       | ✅     |
| Speaker map                | `PUT /meetings/{id}/speaker-map` aceita dict[str,str]; substitui inteiramente (não merge) — comportamento claro                  | ✅     |

### Frontend security

| Verificação                  | Configuração                                                                                                                 | Status |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------ |
| API base hard-coded          | `http://127.0.0.1:8765` — não muda em runtime; impossível redirecionar pra origem externa                                    | ✅     |
| `ApiError` tipado            | Toda chamada que retorna não-2xx vira `ApiError`; UI trata via `err.detail` (sem expor stack ou body cru ao usuário)         | ✅     |
| Sidecar gate                 | `App.tsx` bloqueia toda a UI até `/health` responder. Sem race condition de "renderizar ata enquanto sidecar não tá pronto" | ✅     |
| Input do user em URL          | Title vai como query param URL-encoded; nunca interpolado direto no path                                                     | ✅     |
| Confirm() antes de delete    | `confirm()` pra remover API key (UX guardrail; backend é o gate real)                                                        | ✅     |

---

## 4. Decisões de design

### 4.1 Backend

| Decisão                                                                       | Por quê                                                                                                                                                              |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Endpoints organizados em `app/api/meetings.py`                                | Mesma estrutura modular das fases anteriores (`api/keys.py`, `api/transcription.py`)                                                                                |
| UUID hex como filename no disco                                               | Zero risco de path traversal mesmo com sanitização defeituosa do filename original; também garante unique                                                            |
| Streaming upload com hashing incremental                                      | Não carrega 500MB na memória; hash sha256 calculado em paralelo na escrita; aborta cedo se exceder limite                                                            |
| Eager-loading explícito de transcript + segments + minutes + decisions + actions + evidences | `selectinload` aninhado evita N+1 — uma roundtrip no DB pra detail completo                                                                                          |
| Soft delete em vez de hard delete                                             | Permite undo + auditoria. Cleanup físico (remover arquivo) fica pra task separada futura                                                                            |
| `_load_meeting` helper centraliza 404                                          | Toda rota que requer meeting existente usa o mesmo helper — mesma mensagem, mesmo status, sem repetição                                                              |
| `MeetingStatusResponse` enxuto                                                | Endpoint de polling roda a cada 2s; retornar só `{status, error}` (não detail completo) economiza banda                                                              |
| Status codes deprecation                                                      | Usei `HTTP_422_UNPROCESSABLE_CONTENT` e `HTTP_413_CONTENT_TOO_LARGE` (FastAPI moveu nomes)                                                                            |

### 4.2 Frontend

| Decisão                                                                  | Por quê                                                                                                                                                              |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Single `src/lib/api.ts` com todos endpoints                              | Centraliza chamada HTTP, error mapping, query string building. Relatório §1.10.2 sugere esse pattern                                                                |
| TypeScript types espelham Pydantic 1:1                                   | Snake_case mantido nos campos JSON pra evitar transformação intermediária; team-prone error                                                                          |
| `BrowserRouter` + Outlet pattern                                         | Padrão React Router 6+ — sidebar fica fora de `<Routes>` mas em layout pai (`AppLayout`)                                                                            |
| Onboarding fora do AppLayout                                             | Primeira execução não tem sidebar — é um gate. Layout aplicado só após user passar pelo onboarding                                                                  |
| `pipelineProgress.ts` puro (sem React)                                    | Bloco B.1. Lógica testável sem mocks de hook. Encapsula labels pt-BR + ETA + percent — UI só renderiza                                                              |
| `progressPercent` linear (não-ponderado)                                  | Simplicidade > precisão. Fase real-time não traz ganho significativo sem instrumentação (vide AUDIT 1.9 follow-up)                                                  |
| `useState(() => Date.now())` em vez de `useRef`                          | React 19's eslint regra `react-hooks/refs` impede acesso a `.current` durante render. Lazy initializer é o pattern canônico                                          |
| Polling 2s no `Processing.tsx`                                            | Equilíbrio: usuário sente progresso, mas não martela o sidecar. Sem WebSocket/SSE no MVP — futura otimização se ficar pesado                                        |
| 600ms de delay antes do redirect quando completed                         | Usuário vê o ✅ "Pronto" antes do redirect — feedback visual claro                                                                                                  |
| Confirm dialog antes de delete API key                                   | Operação destrutiva (perde key, precisa re-entrar). Confirm() nativo é mínimo aceitável; toast/modal Shadcn pode vir em iteração futura                            |
| `EvidenceQuote` inline + blockquote estilo                               | Princípio anti-alucinação: usuário vê de onde veio cada afirmação. UI deixa óbvio                                                                                   |
| Sidebar fixa em 224px (`w-56`)                                            | Tamanho confortável pra 3-5 itens; não tem responsive complicado no MVP (relatório especifica mínimo 800x600)                                                       |

### 4.3 Bloco B.1 (pipelineProgress)

| Decisão                                              | Por quê                                                                                                                       |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 9 fases (8 ativas + completed)                       | Bate com `MEETING_STATUS_VALUES` do pipeline (Fase 1.9). `failed` é estado terminal fora da progressão linear                |
| `deriveState` retorna union discriminado            | TypeScript narrowing facilita render: caller usa `switch (state.kind)` ou conditional checks                                  |
| ETA com fórmula simples (`elapsed / percent * 100`) | Princípio "performance percebida > precisa": ETA bem aproximado é melhor do que nenhum                                       |
| Clampa ETA negativo em 0                             | Defensivo — quando pipeline trava num passo, percent não avança mas tempo passa. ETA não vira negativo (que seria absurdo)   |
| `formatEta` em pt-BR (`Xmin Ys`)                     | Branding consistente com o resto da UI                                                                                       |
| Status desconhecido cai pro fallback `position=0`    | Defesa em profundidade — se backend adicionar novo status, frontend não crasha (mostra label cru em vez de error boundary)   |

---

## 5. Cobertura de testes

### Backend

**514 testes** totais (489 anteriores + **25 novos pro meetings**),
**96.84% de cobertura geral**.

| Arquivo                                | Cobertura |
| -------------------------------------- | --------- |
| `app/api/meetings.py`                  | 100%      |

Testes cobrem:
- Upload com diferentes formatos / sem extensão / extensão inválida / tamanho excedido
- Sanitização de filename perigoso (`../../etc/passwd.mp3`)
- List paginação, soft-deleted excluídos, ordem por created_at desc
- Detail com eager-loading de transcript + minutes
- 404 quando soft-deleted
- Status com error_type populado
- Speaker map set / replace / clear
- Delete idempotência (404 na segunda chamada)

### Frontend

| Arquivo                              | Testes                                            |
| ------------------------------------ | ------------------------------------------------- |
| `src/App.test.tsx`                   | Sidecar gate (loading / error / pronto)           |
| `src/lib/api.test.ts`                | health, ApiError.detail, todos os endpoints CRUD  |
| `src/lib/pipelineProgress.test.ts`   | Constantes, phaseFromStatus, deriveState, ETA      |
| `src/lib/utils.test.ts`              | (já existia — não tocado)                         |

**Vitest local quebra** com Node 24 + jsdom (quirk conhecido — memo
`project_eskuta_local_env_quirks.md`). CI usa Node 20 onde funciona.

---

## 6. Critérios de aceite — RELATORIO_TECNICO §1.10

### 1.10.1 — Roteamento e layout base

- [x] React Router instalado + roteamento entre telas
- [x] Estrutura `src/pages/` com Home, Upload, Processing, MeetingDetail,
      Settings, Onboarding
- [x] Layout base com sidebar (`AppLayout`)
- [x] Onboarding aparece como rota separada (caller decide quando navegar)

### 1.10.2 — Cliente HTTP

- [x] Todas as chamadas centralizadas em `src/lib/api.ts`
- [x] Tipos TypeScript em `src/types/meeting.ts` espelham schemas Pydantic
- [x] Erros têm tratamento consistente via `ApiError`

### 1.10.3 — Tela de Upload com progresso em tempo real

- [x] Drag & drop via `react-dropzone` pra MP3, MP4, M4A, WAV
- [x] Validação de tamanho (500MB) e formato no frontend + reforço no backend (defesa em camadas)
- [x] Após upload, redirect pra `/processing/:id` automático
- [x] Polling `/meetings/:id/status` a cada 2s
- [x] Progresso visual: progress bar + lista de fases com ícones (✓ done, ⏳ active, ○ pending)
- [x] Erros mostrados com mensagem clara + botão "Tentar de novo"

### 1.10.4 — Tela de detalhes da reunião

- [x] Tabs: Ata / Transcrição / Ações
- [x] Ata renderiza com tipografia clean (sections: Sumário, Participantes, Tópicos, Decisões, Open Questions)
- [x] Evidências de cada item mostradas inline como blockquote
- [x] Banner de warning quando `validation_passed=False`
- [x] Botão "Voltar pra lista"
- [ ] Botão de exportar (Markdown) — **FOLLOW-UP** (não scope do MVP — relatório lista como "V2 pra PDF")
- [ ] Botão de regenerar ata — **FOLLOW-UP** (precisa de novo endpoint backend)

### Implícitos no relatório

- [x] Home/Dashboard com lista de meetings (cards + status badges)
- [x] Settings com gerenciamento de API keys (form + remove + clear)
- [x] Onboarding com explicação inicial

### Bloco B.1 (MELHORIAS-CONCORRENTE)

- [x] `pipelineProgress.ts` puro (185 linhas equivalente ao concorrente — adaptado)
- [x] 8 fases + completed + failed
- [x] ETA atualiza em tempo real conforme polling
- [x] Edge cases tratados: NaN, divisão por zero, fase fora de ordem

---

## 7. Régua pré-PR — status local

| Comando                                              | Resultado                                                       |
| ---------------------------------------------------- | --------------------------------------------------------------- |
| `pytest`                                             | ✅ 514 passed, cov 96.84%                                       |
| `npm audit`                                          | ✅ 0 vulnerabilidades                                           |
| `pip_audit`                                          | ✅ No known vulnerabilities                                     |
| `npx tsc --noEmit`                                   | ✅ 0 errors                                                     |
| `npx eslint . --max-warnings=0`                      | ✅ 0 errors                                                     |
| `npx prettier --check`                               | ✅ All files OK                                                 |
| `npm test`                                           | ⚠️ falha local (Node 24 + jsdom) — CI Node 20 valida            |
| `cargo fmt / clippy`                                 | ⚠️ não rodado local (sem cargo); CI valida                      |

---

## 8. Aprovação

✅ **Auditoria aprovada para commit + PR.**

### Follow-ups fora do escopo desta fase

- Export de Markdown (relatório §1.10.4 lista como nice-to-have)
- Botão de regenerar ata (precisa de novo endpoint backend)
- WebSocket / SSE pra progresso real-time (substitui polling — otimização)
- Cleanup físico de arquivos de áudio após soft delete (task background)
- Toast notifications via Shadcn (substituir `confirm()` + erros inline)
- Dark mode polish (já temos variables CSS, mas sem toggle UI)
- B.2 (revisar `parallel.py` contra min-heap merge) — fica pra próxima iteração

### Marcos atingidos

Esta fase **fecha o MVP utilizável** — usuário consegue:

1. Abrir o app
2. Configurar API keys nas Settings
3. Fazer upload de áudio
4. Acompanhar progresso em tempo real
5. Ver a ata gerada
6. Auditar evidências de cada item
7. Voltar pra lista e gerenciar histórico

A próxima fase (1.12 — Empacotamento) transforma isso num instalador
distribuível, fechando o MVP.
