# 📘 Projeto Eskuta — Documento Geral

> **Versão:** 0.1.0 (rascunho de planejamento)
> **Última atualização:** 20/05/2026
> **Status:** Pré-desenvolvimento (planejamento concluído)

---

## 🎯 O que é isso aqui?

Eskuta é um aplicativo desktop que resolve uma dor real e específica: **a gente esquece o que foi combinado nas reuniões**. Quem tem reunião de 1, 2, 3 horas seguidas sabe disso — no final, fica difícil lembrar quem ficou responsável pelo quê, qual decisão foi tomada e o que precisa ser feito até a próxima reunião.

A Eskuta resolve isso de dois jeitos:

1. **Modo Upload (Fase 1 / MVP):** Você sobe um arquivo MP3 ou MP4 da reunião e o app transcreve e gera uma ata estruturada profissional em poucos minutos.

2. **Modo Tempo Real (Fase 2):** O app fica rodando em segundo plano durante a sua reunião (Google Meet, Zoom, Teams, qualquer um), captura o áudio do sistema sem precisar entrar como bot, e ao final entrega a ata pronta.

Não é mais um "Otter" ou "Fireflies". Os pontos onde a gente vai brigar:

- **Privacidade real:** áudio fica na sua máquina, só a transcrição vai pra API (e mesmo isso é configurável)
- **Sem bot na reunião:** ninguém vê "Eskuta Bot entrou na chamada"
- **Português brasileiro de verdade:** otimizado pro nosso jeito de falar (gírias, "né", "tipo", "então")
- **Você escolhe a IA:** GPT, Claude ou Gemini — você plugga sua chave e usa o que quiser
- **Custo absurdamente baixo:** com Groq + Llama no free tier, você roda de graça pra uso pessoal

---

## 🧠 Pra quem é

- **Persona principal:** Profissional que participa de 5+ reuniões longas por semana e precisa documentar decisões/ações
- **Cenários típicos:**
  - Dev/PM em reuniões de planning, retrô, alinhamento técnico
  - Advogado, contador, consultor em reuniões com cliente
  - Líder de time em 1-on-1s e all-hands
  - Estudante em aulas gravadas

---

## 🛠️ Stack Tecnológica

A escolha de cada peça tem motivo. Não escolhi nada "porque tá na moda".

### Frontend
**React + TypeScript + TailwindCSS**

- React é o padrão de mercado, qualquer dev pega rápido
- TypeScript pra ter segurança de tipos e autocomplete decente
- Tailwind pra não ficar perdendo tempo com CSS

### Backend Local (Sidecar)
**Python + FastAPI**

- Python porque o ecossistema de áudio/ML é dele (ffmpeg-python, pyannote, librosa, etc.)
- FastAPI porque é leve, rápido, async nativo e tem docs automáticas (Swagger)
- **Por que não Django?** Django é overkill pra rodar como sidecar local. FastAPI inicia mais rápido, consome menos memória e é mais simples de empacotar no PyInstaller.

### Wrapper Desktop
**Tauri (Rust)**

- 10x menor que Electron no instalador (~15MB vs ~200MB)
- 3x menos consumo de memória durante a reunião
- Acesso nativo às APIs de áudio do sistema operacional
- WebView nativa do SO (não embute Chromium)

### Banco de Dados
**SQLite (local) → Postgres (produção/cloud no futuro)**

- SQLite zero-config pra app local, embarcado direto no Tauri
- **Todas as migrations escritas de forma compatível com Postgres** pra futuro fácil
- Quando virar produto pago multi-usuário, troca driver e migra estrutura

### APIs Externas (configuráveis pelo usuário)

**Transcrição (STT):**
- **Primária:** Groq Whisper Large v3 Turbo (free tier generoso)
- **Fallback:** AssemblyAI (100h grátis, melhor diarização)

**LLM (geração de ata):**
- **Claude** (Anthropic) — escolha padrão por qualidade superior em raciocínio
- **GPT** (OpenAI)
- **Gemini** (Google)

**Diarização (separar quem falou):**
- **pyannote.audio** (open-source, roda local)

