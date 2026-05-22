# Eskuta

> **Áudio de reunião → ata estruturada profissional, em português.**
> Local-first, suas API keys e seus áudios nunca saem da sua máquina.

[![CI](https://github.com/Caiortdev/Eskuta/actions/workflows/ci.yml/badge.svg)](https://github.com/Caiortdev/Eskuta/actions)
[![Release](https://img.shields.io/github/v/release/Caiortdev/Eskuta?include_prereleases&label=download)](https://github.com/Caiortdev/Eskuta/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## O que o Eskuta faz

Você sobe um áudio de reunião (MP3, MP4, M4A, WAV — até 500MB). O app:

1. **Transcreve** com Whisper (Groq por padrão, AssemblyAI como fallback)
2. **Identifica falantes** (diarização por pyannote)
3. **Gera ata estruturada** via LLM (Claude, GPT ou Gemini):
   - 📝 Sumário executivo
   - 🎯 Decisões tomadas
   - ✅ Action items com responsável + prazo
   - ❓ Questões em aberto
   - 📌 Tópicos discutidos
4. **Cada decisão / ação** vem com a **citação literal do trecho da reunião** que sustenta — anti-alucinação real, não confia cegamente no LLM.

**Privacidade:**

- Áudio fica no seu disco em `~/.eskuta/uploads/`
- API keys ficam no **keyring nativo do OS** (Credential Manager no Windows, Keychain no macOS)
- Nada é enviado pro nosso servidor — **não temos servidor**
- Logs são locais e mascarados se você exportar pra suporte

---

## Como instalar

### Windows (recomendado)

1. Baixe o instalador mais recente em [Releases](https://github.com/Caiortdev/Eskuta/releases)
   - `Eskuta_X.Y.Z_x64-setup.exe` — instalador rápido (NSIS)
   - `Eskuta_X.Y.Z_x64_pt-BR.msi` — pacote MSI corporativo
2. Execute. Na primeira tela do SmartScreen, clique em **"Mais informações" → "Executar mesmo assim"** (o app ainda não tem certificado EV).
3. Abra o app pelo menu Iniciar.
4. Na tela de Onboarding, configure pelo menos:
   - **1 chave de transcrição** (Groq recomendado — tem free tier)
   - **1 chave de LLM** (Claude recomendado pra qualidade)

### macOS / Linux

Suportados pelo Tauri mas builds automatizados ainda não estão disponíveis. Veja [docs/BUILD-DISTRIBUTION.md](docs/BUILD-DISTRIBUTION.md) pra buildar do código.

---

## Como obter as API keys

Cada provider tem um console próprio. O app tem um modal passo-a-passo em **Configurações → "Como obter minha chave"**, mas resumo rápido:

| Provider               | Função            | Custo aprox.                        | Como obter            |
| ---------------------- | ----------------- | ----------------------------------- | --------------------- |
| **Groq**               | STT (transcrição) | Free tier amplo + ~US$0,04/h depois | console.groq.com/keys |
| **AssemblyAI**         | STT (fallback)    | 100h/mês grátis                     | assemblyai.com        |
| **Anthropic (Claude)** | LLM principal     | ~US$0,02 por reunião 1h             | console.anthropic.com |
| **OpenAI (GPT)**       | LLM alternativo   | ~US$0,03 por reunião 1h             | platform.openai.com   |
| **Google (Gemini)**    | LLM mais barato   | Free tier amplo + ~US$0,01/h        | aistudio.google.com   |

Você precisa de **no mínimo 1 STT + 1 LLM** pra gerar atas.

**Sugestão econômica:** Groq (STT free tier) + Google Gemini (LLM free tier) = atas grátis até estourar limites diários.

---

## Como usar

1. **Reuniões** (sidebar) → **Nova reunião**
2. Arraste o áudio (ou clique pra escolher) — MP3/MP4/M4A/WAV até 500MB
3. (Opcional) Dê um título
4. O app mostra progresso em tempo real: Convertendo → VAD → Chunking → Transcrevendo → Diarizando → Gerando ata → Validando
5. Em ~2-10min (depende do tamanho), a ata aparece com 3 abas:
   - **Ata** — sumário + decisões + tópicos + questões abertas
   - **Transcrição** — texto completo com tempos por trecho
   - **Ações** — checklist de action items

### Atalhos de teclado

- `Ctrl+H` — Início (lista de reuniões)
- `Ctrl+U` — Nova reunião (upload)
- `Ctrl+,` — Configurações
- `Esc` — fecha modais

### Exportar logs pra suporte

Em **Configurações → Diagnóstico → Exportar logs** baixa um ZIP com os logs locais (com API keys mascaradas) + metadata do app. Útil pra anexar em reports de bug.

---

## FAQ

**A minha API key fica segura?**
Sim. Ela é armazenada no keyring do sistema operacional (Credential Manager / Keychain). Não fica em nenhum arquivo. O app só lê quando precisa chamar o provider. O endpoint `/test` valida sem expor o valor.

**Quanto custa pra rodar?**
Depende do uso. Com Groq + Gemini no free tier, ~10 reuniões de 1h/dia custam zero. Acima disso, conta o usage de cada provider.

**Funciona offline?**
Não — STT e LLM precisam de internet pra chamar os providers. Mas o áudio, a ata, e a transcrição ficam armazenados localmente.

**O áudio é enviado pra Anthropic / OpenAI?**
Não. Só a **transcrição em texto** é enviada pro LLM (Claude/GPT/Gemini). O áudio em si só vai pra Groq/AssemblyAI durante a transcrição.

**Posso mudar de LLM?**
Sim, em Configurações. Pode salvar todas as keys e escolher qual usar como padrão.

**Como atualizar?**
O app verifica updates no startup (quando ativado em `tauri.conf.json`) e mostra notificação. Por enquanto a infra de update está em modo manual — baixe a versão nova em [Releases](https://github.com/Caiortdev/Eskuta/releases).

---

## Para desenvolvedores

- [docs/MAPA_PROJETO.md](docs/MAPA_PROJETO.md) — visão geral do projeto
- [docs/RELATORIO_TECNICO.md](docs/RELATORIO_TECNICO.md) — roadmap técnico fase-a-fase
- [docs/BUILD-DISTRIBUTION.md](docs/BUILD-DISTRIBUTION.md) — como buildar do código
- [docs/AUTO-UPDATE.md](docs/AUTO-UPDATE.md) — sistema de auto-update
- [docs/RELEASE-READINESS.md](docs/RELEASE-READINESS.md) — scorecard técnico
- [CONTRIBUTING.md](docs/CONTRIBUTING.md) — guia de contribuição
- [CHANGELOG.md](CHANGELOG.md) — histórico de releases

### Stack

- **Frontend:** React 19 + TypeScript + Vite 7 + TailwindCSS v4
- **Wrapper desktop:** Tauri 2 (Rust)
- **Backend local (sidecar):** Python 3.11 + FastAPI + SQLAlchemy async
- **Banco:** SQLite (MVP) — migrations Alembic bilíngues pra Postgres futuro

### Quick dev

```powershell
# Pré-requisitos: Node 20+, Rust stable, Python 3.11
git clone https://github.com/Caiortdev/Eskuta && cd Eskuta
npm install
cd src-python
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
cd ..
npm run tauri dev
```

---

## Licença

MIT — veja [LICENSE](LICENSE).
