# Eskuta — Auditoria pós-instalação (HONESTA)

**Data:** 2026-05-22
**Build testado:** v0.1.0 (final desta sessão)
**Quem testou:** Caio (usuário real, primeiro contato com o app instalado)

---

## Estado real: **não está pronto pra usuário final**

Score honesto: **~6/10** (não 9 como eu disse antes).

O scorecard anterior em `RELEASE-READINESS.md` focava em métricas de testes
unitários e ignorava que **ninguém tinha instalado o app antes**. Quando você
instalou pela primeira vez, **3 bugs críticos** apareceram que nenhum teste
unitário pegou:

### 🔴 Bugs críticos descobertos NA primeira instalação

| # | Bug | Causa raiz | Como deveria ter sido pego |
|---|-----|-----------|---------------------------|
| 1 | "Aguardando sidecar Python subir…" como mensagem ao usuário | Label de dev hardcoded em `App.tsx` | Revisão de UX antes do release |
| 2 | Janela CMD/console preta abrindo junto com o app | PyInstaller `--console` em vez de `--windowed` | Teste de instalação em VM/máquina limpa |
| 3 | "Erro ao carregar reuniões: Failed to fetch" + "no such table: meetings" | Alembic migrations nunca rodavam no startup do sidecar empacotado | E2E test do upload completo |
| 4 | Sidecar antigo `eskuta-sidecar.exe` (120MB) ficava no disco após reinstalar | NSIS não limpa arquivos do build antigo | Smoke test pós-upgrade |

**Por que escapou dos meus testes:**
- Unit tests passavam (`550 backend + ~120 frontend`) — mas eles testam unidades isoladas, não o app empacotado
- CI tinha "smoke test do sidecar empacotado" — mas só validava `/health`, não `/api/meetings` (que precisa do DB ter tabelas)
- Não havia **teste de instalação em máquina limpa**

### 🟡 Não validado (pode ter mais bugs)

- ⚠ **Upload de áudio real**: nunca foi testado end-to-end no app empacotado. Bug do migrations sugere que outros paths quebrados podem existir.
- ⚠ **Geração de ata via LLM real**: nunca foi feita uma chamada real com sua API key
- ⚠ **Fluxo da ata renderizada na UI**: nunca foi visto com dados reais
- ⚠ **Exportar logs**: endpoint existe mas botão na UI nunca foi exercitado
- ⚠ **Teste de chave**: o fluxo "Salvar e testar" nunca foi rodado contra provider real
- ⚠ **Dark mode**: implementado mas não testado visualmente
- ⚠ **Shortcut Ctrl+,/U/H**: implementados mas não testados na webview do Tauri
- ⚠ **Onboarding inteligente**: lógica de skip nunca foi exercitada
- ⚠ **Reaper de meetings travadas**: tentou rodar mas falhou (sem tabela) — não sabemos se o caminho feliz funciona
- ⚠ **Health/detailed**: endpoint existe mas nunca chamado por humano
- ⚠ **Rate limiting**: integrado mas nunca testado contra carga

### 🟠 Features parcialmente implementadas

- 🟠 **Diarização (pyannote)**: excluída do bundle pra reduzir tamanho. O app vai funcionar SEM diarização ("quem falou o quê"). Ata sai só com texto, sem nomes de speakers — pode confundir usuário.
- 🟠 **Screenshots do `ApiKeyGuideModal`**: nunca foram capturados. O modal abre mas o `onError` esconde img quebrada → usuário vê só passos em texto.
- 🟠 **Auto-update**: plugin integrado mas `active=false`. Nenhum servidor de updates. Usuários terão que baixar novas versões manualmente.
- 🟠 **Sentry**: SDK integrado mas DSN vazio (no-op). Nenhuma telemetria de erros real.
- 🟠 **Code signing**: nenhum. SmartScreen vai assustar todo primeiro usuário.

### 🔵 Decisões inseguras que precisam validação

- 🔵 **Bundle 120MB do sidecar**: PyInstaller --onedir gera ~258MB de arquivos. Defender pode flagar partes (`*.pyd` desconhecidos).
- 🔵 **Spawn via std::process::Command em vez de tauri-plugin-shell**: refactor recente, lib.rs nunca foi testado em produção.
- 🔵 **Resource glob `binaries/eskuta-sidecar/**`**: WiX pode reclamar de muitos arquivos pequenos no MSI.