---

## 🏗️ Arquitetura em Alto Nível

```
┌──────────────────────────────────────────────────────────┐
│                     APLICATIVO DESKTOP                    │
│                         (Tauri Shell)                     │
│                                                            │
│   ┌──────────────────────┐    ┌─────────────────────┐    │
│   │   FRONTEND REACT     │◄──►│   SIDECAR PYTHON    │    │
│   │   (UI / TypeScript)  │    │   (FastAPI)         │    │
│   └──────────────────────┘    │                     │    │
│           │                    │   - Pipeline Áudio  │    │
│           │ Rust commands      │   - STT Router      │    │
│           ▼                    │   - LLM Router      │    │
│   ┌──────────────────────┐    │   - Gerador Ata     │    │
│   │   RUST (Tauri Core)  │    │   - Pyannote        │    │
│   │                      │    └─────────────────────┘    │
│   │   - Captura áudio    │              │                │
│   │   - Janelas/overlay  │              │                │
│   │   - File system      │              ▼                │
│   │   - SQLite           │    ┌─────────────────────┐    │
│   └──────────────────────┘    │   SQLite (local)    │    │
│                                └─────────────────────┘    │
└────────────────┬──────────────────────────────────────────┘
                 │
                 │ HTTPS (criptografado)
                 ▼
   ┌────────────────────────────────────┐
   │      APIs EXTERNAS DE IA           │
   │  • Groq (STT primário)             │
   │  • AssemblyAI (STT fallback)       │
   │  • Claude / GPT / Gemini (ata)     │
   └────────────────────────────────────┘
```

---

## 🗺️ Roadmap em Fases

### 🟢 Fase 0 — Setup (1 semana)
Ambiente de desenvolvimento, scaffolding, build pipeline funcionando.

### 🟢 Fase 1 — MVP Upload (4-6 semanas)
- Upload de MP3/MP4 (até 3h)
- Pipeline de transcrição com fallback (Groq → AssemblyAI)
- Geração de ata com LLM configurável (Claude/GPT/Gemini)
- Persistência local
- Build de instalador único (Windows e macOS)
- **Critério de sucesso:** você consegue jogar uma reunião sua de 2h, esperar ~3 min, e ter uma ata útil de verdade

### 🟡 Fase 2 — Tempo Real (4-6 semanas após Fase 1 validada)
- Captura de áudio do sistema operacional (mic + sistema)
- Transcrição "quase real-time" via chunks
- UI minimalista durante reunião
- Reprocessamento pós-reunião pra ata final de qualidade
- **Critério de sucesso:** você liga o modo durante uma reunião de Meet, fala normalmente, e ao final tem ata

### 🔵 Fase 3 — Produto Pago (quando MVP+Real-time estiverem maduros)
Detalhes no relatório técnico. Inclui:
- Multi-tenant / contas de usuário
- Backend hospedado
- Sync entre devices
- Migração SQLite → Postgres
- Cobrança recorrente
- Time de suporte

### 🟣 Fase 4 — Integrações (V2)
Google Meet via bot (Recall.ai ou Vexa), Microsoft Teams nativo, Zoom, integrações com Notion/Slack/Trello.

---

## 📚 Glossário

Termos que vão aparecer durante o projeto. Se você travar em algum, consulta aqui.