---

## O que precisa fazer ANTES de distribuir

### 🔥 Bloqueadores (não release sem isso)

1. **Validar fluxo completo end-to-end manualmente:**
   - [ ] Instalar em VM/PC limpo (sem Visual Studio, sem Python instalado)
   - [ ] Abrir app — não pode ter janela CMD
   - [ ] Sidecar sobe em <5s
   - [ ] Onboarding configura 1 STT (Groq) + 1 LLM (Claude)
   - [ ] Test de chave responde "✓ válida"
   - [ ] Upload de áudio real (5-10min de reunião)
   - [ ] Pipeline completa: convert → VAD → chunk → transcribe → minutes → validate
   - [ ] Ata aparece na UI com decisões + ações + evidence quotes
   - [ ] Exportar logs funciona
   - [ ] Desinstalar limpa tudo

2. **Validar handling de erros realistas:**
   - [ ] Key inválida → mensagem clara
   - [ ] Áudio corrupto → erro útil
   - [ ] Sem internet → erro útil
   - [ ] Provider fora do ar → fallback funciona

3. **Smoke test em CI do bundle:**
   - O CI atual roda `/health` mas não `/api/meetings`. Adicionar test que valida que migrations rodaram (chamar `GET /api/meetings`).

### 🟡 Importantes (release "soft launch" para ~5 amigos talvez aceite sem)

4. Capturar screenshots dos consoles (issue #18)
5. Subir servidor de updates + ativar auto-update
6. Adicionar pyannote de volta com flag opcional
7. Code signing EV cert

### 🟢 Pós-release

8. Sentry com DSN real
9. macOS/Linux builds
10. Real user metrics

---

## Plano realista pra ficar pronto

### Esta semana — **VOCÊ** valida manualmente

Não dá pra distribuir sem **VOCÊ testar uma reunião real do começo ao fim**. Sequência:

1. Instale o build novo (com migrations + windowed fixes)
2. Configure Groq + Claude (suas keys)
3. Suba um áudio de 5min seu (qualquer reunião)
4. Veja o que quebra
5. Cola erro aqui, eu fixo
6. Repete até funcionar end-to-end

**Estimativa:** 2-4 ciclos de fix+test, ~2-3 horas suas (não minhas).

### Depois disso

7. Eu adiciono E2E test que reproduz o fluxo (pra nunca mais regredir)
8. Você decide se distribui pra beta privado (~10 pessoas) ou continua hardening

---

## Lições do que aconteceu hoje

Eu errei em 3 coisas:

1. **Confiei em testes unitários como prova de funcionar.** Eles provam apenas que cada peça isolada está OK. Não provam que o app inteiro funciona.

2. **Dei score otimista sem ter rodado o app.** Score 9.1/10 era pra um app que ainda nunca tinha aberto numa máquina. Score honesto era ~6/10.

3. **Não priorizei "instalar e usar" como teste antes de distribuir.** A primeira pessoa a abrir o app empacotado foi você, na primeira distribuição. Isso é o teste que deveria ter sido feito primeiro, não último.

Pra próximas releases: **nenhum release público sem rodar o fluxo principal pelo menos uma vez no bundle final**.

---

## Score real por área (revisado depois dos bugs)

| Área | Score anterior (otimista) | Score honesto |
|------|---------------------------|---------------|
| Segurança | 9.5 | 8 (não validado em prod) |
| Performance | 9 | 6 (start lento descoberto) |
| UX | 9 | 5 (CMD aparecia, label técnica) |
| Testes & QA | 9.5 | 7 (passa em unit, falha em E2E real) |
| Distribuição | 8 | 5 (instalador feito, mas bug crítico) |
| Observabilidade | 9 | 7 (logs ok mas migrations falhavam silenciosamente) |
| Documentação | 9.5 | 8 (boa, mas faltava onboarding pós-install) |
| Robustez | 9.5 | 5 (DB vazio = app inutilizável) |
| **Geral** | **9.1** | **~6.4** |

**A diferença entre 9.1 e 6.4 é exatamente "testar o app instalado pelo menos uma vez".**