| Termo | O que significa |
|-------|-----------------|
| **STT** | Speech-to-Text. Transformar áudio em texto. (Whisper, Deepgram, AssemblyAI) |
| **LLM** | Large Language Model. Modelo de linguagem grande. (Claude, GPT, Gemini, Llama) |
| **Diarização** | Identificar QUEM falou o quê numa gravação multi-falante. |
| **VAD** | Voice Activity Detection. Detector que separa fala de silêncio. |
| **WER** | Word Error Rate. Métrica de qualidade de transcrição (quanto menor, melhor). |
| **Chunking** | Cortar áudio em pedaços menores pra processar em paralelo. |
| **Sidecar** | Processo separado que roda junto com o app principal (no nosso caso, FastAPI dentro do Tauri). |
| **Few-shot prompting** | Dar exemplos pro LLM antes de pedir pra ele fazer algo. |
| **Chain-of-thought** | Forçar o LLM a "pensar passo a passo" antes de responder. |
| **Alucinação** | Quando a IA inventa informação que não estava no input. |
| **Fallback** | Plano B quando o plano A falha. (Groq cai → AssemblyAI assume) |
| **Free tier** | Plano gratuito de uma API. |
| **Rate limit** | Limite de requisições por tempo. |
| **WebView** | Componente do SO que renderiza HTML (usado pelo Tauri). |
| **PyInstaller** | Ferramenta que empacota um app Python em executável. |
| **WASAPI** | API de áudio do Windows que permite captura de loopback (áudio do sistema). |
| **ScreenCaptureKit** | API de captura de tela/áudio do macOS 13+. |
| **Content Protection** | Flag que esconde uma janela de softwares de captura de tela. |

---

## ⚠️ Limitações Conscientes do MVP

A gente deliberadamente **NÃO vai fazer** isso na Fase 1 pra entregar valor rápido:

- ❌ Multi-usuário ou contas
- ❌ Sync entre dispositivos
- ❌ Bot que entra na reunião (vai ser desktop-only)
- ❌ Linux (foco Windows e macOS, Linux fica pra depois)
- ❌ Modo offline 100% (precisa de internet pras APIs de IA)
- ❌ Treinamento de modelo próprio
- ❌ Integração com calendário
- ❌ Mobile (Android/iOS)

Cada uma dessas tem espaço no roadmap. Mas elas viram **distrações** se entrarem no escopo do MVP.

---

## 🎓 Princípios de Design

Algumas regras que vão guiar decisões técnicas no decorrer do projeto:

1. **Local-first sempre que possível.** Áudio nunca sai da máquina do usuário a não ser pra STT (e isso é configurável).

2. **Falha elegante.** Se o Groq cair, AssemblyAI assume. Se Claude estiver fora, GPT entra. Usuário não vê erro, vê "processando".

3. **O usuário no controle.** Ele escolhe qual LLM usar, qual modelo, qual provider. A gente sugere defaults bons, mas ele decide.

4. **Performance percebida > performance real.** É melhor mostrar progresso constante do que esperar 30s no spinner.

5. **Documentar enquanto desenvolve.** Cada decisão arquitetural tem comentário no código explicando "por quê".

6. **Migrations SEMPRE versionadas.** SQLite hoje, Postgres amanhã. Toda mudança de schema vira arquivo numerado em `/migrations`.

7. **Anti-alucinação como feature, não bug.** O LLM tem que CITAR a transcrição quando afirma algo. Se não cita, ata não é confiável.

---

## 🚀 Como Rodar (depois do setup)

```bash
# Clone
git clone <repo>
cd eskuta

# Setup
npm install               # Frontend deps
cd src-python && pip install -r requirements.txt && cd ..

# Dev (frontend + backend + tauri rodando juntos)
npm run tauri dev

# Build de instalador
npm run tauri build
```

Saída do build: `src-tauri/target/release/bundle/`
- Windows: `.msi` e `.exe`
- macOS: `.dmg` e `.app`

Detalhes completos no relatório técnico.

---

## 📖 Documentos Relacionados

- **`RELATORIO_TECNICO.md`** — Mapa passo a passo do desenvolvimento, com critérios de aceite. **É o coração do projeto.**
- **`SCHEMA_BD.xlsx`** — Modelagem completa do banco de dados com migrations.

---

## 👋 Pra Quem Tá Lendo Isso Pela Primeira Vez

Se você é dev (humano ou IA) chegando agora no projeto:

1. Leia este documento até o fim (você tá quase lá)
2. Depois leia `RELATORIO_TECNICO.md` na ordem das etapas
3. Quando bater dúvida de modelagem, consulta `SCHEMA_BD.xlsx`
4. Não inventa. Se algo não tá documentado, pergunta antes de codar.

**Bem-vindo ao Eskuta. Vamos construir uma coisa boa.**
