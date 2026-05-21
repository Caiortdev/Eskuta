# 🛠️ Relatório Técnico — Projeto Eskuta

> **Este é o mapa do desenvolvimento.** Cada etapa tem objetivo, passo a passo, critério de aceite e riscos. Segue na ordem. Quando uma etapa termina e passa nos critérios de aceite, vai pra próxima.
>
> Se você é uma IA desenvolvendo: **não pule etapas, não invente arquitetura paralela**. Se algo não tá aqui, pergunta antes.

---

## 📑 Índice

- [Fase 0 — Setup do Ambiente](#fase-0--setup-do-ambiente)
- [Fase 1 — MVP: Upload de Arquivo](#fase-1--mvp-upload-de-arquivo)
  - [1.1 Estrutura base do projeto](#11-estrutura-base-do-projeto)
  - [1.2 Banco de dados SQLite + migrations](#12-banco-de-dados-sqlite--migrations)
  - [1.3 Pipeline de pré-processamento de áudio](#13-pipeline-de-pré-processamento-de-áudio)
  - [1.4 Camada de Transcrição com Fallback](#14-camada-de-transcrição-com-fallback)
  - [1.5 Camada de Diarização](#15-camada-de-diarização)
  - [1.6 Camada de LLM (Claude/GPT/Gemini)](#16-camada-de-llm-claudegptgemini)
  - [1.7 Arquitetura Anti-Alucinação](#17-arquitetura-anti-alucinação)
  - [1.8 System Prompts Profissionais](#18-system-prompts-profissionais)
  - [1.9 Pipeline de Geração da Ata](#19-pipeline-de-geração-da-ata)
  - [1.10 Frontend React: telas e fluxos](#110-frontend-react-telas-e-fluxos)
  - [1.11 Configuração de API Keys pelo usuário](#111-configuração-de-api-keys-pelo-usuário)
  - [1.12 Empacotamento e Distribuição (1 instalador)](#112-empacotamento-e-distribuição-1-instalador)
- [Fase 2 — Captura em Tempo Real](#fase-2--captura-em-tempo-real)
  - [2.1 Captura de áudio do sistema (Windows)](#21-captura-de-áudio-do-sistema-windows)
  - [2.2 Captura de áudio do sistema (macOS)](#22-captura-de-áudio-do-sistema-macos)
  - [2.3 Mix de microfone + sistema](#23-mix-de-microfone--sistema)
  - [2.4 Streaming "quase real-time" com chunks](#24-streaming-quase-real-time-com-chunks)
  - [2.5 UI durante reunião](#25-ui-durante-reunião)
  - [2.6 Reprocessamento pós-reunião](#26-reprocessamento-pós-reunião)
- [Fase 3 — Produção (App Pago)](#fase-3--produção-app-pago)
- [Apêndices](#apêndices)

---

# Fase 0 — Setup do Ambiente

> **Objetivo:** Ter um ambiente onde dá pra rodar Tauri + React + FastAPI tudo junto, com hot-reload, e gerar um instalador funcional (mesmo que vazio).

## Etapa 0.1 — Instalações Base

**Objetivo:** Garantir que todas as ferramentas estão na máquina do dev.

**Passo a passo:**

1. **Node.js 20.x ou superior**
   - Windows: baixar do site oficial
   - macOS: `brew install node@20`
   - Validar: `node --version` deve mostrar v20.x+

2. **Rust (toolchain mais recente)**
   - Comando: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
   - Validar: `rustc --version`

3. **Python 3.11.x** (importante: não usar 3.12 ou 3.13 ainda — incompatibilidades com pyannote)
   - Windows: instalador oficial, marcar "Add to PATH"
   - macOS: `brew install python@3.11`
   - Validar: `python3.11 --version`

4. **FFmpeg** (essencial pro pipeline de áudio)
   - Windows: baixar de ffmpeg.org e adicionar ao PATH
   - macOS: `brew install ffmpeg`
   - Validar: `ffmpeg -version`

5. **Tauri prerequisites**
   - Windows: Microsoft C++ Build Tools + WebView2 (já vem no Windows 11)
   - macOS: Xcode Command Line Tools (`xcode-select --install`)

6. **Git** (óbvio mas seja exaustivo)

**Critério de aceite:**
- [ ] Todos os comandos acima retornam versão sem erro
- [ ] `cargo --version` funciona
- [ ] `pip --version` funciona (Python 3.11)

---

## Etapa 0.2 — Criar Projeto Tauri Base

**Objetivo:** Ter um app Tauri + React rodando vazio.

**Passo a passo:**

1. Criar projeto com template oficial:
   ```bash
   npm create tauri-app@latest eskuta
   ```
   - Frontend: **React**
   - Variante: **TypeScript**
   - Package manager: **npm**

2. Entrar no projeto e instalar deps:
   ```bash
   cd eskuta
   npm install
   ```

3. Rodar em dev:
   ```bash
   npm run tauri dev
   ```

4. Verificar que janela abre com "Hello Tauri".

**Critério de aceite:**
- [ ] Janela do app abre sem erro
- [ ] Hot-reload funciona (mude texto no `App.tsx` e veja atualizar)
- [ ] `npm run tauri build` gera um instalador (mesmo que vazio) na pasta `src-tauri/target/release/bundle/`

---

## Etapa 0.3 — Adicionar TailwindCSS + Shadcn/UI

**Objetivo:** Setup de UI bonito desde o começo.

**Passo a passo:**

1. Instalar Tailwind:
   ```bash
   npm install -D tailwindcss@latest postcss autoprefixer
   npx tailwindcss init -p
   ```

2. Configurar `tailwind.config.js` apontando pra `./src/**/*.{ts,tsx}`.

3. Adicionar diretivas no `src/index.css`:
   ```css
   @tailwind base;
   @tailwind components;
   @tailwind utilities;
   ```

4. Instalar Shadcn/UI:
   ```bash
   npx shadcn@latest init
   ```
   - Style: **Default**
   - Base color: **Slate** (ou sua preferência)
   - CSS variables: **Yes**

5. Adicionar componentes que vamos usar bastante:
   ```bash
   npx shadcn@latest add button input dialog progress card tabs select textarea
   ```

**Critério de aceite:**
- [ ] Botão Shadcn renderiza no `App.tsx` sem erro
- [ ] Classes Tailwind funcionam
- [ ] Build não quebra

---

## Etapa 0.4 — Estruturar Pastas do Projeto

**Objetivo:** Organização de pastas clara desde o início.

**Estrutura final esperada:**

```
eskuta/
├── src/                          # Frontend React
│   ├── components/               # Componentes reutilizáveis
│   │   ├── ui/                   # Shadcn components
│   │   └── ...
│   ├── pages/                    # Telas
│   ├── hooks/                    # Custom React hooks
│   ├── lib/                      # Utilities, API client
│   ├── types/                    # TypeScript types
│   └── App.tsx
├── src-tauri/                    # Código Rust do Tauri
│   ├── src/
│   │   ├── main.rs
│   │   ├── audio/                # Captura de áudio (Fase 2)
│   │   ├── commands/             # Tauri commands expostos pro JS
│   │   └── ...
│   ├── Cargo.toml
│   └── tauri.conf.json
├── src-python/                   # Sidecar Python (FastAPI)
│   ├── app/
│   │   ├── main.py               # Entry point FastAPI
│   │   ├── api/                  # Rotas
│   │   ├── core/                 # Configs, settings
│   │   ├── services/             # Lógica de negócio
│   │   │   ├── audio/            # Pré-processamento
│   │   │   ├── transcription/    # STT + fallback
│   │   │   ├── diarization/      # pyannote
│   │   │   ├── llm/              # Claude/GPT/Gemini
│   │   │   └── minutes/          # Geração de ata
│   │   ├── db/                   # SQLite, migrations
│   │   ├── models/               # Pydantic models
│   │   └── utils/
│   ├── tests/
│   └── requirements.txt
├── migrations/                   # Migrations SQL (versionadas)
│   ├── 001_initial.sql
│   ├── 002_xxx.sql
│   └── ...
├── docs/                         # Documentação (esta pasta)
├── scripts/                      # Scripts auxiliares (build, etc)
└── package.json
```

**Passo a passo:**

1. Criar todas as pastas vazias com `.gitkeep` dentro
2. Mover `App.tsx`, `main.tsx` etc pra suas posições corretas
3. Atualizar `tsconfig.json` com `paths` se necessário (ex: `@/components`)

**Critério de aceite:**
- [ ] Estrutura de pastas igual à descrita
- [ ] App ainda roda com `npm run tauri dev`
- [ ] Imports usando alias `@/` funcionam

---

## Etapa 0.5 — Setup do Sidecar Python (FastAPI)

**Objetivo:** Ter um FastAPI mínimo rodando, que vai virar nosso backend embarcado.

**Passo a passo:**

1. Criar virtual env:
   ```bash
   cd src-python
   python3.11 -m venv venv
   source venv/bin/activate  # ou venv\Scripts\activate no Windows
   ```

2. Criar `requirements.txt` com deps básicas:
   ```txt
   fastapi==0.115.0
   uvicorn[standard]==0.32.0
   pydantic==2.9.0
   pydantic-settings==2.5.0
   python-multipart==0.0.12
   httpx==0.27.0
   sqlalchemy==2.0.35
   aiosqlite==0.20.0
   alembic==1.13.3
   loguru==0.7.2
   ```

3. Instalar:
   ```bash
   pip install -r requirements.txt
   ```

4. Criar `app/main.py`:
   ```python
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware

   app = FastAPI(title="Eskuta Sidecar", version="0.1.0")

   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:1420", "tauri://localhost"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )

   @app.get("/health")
   async def health():
       return {"status": "ok"}
   ```

5. Rodar:
   ```bash
   uvicorn app.main:app --reload --port 8765
   ```

6. Validar: abrir `http://localhost:8765/health` no browser, deve retornar `{"status":"ok"}`.

**Critério de aceite:**
- [ ] FastAPI sobe sem erro
- [ ] `/health` responde
- [ ] `/docs` (Swagger) carrega

---

## Etapa 0.6 — Integrar Sidecar Python ao Tauri

**Objetivo:** Quando o app Tauri abre, o FastAPI sobe junto automaticamente. Quando fecha, mata o processo.

**Passo a passo:**

1. **Empacotar o Python com PyInstaller pra ter um binário standalone:**

   Criar `src-python/build_sidecar.py`:
   ```python
   import PyInstaller.__main__
   import platform
   import os

   target = "eskuta-sidecar"
   if platform.system() == "Windows":
       target += ".exe"

   PyInstaller.__main__.run([
       'app/main.py',
       '--name', target,
       '--onefile',
       '--clean',
       '--noconfirm',
       # Adicione hidden imports se faltar algo
       '--hidden-import', 'uvicorn.logging',
       '--hidden-import', 'uvicorn.lifespan.on',
       '--hidden-import', 'uvicorn.protocols.http.auto',
       '--hidden-import', 'uvicorn.protocols.websockets.auto',
   ])
   ```

2. **Configurar Tauri pra usar como sidecar:**

   No `src-tauri/tauri.conf.json`, adicionar em `bundle`:
   ```json
   "externalBin": [
     "binaries/eskuta-sidecar"
   ]
   ```

3. **Inicializar o sidecar no `main.rs`:**

   ```rust
   use tauri::Manager;
   use tauri_plugin_shell::ShellExt;
   use tauri_plugin_shell::process::CommandEvent;

   #[cfg_attr(mobile, tauri::mobile_entry_point)]
   pub fn run() {
       tauri::Builder::default()
           .plugin(tauri_plugin_shell::init())
           .setup(|app| {
               let sidecar_command = app.shell()
                   .sidecar("eskuta-sidecar")
                   .expect("falha ao criar sidecar")
                   .args(["--port", "8765"]);

               let (mut rx, _child) = sidecar_command
                   .spawn()
                   .expect("falha ao spawn sidecar");

               // Loop pra capturar logs
               tauri::async_runtime::spawn(async move {
                   while let Some(event) = rx.recv().await {
                       if let CommandEvent::Stdout(line) = event {
                           println!("[sidecar] {}", String::from_utf8_lossy(&line));
                       }
                   }
               });

               Ok(())
           })
           .run(tauri::generate_context!())
           .expect("erro rodando Tauri");
   }
   ```

4. **Script de build:**

   Criar `scripts/build.sh` (e `.bat` pra Windows) que:
   ```bash
   #!/bin/bash
   set -e
   cd src-python
   python build_sidecar.py
   cp dist/eskuta-sidecar ../src-tauri/binaries/eskuta-sidecar-x86_64-pc-windows-msvc.exe  # ajustar target triple
   cd ..
   npm run tauri build
   ```

5. **Health check de inicialização:**

   No frontend, no `App.tsx`, fazer fetch periódico até `/health` responder, antes de mostrar UI principal.

**Critério de aceite:**
- [ ] `npm run tauri dev` sobe Tauri + Python juntos automaticamente
- [ ] Fechar a janela mata o processo Python (verificar no gerenciador de tarefas)
- [ ] Frontend consegue chamar `http://localhost:8765/health` e receber resposta
- [ ] Build de produção gera UM instalador que ao ser instalado e aberto, sobe tudo automaticamente

**Riscos e mitigações:**

| Risco | Mitigação |
|-------|-----------|
| PyInstaller não inclui módulo necessário | Adicionar em `--hidden-import` |
| Porta 8765 ocupada | Implementar busca por porta livre dinâmica |
| Python crasha silenciosamente | Capturar stderr no Rust e logar |
| Antivírus bloqueia o sidecar.exe | Assinar binário com certificado (custa $$, deixar pra produção) |

---

# Fase 1 — MVP: Upload de Arquivo

> **Objetivo da fase:** Você consegue arrastar um MP3/MP4 pra dentro do app, esperar ~3 minutos, e receber uma ata estruturada profissional.

## 1.1 Estrutura base do projeto

### Etapa 1.1.1 — Configurar logging estruturado

**Objetivo:** Logs decentes desde o início (vai salvar sua vida no debug).

**Passo a passo:**

1. No Python, configurar Loguru em `src-python/app/core/logging.py`:
   ```python
   from loguru import logger
   import sys
   from pathlib import Path

   LOG_DIR = Path.home() / ".eskuta" / "logs"
   LOG_DIR.mkdir(parents=True, exist_ok=True)

   logger.remove()  # remove handler padrão
   logger.add(sys.stderr, level="INFO", colorize=True)
   logger.add(
       LOG_DIR / "eskuta_{time}.log",
       rotation="50 MB",
       retention="14 days",
       level="DEBUG",
       enqueue=True,  # thread-safe
   )
   ```

2. Usar em tudo:
   ```python
   from loguru import logger

   logger.info("Processando arquivo", file=path, size=size)
   ```

**Critério de aceite:**
- [ ] Logs aparecem no console quando rodando
- [ ] Arquivo de log é criado em `~/.eskuta/logs/`
- [ ] Rotação funciona (testar com arquivo grande)

---

### Etapa 1.1.2 — Sistema de configuração (Settings)

**Objetivo:** Centralizar todas as configs em um único lugar, com .env como override.

**Passo a passo:**

1. Criar `src-python/app/core/settings.py`:
   ```python
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from pathlib import Path

   class Settings(BaseSettings):
       model_config = SettingsConfigDict(
           env_file=".env",
           env_file_encoding="utf-8",
           extra="ignore",
       )

       # Paths
       APP_DIR: Path = Path.home() / ".eskuta"
       DB_PATH: Path = APP_DIR / "eskuta.db"
       UPLOADS_DIR: Path = APP_DIR / "uploads"
       PROCESSED_DIR: Path = APP_DIR / "processed"

       # APIs (preenchidas pelo usuário via UI, NÃO via .env em produção)
       GROQ_API_KEY: str = ""
       ASSEMBLYAI_API_KEY: str = ""
       ANTHROPIC_API_KEY: str = ""
       OPENAI_API_KEY: str = ""
       GOOGLE_API_KEY: str = ""

       # LLM preferido pelo usuário
       PREFERRED_LLM: str = "claude"  # claude | gpt | gemini

       # Limites
       MAX_AUDIO_MB: int = 500
       CHUNK_DURATION_SEC: int = 600  # 10 min por chunk
       MAX_PARALLEL_CHUNKS: int = 4

       def ensure_dirs(self):
           for d in [self.APP_DIR, self.UPLOADS_DIR, self.PROCESSED_DIR]:
               d.mkdir(parents=True, exist_ok=True)

   settings = Settings()
   settings.ensure_dirs()
   ```

2. **Importante:** Em produção, as API keys NÃO vêm de `.env`. Elas são armazenadas criptografadas no banco. O `.env` é só pra desenvolvimento.

**Critério de aceite:**
- [ ] `from app.core.settings import settings` funciona em qualquer lugar
- [ ] Diretórios são criados na primeira execução
- [ ] Validação Pydantic falha gracefully se valor inválido

---

## 1.2 Banco de dados SQLite + migrations

### Etapa 1.2.1 — Setup do SQLAlchemy + Alembic

**Objetivo:** ORM funcionando e sistema de migrations versionado e compatível com Postgres no futuro.

**Passo a passo:**

1. Criar `src-python/app/db/database.py`:
   ```python
   from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
   from sqlalchemy.orm import DeclarativeBase
   from app.core.settings import settings

   class Base(DeclarativeBase):
       pass

   engine = create_async_engine(
       f"sqlite+aiosqlite:///{settings.DB_PATH}",
       echo=False,
       future=True,
   )

   AsyncSessionLocal = async_sessionmaker(
       engine, class_=AsyncSession, expire_on_commit=False
   )

   async def get_db():
       async with AsyncSessionLocal() as session:
           try:
               yield session
           finally:
               await session.close()
   ```

2. Inicializar Alembic:
   ```bash
   cd src-python
   alembic init -t async migrations_alembic
   ```

3. Configurar `alembic.ini` e `env.py` pra apontar pro nosso `Base.metadata`.

4. **Regra crítica:** As migrations escritas pelo Alembic vão pra `migrations_alembic/versions/`. Mas a gente ALSO mantém uma cópia em SQL puro em `/migrations/` na raiz do projeto, compatível com Postgres, pra facilitar futura migração.

5. Criar `/migrations/001_initial.sql` (manualmente, paralelo ao Alembic — sim, é redundante, é proposital):
   - Esse arquivo SQL puro vai usar sintaxe compatível com Postgres
   - Quando hora de migrar pra produção, basta rodar esse SQL no Postgres

**Critério de aceite:**
- [ ] `alembic upgrade head` cria as tabelas no SQLite
- [ ] Arquivo `001_initial.sql` existe e é válido em Postgres (testar em container Docker)
- [ ] Conexão async funciona em endpoints FastAPI

---

### Etapa 1.2.2 — Modelar todas as tabelas

**Veja o arquivo `SCHEMA_BD.xlsx` pra spec completa.** Aqui só listo o que precisa ser criado:

Tabelas:
1. `meetings` — uma reunião processada
2. `transcripts` — transcrição bruta de uma reunião
3. `transcript_segments` — segmentos com timestamp e speaker
4. `minutes` — atas geradas
5. `minute_versions` — histórico de versões de uma ata
6. `action_items` — ações extraídas
7. `decisions` — decisões extraídas
8. `api_keys` — chaves criptografadas dos providers
9. `processing_jobs` — fila/estado de processamento assíncrono
10. `audit_log` — auditoria de operações sensíveis
11. `user_preferences` — preferências (LLM preferido, idioma da ata, etc)

**Passo a passo:**

1. Pra cada tabela do schema, criar um model SQLAlchemy em `app/db/models/`
2. Rodar `alembic revision --autogenerate -m "initial schema"`
3. Revisar a migration gerada (Alembic não é perfeito)
4. Aplicar com `alembic upgrade head`
5. Copiar SQL equivalente pra `/migrations/001_initial.sql`

**Critério de aceite:**
- [ ] Todas as tabelas criadas no SQLite
- [ ] `001_initial.sql` cria tabelas idênticas no Postgres (testado)
- [ ] Relacionamentos (FKs) funcionam
- [ ] Índices criados nas colunas certas (ver schema)

---

## 1.3 Pipeline de pré-processamento de áudio

> **Objetivo:** Transformar qualquer arquivo de entrada num MP3 limpo, otimizado pra transcrição, dividido em chunks gerenciáveis.

### Etapa 1.3.1 — Conversão e compressão com ffmpeg

**Objetivo:** Receber MP3/MP4/WAV/M4A/etc e produzir MP3 16kHz mono 32kbps.

**Passo a passo:**

1. Instalar dep: `pip install ffmpeg-python==0.2.0`

2. Criar `app/services/audio/converter.py`:
   ```python
   import ffmpeg
   from pathlib import Path
   from loguru import logger

   async def convert_to_optimized_mp3(input_path: Path, output_path: Path) -> Path:
       """
       Converte qualquer formato de áudio/vídeo pra MP3 otimizado pra voz.
       - 16kHz (taxa que Whisper usa internamente)
       - Mono (voz não precisa estéreo)
       - 32kbps (mais que suficiente pra voz inteligível)
       
       Reduz drasticamente o tamanho. 3h de reunião em MP4 (1.5GB) vira ~40MB.
       """
       try:
           (
               ffmpeg
               .input(str(input_path))
               .output(
                   str(output_path),
                   format='mp3',
                   acodec='libmp3lame',
                   ac=1,           # mono
                   ar=16000,       # 16kHz
                   audio_bitrate='32k',
                   loglevel='error',
               )
               .overwrite_output()
               .run(capture_stdout=True, capture_stderr=True)
           )
           logger.info(f"Áudio convertido: {input_path.name} -> {output_path.name}")
           return output_path
       except ffmpeg.Error as e:
           logger.error(f"Erro ffmpeg: {e.stderr.decode()}")
           raise
   ```

3. Wrapper async-safe (ffmpeg é blocking, então roda em thread):
   ```python
   import asyncio

   async def convert_async(input_path, output_path):
       loop = asyncio.get_event_loop()
       return await loop.run_in_executor(None, convert_to_optimized_mp3, input_path, output_path)
   ```

**Critério de aceite:**
- [ ] MP4 de 1GB vira MP3 < 50MB
- [ ] MP3 de qualquer bitrate vira MP3 16kHz mono 32kbps
- [ ] Função é async e não bloqueia o event loop
- [ ] Erros do ffmpeg são logados claramente

---

### Etapa 1.3.2 — VAD (Voice Activity Detection) com Silero

**Objetivo:** Remover silêncios e ruídos não-fala antes de mandar pro Whisper. Reduz tamanho, acelera processamento, **reduz alucinação**.

**Passo a passo:**

1. Instalar dep: `pip install silero-vad==5.1.2`

2. Criar `app/services/audio/vad.py`:
   ```python
   import torch
   from pathlib import Path
   from typing import List, Tuple
   from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
   from loguru import logger

   _model = None

   def _get_model():
       global _model
       if _model is None:
           _model = load_silero_vad()
       return _model

   def detect_speech_segments(audio_path: Path) -> List[Tuple[float, float]]:
       """
       Retorna lista de (start_sec, end_sec) com APENAS os trechos de fala.
       """
       model = _get_model()
       wav = read_audio(str(audio_path), sampling_rate=16000)
       speech_timestamps = get_speech_timestamps(
           wav, model,
           sampling_rate=16000,
           min_speech_duration_ms=250,
           min_silence_duration_ms=500,
           threshold=0.5,
       )
       segments = [(s['start'] / 16000, s['end'] / 16000) for s in speech_timestamps]
       logger.info(f"VAD detectou {len(segments)} segmentos de fala")
       return segments
   ```

3. Função auxiliar pra cortar o áudio mantendo só os segmentos de fala:
   ```python
   def remove_silence(input_path: Path, output_path: Path) -> Path:
       segments = detect_speech_segments(input_path)
       # Usar ffmpeg pra conceskutar só os segmentos de fala
       # (construção do filter_complex)
       ...
   ```

**Critério de aceite:**
- [ ] Áudio de 1h com 20% de silêncio vira áudio de ~48min
- [ ] Timestamps fazem sentido (validar manualmente em 2-3 amostras)
- [ ] Processamento de 1h leva < 30s

---

### Etapa 1.3.3 — Chunking inteligente

**Objetivo:** Dividir áudios longos em chunks de ~10 minutos, cortando em pausas naturais (silêncios detectados pelo VAD), nunca no meio de uma palavra.

**Passo a passo:**

1. Criar `app/services/audio/chunker.py`:
   ```python
   from typing import List
   from pathlib import Path
   from dataclasses import dataclass

   @dataclass
   class AudioChunk:
       index: int
       file_path: Path
       start_sec: float
       end_sec: float
       duration_sec: float

   def chunk_audio_smart(
       audio_path: Path,
       speech_segments: List[Tuple[float, float]],
       max_chunk_duration: int = 600,  # 10 min
       output_dir: Path = None,
   ) -> List[AudioChunk]:
       """
       Estratégia:
       1. Começa um chunk no segmento 0
       2. Vai adicionando segmentos até atingir ~max_chunk_duration
       3. Quando ultrapassar, fecha o chunk no último silêncio detectado
       4. Salva como MP3 individual
       """
       chunks = []
       current_start = 0
       current_segments = []
       chunk_idx = 0

       for seg_start, seg_end in speech_segments:
           if seg_end - current_start > max_chunk_duration and current_segments:
               # Fecha o chunk atual
               chunk_path = _save_chunk(audio_path, current_segments, chunk_idx, output_dir)
               chunks.append(AudioChunk(
                   index=chunk_idx,
                   file_path=chunk_path,
                   start_sec=current_start,
                   end_sec=current_segments[-1][1],
                   duration_sec=current_segments[-1][1] - current_start,
               ))
               chunk_idx += 1
               current_start = seg_start
               current_segments = []
           current_segments.append((seg_start, seg_end))

       # Último chunk
       if current_segments:
           chunk_path = _save_chunk(audio_path, current_segments, chunk_idx, output_dir)
           chunks.append(AudioChunk(...))

       return chunks
   ```

**Critério de aceite:**
- [ ] Áudio de 3h vira ~18 chunks de ~10 min cada
- [ ] Nenhum chunk passa de 25MB (limite do Groq)
- [ ] Cortes acontecem em silêncios, nunca no meio de fala
- [ ] Timestamps relativos são preservados pra reconstrução

---

## 1.4 Camada de Transcrição com Fallback

> **Objetivo:** Sistema robusto que tenta Groq primeiro, cai pra AssemblyAI se falhar. Interface única pro resto do sistema.

### Etapa 1.4.1 — Padrão Adapter pra providers

**Objetivo:** Cada provider tem sua API, mas o resto do sistema só conhece UMA interface.

**Passo a passo:**

1. Criar interface base em `app/services/transcription/base.py`:
   ```python
   from abc import ABC, abstractmethod
   from pathlib import Path
   from dataclasses import dataclass
   from typing import List, Optional

   @dataclass
   class TranscriptSegment:
       start_sec: float
       end_sec: float
       text: str
       speaker: Optional[str] = None
       confidence: Optional[float] = None

   @dataclass
   class TranscriptionResult:
       full_text: str
       segments: List[TranscriptSegment]
       language: str
       duration_sec: float
       provider_used: str  # "groq" | "assemblyai"
       cost_usd: float = 0.0

   class TranscriptionProvider(ABC):
       @abstractmethod
       async def transcribe(self, audio_path: Path, language: str = "pt") -> TranscriptionResult:
           ...

       @abstractmethod
       def is_available(self) -> bool:
           """Verifica se temos API key e está acessível."""
           ...

       @property
       @abstractmethod
       def name(self) -> str:
           ...
   ```

2. Implementar adapter Groq em `app/services/transcription/groq_provider.py`:
   ```python
   from groq import AsyncGroq
   from app.services.transcription.base import TranscriptionProvider, TranscriptionResult
   from app.services.keys import get_api_key  # implementar
   import time

   class GroqProvider(TranscriptionProvider):
       name = "groq"

       def is_available(self) -> bool:
           return bool(get_api_key("groq"))

       async def transcribe(self, audio_path, language="pt"):
           client = AsyncGroq(api_key=get_api_key("groq"))
           start = time.time()
           with open(audio_path, "rb") as f:
               response = await client.audio.transcriptions.create(
                   file=(audio_path.name, f.read()),
                   model="whisper-large-v3-turbo",
                   language=language,
                   response_format="verbose_json",
                   temperature=0.0,  # importante: zero pra reduzir alucinação
               )

           # Parsear segments do verbose_json
           segments = [
               TranscriptSegment(
                   start_sec=s["start"],
                   end_sec=s["end"],
                   text=s["text"].strip(),
                   confidence=s.get("avg_logprob"),
               )
               for s in response.segments
           ]

           return TranscriptionResult(
               full_text=response.text,
               segments=segments,
               language=response.language,
               duration_sec=response.duration,
               provider_used="groq",
               cost_usd=response.duration / 3600 * 0.04,  # $0.04/hr no tier pago
           )
   ```

3. Implementar adapter AssemblyAI em `app/services/transcription/assemblyai_provider.py` (similar, com API deles).

**Critério de aceite:**
- [ ] Ambos providers implementam a mesma interface
- [ ] Resultado normalizado idêntico independente do provider
- [ ] `is_available()` retorna `False` quando API key faltando

---

### Etapa 1.4.2 — Router com Fallback Inteligente

**Objetivo:** Sistema que tenta primário, faz retry exponencial, e cai pro secundário se necessário.

**Passo a passo:**

1. Criar `app/services/transcription/router.py`:
   ```python
   from typing import List
   from app.services.transcription.base import TranscriptionProvider, TranscriptionResult
   from app.services.transcription.groq_provider import GroqProvider
   from app.services.transcription.assemblyai_provider import AssemblyAIProvider
   from loguru import logger
   import asyncio

   class TranscriptionRouter:
       def __init__(self):
           self.providers: List[TranscriptionProvider] = [
               GroqProvider(),
               AssemblyAIProvider(),
           ]

       async def transcribe(self, audio_path, language="pt") -> TranscriptionResult:
           last_error = None
           for provider in self.providers:
               if not provider.is_available():
                   logger.warning(f"Provider {provider.name} não disponível, pulando")
                   continue

               for attempt in range(3):
                   try:
                       logger.info(f"Tentando {provider.name} (tentativa {attempt+1})")
                       return await provider.transcribe(audio_path, language)
                   except RateLimitError:
                       wait = 2 ** attempt
                       logger.warning(f"Rate limit em {provider.name}, esperando {wait}s")
                       await asyncio.sleep(wait)
                   except Exception as e:
                       logger.error(f"Erro em {provider.name}: {e}")
                       last_error = e
                       break  # vai pro próximo provider

           raise RuntimeError(f"Todos providers falharam. Último erro: {last_error}")
   ```

2. Endpoint FastAPI em `app/api/transcription.py`:
   ```python
   from fastapi import APIRouter, BackgroundTasks
   from app.services.transcription.router import TranscriptionRouter

   router = APIRouter(prefix="/transcribe")
   transcription_router = TranscriptionRouter()

   @router.post("/start")
   async def start_transcription(meeting_id: str, background: BackgroundTasks):
       background.add_task(process_meeting, meeting_id)
       return {"status": "processing", "meeting_id": meeting_id}
   ```

**Critério de aceite:**
- [ ] Com Groq disponível, sempre tenta Groq primeiro
- [ ] Quando Groq retorna 429 (rate limit), retry com backoff exponencial
- [ ] Se Groq falhar 3x, cai pra AssemblyAI
- [ ] Resultado final guarda qual provider foi usado
- [ ] Logs deixam claro o que aconteceu em cada tentativa

---

### Etapa 1.4.3 — Paralelização de chunks

**Objetivo:** Transcrever 18 chunks ao mesmo tempo, respeitando rate limit.

**Passo a passo:**

1. Criar `app/services/transcription/parallel.py`:
   ```python
   import asyncio
   from app.core.settings import settings

   async def transcribe_chunks_parallel(chunks, router):
       semaphore = asyncio.Semaphore(settings.MAX_PARALLEL_CHUNKS)

       async def transcribe_one(chunk):
           async with semaphore:
               return await router.transcribe(chunk.file_path)

       results = await asyncio.gather(
           *[transcribe_one(c) for c in chunks],
           return_exceptions=True,
       )
       return results
   ```

2. Mesclar resultados respeitando timestamps absolutos do áudio original:
   ```python
   def merge_chunk_transcriptions(chunks, results):
       all_segments = []
       full_text = []
       for chunk, result in zip(chunks, results):
           for seg in result.segments:
               # Ajustar timestamp pro áudio original
               all_segments.append(TranscriptSegment(
                   start_sec=chunk.start_sec + seg.start_sec,
                   end_sec=chunk.start_sec + seg.end_sec,
                   text=seg.text,
                   ...
               ))
           full_text.append(result.full_text)
       return TranscriptionResult(
           full_text=" ".join(full_text),
           segments=all_segments,
           ...
       )
   ```

**Critério de aceite:**
- [ ] 18 chunks transcritos em paralelo (max 4 simultâneos)
- [ ] Semáforo respeitado (verificar logs)
- [ ] Timestamps absolutos batem com o áudio original
- [ ] Nenhuma fala "perdida" entre chunks (validar com amostra)

---

## 1.5 Camada de Diarização

> **Objetivo:** Identificar QUEM falou o quê, usando pyannote local. Opcional no MVP, mas a arquitetura prevê.

### Etapa 1.5.1 — Setup do pyannote.audio

**Passo a passo:**

1. Instalar:
   ```bash
   pip install pyannote.audio==3.3.2
   ```

2. Aceitar termos no Hugging Face e gerar token:
   - User acessa `https://huggingface.co/pyannote/speaker-diarization-3.1` e aceita
   - Gera token de acesso
   - **Importante:** o token é da configuração do APP, não do usuário final. Documentar isso pro instalador.

3. Criar `app/services/diarization/pyannote_service.py`:
   ```python
   from pyannote.audio import Pipeline
   from pathlib import Path
   from dataclasses import dataclass
   from typing import List

   @dataclass
   class SpeakerSegment:
       start_sec: float
       end_sec: float
       speaker_id: str  # "SPEAKER_00", "SPEAKER_01", ...

   _pipeline = None

   def _get_pipeline():
       global _pipeline
       if _pipeline is None:
           _pipeline = Pipeline.from_pretrained(
               "pyannote/speaker-diarization-3.1",
               use_auth_token=os.getenv("HF_TOKEN"),
           )
       return _pipeline

   def diarize(audio_path: Path) -> List[SpeakerSegment]:
       pipeline = _get_pipeline()
       diarization = pipeline(str(audio_path))
       segments = []
       for turn, _, speaker in diarization.itertracks(yield_label=True):
           segments.append(SpeakerSegment(
               start_sec=turn.start,
               end_sec=turn.end,
               speaker_id=speaker,
           ))
       return segments
   ```

**Critério de aceite:**
- [ ] Modelo baixa na primeira execução (~500MB)
- [ ] Diarização de 1h leva < 5 min em CPU decente
- [ ] Speakers identificados batem com a realidade (validar 2-3 amostras)

---

### Etapa 1.5.2 — Merge Diarização + Transcrição

**Objetivo:** Combinar saídas do Whisper (texto + timestamps) e pyannote (speakers + timestamps).

**Passo a passo:**

1. Criar `app/services/diarization/merger.py`:
   ```python
   def merge_transcription_and_diarization(
       transcription_segments: List[TranscriptSegment],
       speaker_segments: List[SpeakerSegment],
   ) -> List[TranscriptSegment]:
       """
       Pra cada segmento de transcrição, encontra o speaker que dominou
       aquele intervalo de tempo na diarização.
       """
       result = []
       for ts in transcription_segments:
           best_speaker = None
           best_overlap = 0
           for sp in speaker_segments:
               overlap = max(0, min(ts.end_sec, sp.end_sec) - max(ts.start_sec, sp.start_sec))
               if overlap > best_overlap:
                   best_overlap = overlap
                   best_speaker = sp.speaker_id
           result.append(TranscriptSegment(
               start_sec=ts.start_sec,
               end_sec=ts.end_sec,
               text=ts.text,
               speaker=best_speaker,
               confidence=ts.confidence,
           ))
       return result
   ```

**Critério de aceite:**
- [ ] Cada segmento de transcrição tem um speaker atribuído
- [ ] Speakers diferentes em momentos diferentes da reunião (validar)
- [ ] Quando há sobreposição, prevalece o speaker dominante

---

### Etapa 1.5.3 — Mapeamento de Speakers Anônimos pra Nomes

**Objetivo:** "SPEAKER_00" não ajuda ninguém. Permitir que o usuário renomeie pra "João", "Maria" depois.

**Passo a passo:**

1. UI: depois da transcrição, mostrar amostras de fala de cada speaker e pedir pro usuário nomear
2. Salvar mapeamento na tabela `meetings.speaker_map` (JSON)
3. Aplicar nomes ao gerar a ata

**Critério de aceite:**
- [ ] Usuário consegue renomear speakers
- [ ] Ata gerada usa nomes em vez de SPEAKER_XX
- [ ] Mapeamento persiste entre execuções

---

## 1.6 Camada de LLM (Claude/GPT/Gemini)

> **Objetivo:** Suportar 3 providers de LLM com a mesma interface, deixando o usuário escolher qual usar (e plugar a key dele).

### Etapa 1.6.1 — Interface base e adapters

**Passo a passo:**

1. Interface em `app/services/llm/base.py`:
   ```python
   from abc import ABC, abstractmethod
   from dataclasses import dataclass
   from typing import List, Optional, Dict, Any

   @dataclass
   class LLMMessage:
       role: str  # "system" | "user" | "assistant"
       content: str

   @dataclass
   class LLMResponse:
       content: str
       provider: str
       model: str
       tokens_input: int
       tokens_output: int
       cost_usd: float

   class LLMProvider(ABC):
       @abstractmethod
       async def complete(
           self,
           messages: List[LLMMessage],
           max_tokens: int = 4096,
           temperature: float = 0.3,
           response_format: Optional[Dict] = None,  # pra JSON mode
       ) -> LLMResponse:
           ...

       @abstractmethod
       def is_available(self) -> bool:
           ...

       @property
       @abstractmethod
       def name(self) -> str:
           ...

       @property
       @abstractmethod
       def default_model(self) -> str:
           ...
   ```

2. Implementar `ClaudeProvider`, `GPTProvider`, `GeminiProvider` em arquivos separados.

3. Cada um usa SDK oficial:
   - `anthropic` pra Claude
   - `openai` pra GPT
   - `google-generativeai` pra Gemini

4. **Modelos padrão recomendados (revisar a cada 3 meses):**
   - Claude: `claude-sonnet-4-5` (melhor custo-benefício pra raciocínio)
   - GPT: `gpt-4.1` ou `gpt-5-mini`
   - Gemini: `gemini-2.5-flash`

**Critério de aceite:**
- [ ] Os 3 providers implementam a mesma interface
- [ ] Cada um retorna `LLMResponse` normalizado
- [ ] JSON mode funciona em todos (necessário pra ata estruturada)

---

### Etapa 1.6.2 — Router de LLM (seleção pelo usuário)

**Passo a passo:**

1. Criar `app/services/llm/router.py`:
   ```python
   from app.services.llm.base import LLMProvider
   from app.services.llm.claude_provider import ClaudeProvider
   from app.services.llm.gpt_provider import GPTProvider
   from app.services.llm.gemini_provider import GeminiProvider
   from app.core.settings import settings

   class LLMRouter:
       def __init__(self):
           self.providers = {
               "claude": ClaudeProvider(),
               "gpt": GPTProvider(),
               "gemini": GeminiProvider(),
           }

       def get_provider(self, preferred: str = None) -> LLMProvider:
           # 1. Usa preferência do usuário se disponível
           # 2. Fallback pra config padrão
           # 3. Fallback pra qualquer um disponível
           name = preferred or settings.PREFERRED_LLM
           provider = self.providers.get(name)
           if provider and provider.is_available():
               return provider
           # Tentar outros
           for p in self.providers.values():
               if p.is_available():
                   return p
           raise RuntimeError("Nenhum LLM disponível. Configure ao menos uma API key.")
   ```

**Critério de aceite:**
- [ ] Usuário consegue escolher provider via setting
- [ ] Se provider escolhido não tem key, sistema avisa e oferece outro
- [ ] Troca de provider é transparente pro resto do código

---

## 1.7 Arquitetura Anti-Alucinação

> **A coisa mais importante desta seção:** garantir que a ata gerada está ANCORADA na transcrição, não inventada pelo LLM.

### Etapa 1.7.1 — Princípios anti-alucinação

A gente vai aplicar 6 técnicas combinadas:

**1. Temperature zero ou muito baixa**
- STT: `temperature=0`
- LLM: `temperature=0.2` (precisa de um pouco pra fluidez na escrita, mas nada criativo)

**2. Citação obrigatória de evidências**
- Toda decisão / action item / fato afirmado pela ata DEVE incluir o trecho exato da transcrição que originou
- Se LLM não consegue citar, deixa em branco (não inventa)

**3. Output estruturado (JSON Schema rigoroso)**
- LLM responde em JSON com campos previsíveis
- Campos vazios = `null` ou `[]`, NUNCA texto criativo

**4. Validação cruzada (LLM-as-judge)**
- Depois da ata, segunda chamada de LLM verifica se ata bate com transcrição
- Se encontra inconsistência, regenera

**5. Few-shot com exemplos concretos**
- Mostrar pro LLM 1-2 exemplos de ata boa antes de pedir a nova

**6. Chain-of-thought explícito**
- LLM "raciocina" antes de produzir output final

### Etapa 1.7.2 — Implementação do JSON Schema

**Passo a passo:**

1. Criar `app/services/minutes/schemas.py`:
   ```python
   from pydantic import BaseModel, Field
   from typing import List, Optional
   from datetime import datetime

   class Evidence(BaseModel):
       """Trecho da transcrição que justifica uma afirmação."""
       quote: str = Field(description="Texto exato da transcrição")
       speaker: Optional[str] = Field(description="Quem disse")
       timestamp_sec: Optional[float] = Field(description="Quando foi dito (segundos)")

   class ActionItem(BaseModel):
       description: str = Field(description="Ação a ser executada")
       assigned_to: Optional[str] = Field(description="Nome do responsável, ou null se não mencionado")
       deadline: Optional[str] = Field(description="Prazo mencionado, ou null")
       evidence: Evidence = Field(description="Trecho que originou esta ação")

   class Decision(BaseModel):
       description: str
       evidence: Evidence

   class Topic(BaseModel):
       title: str
       summary: str = Field(description="Resumo em até 3 frases, NUNCA invente")
       evidence: Evidence

   class MinutesOutput(BaseModel):
       """Schema obrigatório do output do LLM."""
       title: str
       date: str
       participants: List[str] = Field(description="Apenas nomes EXPLICITAMENTE mencionados")
       executive_summary: str = Field(description="2-4 frases")
       topics: List[Topic]
       decisions: List[Decision]
       action_items: List[ActionItem]
       open_questions: List[str] = Field(description="Pontos em aberto, sem resolução")
   ```

2. Forçar uso do schema na chamada do LLM:
   ```python
   # Claude
   response = await client.messages.create(
       model="claude-sonnet-4-5",
       max_tokens=4096,
       system=SYSTEM_PROMPT,
       messages=[{"role": "user", "content": user_prompt}],
       # Não tem JSON mode estrito como GPT, mas o prompt + schema no system bastam
   )

   # GPT
   response = await client.chat.completions.create(
       model="gpt-4.1",
       response_format={"type": "json_object"},
       ...
   )
   ```

3. Validar com Pydantic — se LLM mandou JSON inválido, regerar:
   ```python
   try:
       minutes = MinutesOutput.model_validate_json(response.content)
   except ValidationError as e:
       logger.warning(f"LLM mandou JSON inválido: {e}")
       # Retry com prompt corretivo
   ```

**Critério de aceite:**
- [ ] LLM sempre retorna JSON parseável
- [ ] Todos os campos opcionais aparecem como `null` quando aplicável (não inventados)
- [ ] Todo `action_item` tem `evidence` obrigatório
- [ ] Validação Pydantic falha = retry automático até 2x

---

### Etapa 1.7.3 — Validador de Evidências

**Objetivo:** Garantir que toda `evidence.quote` está REALMENTE na transcrição.

**Passo a passo:**

1. Criar `app/services/minutes/validator.py`:
   ```python
   from rapidfuzz import fuzz

   def validate_evidence(quote: str, transcript_text: str, threshold: int = 85) -> bool:
       """
       Verifica se a quote do LLM está no transcript original.
       Usa fuzzy match porque o LLM pode ter normalizado pontuação.
       """
       # Busca janela deslizante
       quote_len = len(quote)
       transcript_lower = transcript_text.lower()
       quote_lower = quote.lower()

       # Match exato primeiro (rápido)
       if quote_lower in transcript_lower:
           return True

       # Match fuzzy se não bateu exato
       # (busca melhor janela)
       best_score = 0
       step = max(50, quote_len // 4)
       for i in range(0, len(transcript_text) - quote_len, step):
           window = transcript_lower[i:i + quote_len + 50]
           score = fuzz.partial_ratio(quote_lower, window)
           if score > best_score:
               best_score = score

       return best_score >= threshold

   def validate_minutes(minutes: MinutesOutput, transcript_text: str) -> List[str]:
       """Retorna lista de problemas encontrados."""
       problems = []
       for item in minutes.action_items:
           if not validate_evidence(item.evidence.quote, transcript_text):
               problems.append(f"Action item sem evidência válida: {item.description}")
       for dec in minutes.decisions:
           if not validate_evidence(dec.evidence.quote, transcript_text):
               problems.append(f"Decisão sem evidência válida: {dec.description}")
       return problems
   ```

2. Instalar dep: `pip install rapidfuzz==3.10.0`

3. No pipeline da ata: depois de gerar, validar. Se tem problemas, regerar com prompt corretivo destacando os problemas encontrados.

**Critério de aceite:**
- [ ] Quotes inventadas são detectadas
- [ ] Quotes reais (mesmo com pequena normalização) passam
- [ ] Threshold 85% é bom equilíbrio (testar com amostras)

---

## 1.8 System Prompts Profissionais

> **Aqui mora 80% da qualidade da ata.** Cada palavra do prompt foi pensada. Documentar com comentários.

### Etapa 1.8.1 — System Prompt principal

**Passo a passo:**

1. Criar `app/services/minutes/prompts.py`:

```python
SYSTEM_PROMPT_MINUTES = """Você é Eskuta, uma assistente especialista em criar atas de reunião profissionais em português brasileiro.

# SEU PAPEL
Você recebe a TRANSCRIÇÃO BRUTA de uma reunião e produz uma ATA ESTRUTURADA em JSON.

# REGRAS INVIOLÁVEIS

1. **NUNCA INVENTE INFORMAÇÃO.** Se algo não está EXPLICITAMENTE na transcrição, use null ou array vazio.
   - Nomes de pessoas: só inclua se foram chamados pelo nome na conversa
   - Prazos: só inclua se foi dito explicitamente uma data ou referência temporal
   - Responsáveis: só atribua se foi designado nominalmente
   - Decisões: só registre se houve afirmação clara, não suposição

2. **TODA AFIRMAÇÃO PRECISA DE EVIDÊNCIA.** Cada decisão, action item e tópico DEVE incluir o campo "evidence" com a frase exata da transcrição que originou. Se você não consegue citar literalmente, NÃO inclua o item.

3. **PORTUGUÊS BRASILEIRO NATURAL.** Não use português europeu. Não force formalidade excessiva. Seja claro e objetivo, como um secretário executivo experiente.

4. **IGNORE RUÍDO LINGUÍSTICO.** "Ééé", "tipo", "né", "então" — você processa o conteúdo, não a forma.

5. **PRESERVE NÚMEROS EXATOS.** Valores, datas, percentuais, prazos — copie literalmente da transcrição.

6. **AÇÃO IS NOT IGUAL A DECISÃO.**
   - Decisão: algo que foi resolvido na reunião ("Aprovamos o orçamento X")
   - Action item: algo que ALGUÉM precisa fazer DEPOIS da reunião ("João vai falar com o cliente")

# PROCESSO MENTAL (faça nesta ordem)

Antes de produzir a resposta, raciocine:
1. Quem participou? (só liste se nomes foram ditos)
2. Quais foram os tópicos discutidos? (agrupe assuntos relacionados)
3. Houve decisões formais? (palavras como "decidimos", "aprovamos", "vamos fazer")
4. Houve atribuição de tarefas? (alguém ficou responsável por algo?)
5. Sobrou algo em aberto? (questões não resolvidas)

# FORMATO DE SAÍDA

Responda APENAS com JSON válido seguindo este schema:

```json
{
  "title": "Título curto e descritivo da reunião",
  "date": "Data se mencionada na conversa, senão null",
  "participants": ["Lista de nomes EXPLICITAMENTE mencionados"],
  "executive_summary": "2-4 frases sintetizando o essencial da reunião",
  "topics": [
    {
      "title": "Título do tópico",
      "summary": "Resumo em até 3 frases. NUNCA invente, só descreva o que foi dito.",
      "evidence": {
        "quote": "Trecho exato da transcrição",
        "speaker": "Nome ou null",
        "timestamp_sec": null
      }
    }
  ],
  "decisions": [
    {
      "description": "O que foi decidido",
      "evidence": {
        "quote": "Trecho exato",
        "speaker": "Nome ou null",
        "timestamp_sec": null
      }
    }
  ],
  "action_items": [
    {
      "description": "O que precisa ser feito",
      "assigned_to": "Nome ou null se não atribuído",
      "deadline": "Data/prazo mencionado ou null",
      "evidence": {
        "quote": "Trecho exato que originou esta ação",
        "speaker": "Nome ou null",
        "timestamp_sec": null
      }
    }
  ],
  "open_questions": ["Pontos discutidos mas não resolvidos"]
}
```

# EXEMPLO DE RESPOSTA BOA

Transcrição (entrada):
"João: Pessoal, sobre o projeto Alpha, eu acho que a gente deveria adiar pra próxima sprint. Maria: Concordo, mas precisamos avisar o cliente. João: Beleza, eu falo com ele até sexta. Maria: E sobre o orçamento de design? João: A gente fechou em 15 mil mês passado, lembra? Maria: Ah verdade. Então só falta a aprovação do diretor. João: Eu mando email pra ele hoje."

Resposta (saída):
```json
{
  "title": "Alinhamento Projeto Alpha e Orçamento Design",
  "date": null,
  "participants": ["João", "Maria"],
  "executive_summary": "Decidido adiar o projeto Alpha para a próxima sprint. Ações definidas para comunicar cliente e obter aprovação final do diretor para o orçamento de design já fechado.",
  "topics": [
    {
      "title": "Adiamento do Projeto Alpha",
      "summary": "Discutida a necessidade de adiar a entrega do projeto Alpha para a próxima sprint, com necessidade de comunicar o cliente.",
      "evidence": {
        "quote": "sobre o projeto Alpha, eu acho que a gente deveria adiar pra próxima sprint",
        "speaker": "João",
        "timestamp_sec": null
      }
    },
    {
      "title": "Orçamento de Design",
      "summary": "Orçamento de R$ 15.000 fechado no mês anterior, pendente apenas aprovação do diretor.",
      "evidence": {
        "quote": "A gente fechou em 15 mil mês passado",
        "speaker": "João",
        "timestamp_sec": null
      }
    }
  ],
  "decisions": [
    {
      "description": "Adiar o projeto Alpha para a próxima sprint",
      "evidence": {
        "quote": "eu acho que a gente deveria adiar pra próxima sprint",
        "speaker": "João",
        "timestamp_sec": null
      }
    }
  ],
  "action_items": [
    {
      "description": "Falar com o cliente sobre o adiamento do projeto Alpha",
      "assigned_to": "João",
      "deadline": "sexta-feira",
      "evidence": {
        "quote": "eu falo com ele até sexta",
        "speaker": "João",
        "timestamp_sec": null
      }
    },
    {
      "description": "Enviar email ao diretor solicitando aprovação do orçamento de design",
      "assigned_to": "João",
      "deadline": "hoje",
      "evidence": {
        "quote": "Eu mando email pra ele hoje",
        "speaker": "João",
        "timestamp_sec": null
      }
    }
  ],
  "open_questions": []
}
```

# ANTI-EXEMPLO (NUNCA FAÇA ISSO)

NÃO produza output assim:
```json
{
  "action_items": [
    {
      "description": "Revisar todas as métricas do projeto",  // ❌ NÃO foi dito isso
      "assigned_to": "Equipe",  // ❌ inventou um "responsável genérico"
      "deadline": "próxima semana"  // ❌ não foi mencionado
    }
  ]
}
```

Lembre-se: PREFIRO UMA ATA COM POUCOS ITENS VERDADEIROS A UMA ATA INFLADA COM INVENÇÕES.
"""
```

**Critério de aceite:**
- [ ] Prompt está em arquivo separado, versionado
- [ ] Tem exemplos few-shot completos
- [ ] Tem anti-exemplos claros
- [ ] Tom é português brasileiro natural
- [ ] Schema JSON é explícito dentro do prompt

---

### Etapa 1.8.2 — Prompt para validação cruzada

```python
VALIDATION_PROMPT = """Você é um auditor crítico revisando uma ata gerada por IA.

# SUA TAREFA
Recebe duas coisas:
1. Transcrição original da reunião
2. Ata gerada (JSON)

Sua missão: encontrar INCONSISTÊNCIAS. Pra cada item da ata, verifique:

- O `description` corresponde ao que está em `evidence.quote`?
- A quote em `evidence` está REALMENTE na transcrição?
- Algum nome foi atribuído sem ter sido mencionado?
- Algum prazo foi inventado?
- Alguma decisão foi atribuída a quem não disse?

Retorne JSON com a lista de problemas. Se não houver problemas, retorne lista vazia.

```json
{
  "issues": [
    {
      "type": "fabricated_evidence" | "wrong_attribution" | "invented_deadline" | "other",
      "location": "action_items[2]",
      "description": "Descrição clara do problema"
    }
  ]
}
```

Seja CRÍTICO. Prefira reportar uma suspeita do que deixar passar uma invenção.
"""
```

**Critério de aceite:**
- [ ] LLM validador detecta inconsistências quando inseridas artificialmente
- [ ] Não inventa problemas em atas corretas (taxa de falso positivo baixa)

---

## 1.9 Pipeline de Geração da Ata

> **Objetivo:** Tudo encaixado: chunking → transcrição → diarização → geração → validação → ata final.

### Etapa 1.9.1 — Pipeline em estágios

**Passo a passo:**

1. Criar `app/services/minutes/pipeline.py`:

```python
from app.services.audio.converter import convert_async
from app.services.audio.vad import detect_speech_segments
from app.services.audio.chunker import chunk_audio_smart
from app.services.transcription.router import TranscriptionRouter
from app.services.transcription.parallel import transcribe_chunks_parallel, merge_chunk_transcriptions
from app.services.diarization.pyannote_service import diarize
from app.services.diarization.merger import merge_transcription_and_diarization
from app.services.llm.router import LLMRouter
from app.services.minutes.prompts import SYSTEM_PROMPT_MINUTES, VALIDATION_PROMPT
from app.services.minutes.schemas import MinutesOutput
from app.services.minutes.validator import validate_minutes

async def process_meeting(meeting_id: str, audio_path: Path):
    """
    Pipeline completo. Cada estágio atualiza o status no DB pra UI mostrar progresso.
    """
    db_update_status(meeting_id, "converting")

    # ESTÁGIO 1: Conversão e otimização
    optimized_path = settings.PROCESSED_DIR / f"{meeting_id}.mp3"
    await convert_async(audio_path, optimized_path)

    db_update_status(meeting_id, "detecting_speech")

    # ESTÁGIO 2: VAD
    speech_segments = detect_speech_segments(optimized_path)

    db_update_status(meeting_id, "chunking")

    # ESTÁGIO 3: Chunking
    chunks = chunk_audio_smart(optimized_path, speech_segments)

    db_update_status(meeting_id, "transcribing")

    # ESTÁGIO 4: Transcrição paralela
    router = TranscriptionRouter()
    chunk_results = await transcribe_chunks_parallel(chunks, router)
    transcription = merge_chunk_transcriptions(chunks, chunk_results)
    db_save_transcript(meeting_id, transcription)

    db_update_status(meeting_id, "diarizing")

    # ESTÁGIO 5: Diarização (opcional, mas faz no MVP)
    speaker_segments = diarize(optimized_path)
    transcription_with_speakers = merge_transcription_and_diarization(
        transcription.segments, speaker_segments
    )

    db_update_status(meeting_id, "generating_minutes")

    # ESTÁGIO 6: Geração da ata
    llm = LLMRouter().get_provider()
    minutes = await generate_minutes(llm, transcription_with_speakers)

    db_update_status(meeting_id, "validating")

    # ESTÁGIO 7: Validação anti-alucinação
    problems = validate_minutes(minutes, transcription.full_text)
    if problems:
        logger.warning(f"Problemas na ata: {problems}")
        # Regerar com prompt corretivo
        minutes = await regenerate_with_correction(llm, transcription_with_speakers, problems)

    # ESTÁGIO 8: Validação cruzada (LLM-as-judge)
    issues = await llm_validate_minutes(llm, minutes, transcription.full_text)
    if issues:
        minutes = await fix_issues(llm, minutes, transcription_with_speakers, issues)

    db_save_minutes(meeting_id, minutes)
    db_update_status(meeting_id, "completed")
```

**Critério de aceite:**
- [ ] Status no DB atualizado em cada estágio (UI pode mostrar progresso real)
- [ ] Erro em qualquer estágio é capturado e marcado como `failed` com mensagem clara
- [ ] Reunião de 2h é processada end-to-end em < 5 minutos (com Groq)
- [ ] Ata final passa em todas as validações

---

### Etapa 1.9.2 — Estratégia pra reuniões muito longas (>1h)

**Objetivo:** Quando a transcrição é muito grande (40k+ tokens), não dá pra mandar tudo de uma vez pro LLM.

**Estratégia em 3 passes:**

1. **Passe 1: Segmentação por tópicos**
   - Dividir a transcrição em "blocos de tópicos" (~10k tokens cada)
   - LLM segmenta: "aqui muda de assunto"

2. **Passe 2: Resumo por bloco**
   - Pra cada bloco, gerar mini-ata só dele
   - Salva como `partial_minutes`

3. **Passe 3: Consolidação final**
   - LLM recebe TODOS os `partial_minutes`
   - Sintetiza a ata final
   - Remove duplicatas, agrupa similares

**Critério de aceite:**
- [ ] Reunião de 3h gera ata coerente, sem perder informação
- [ ] Custo total de LLM é razoável (< $0.50 com Claude)
- [ ] Tempo total de geração de ata < 90s

---

## 1.10 Frontend React: telas e fluxos

### Etapa 1.10.1 — Roteamento e layout base

**Telas necessárias:**

1. **Home/Dashboard** — lista de reuniões processadas
2. **Upload** — drag & drop + opções de processamento
3. **Processamento** — tela com progresso em tempo real
4. **Detalhes da Reunião** — ata, transcrição, action items
5. **Configurações** — API keys, preferências, LLM padrão
6. **Onboarding** — primeira execução, configurar pelo menos 1 STT e 1 LLM

**Passo a passo:**

1. Instalar React Router: `npm install react-router-dom`
2. Estrutura em `src/pages/`:
   - `Home.tsx`
   - `Upload.tsx`
   - `Processing.tsx`
   - `MeetingDetail.tsx`
   - `Settings.tsx`
   - `Onboarding.tsx`

3. Layout base com sidebar:
   ```tsx
   <div className="flex h-screen">
     <Sidebar />
     <main className="flex-1 overflow-auto p-6">
       <Outlet />
     </main>
   </div>
   ```

**Critério de aceite:**
- [ ] Navegação entre telas funciona
- [ ] Layout responsivo (mínimo 800x600)
- [ ] Onboarding aparece SÓ na primeira execução

---

### Etapa 1.10.2 — Cliente HTTP pro sidecar

**Passo a passo:**

1. Criar `src/lib/api.ts`:
   ```typescript
   const BASE_URL = "http://localhost:8765";

   export async function api<T>(path: string, options?: RequestInit): Promise<T> {
     const res = await fetch(`${BASE_URL}${path}`, {
       ...options,
       headers: {
         "Content-Type": "application/json",
         ...options?.headers,
       },
     });
     if (!res.ok) throw new Error(`API error: ${res.status}`);
     return res.json();
   }

   export const meetings = {
     list: () => api<Meeting[]>("/meetings"),
     get: (id: string) => api<Meeting>(`/meetings/${id}`),
     upload: async (file: File) => {
       const formData = new FormData();
       formData.append("file", file);
       const res = await fetch(`${BASE_URL}/meetings/upload`, {
         method: "POST",
         body: formData,
       });
       return res.json();
     },
   };
   ```

2. Tipos TypeScript em `src/types/meeting.ts` espelhando Pydantic.

**Critério de aceite:**
- [ ] Todas as chamadas centralizadas em `api.ts`
- [ ] Tipos batem com schemas do backend
- [ ] Erros têm tratamento consistente

---

### Etapa 1.10.3 — Tela de Upload com progresso em tempo real

**Passo a passo:**

1. Implementar drag & drop com `react-dropzone`
2. Após upload, redirecionar pra `/processing/:id`
3. Na tela de processamento, polling no `/meetings/:id/status` a cada 2s
4. Mostrar estágio atual com ícone animado:
   - Convertendo áudio... ⏳
   - Detectando fala... ⏳
   - Transcrevendo... ⏳
   - Gerando ata... ⏳
   - Pronto! ✅

**Critério de aceite:**
- [ ] Drag & drop funciona pra MP3, MP4, M4A, WAV
- [ ] Validação de tamanho (max 500MB) e formato
- [ ] Progresso atualiza em tempo real (sem precisar refresh)
- [ ] Erros mostrados com mensagem clara

---

### Etapa 1.10.4 — Tela de detalhes da reunião

**Layout sugerido:**

```
┌────────────────────────────────────────┐
│ Título da Reunião                       │
│ Data | Duração | Provider usado          │
├────────────────────────────────────────┤
│ [Tabs: Ata | Transcrição | Ações]       │
├────────────────────────────────────────┤
│                                          │
│ # Sumário Executivo                      │
│ ...                                      │
│                                          │
│ # Decisões                               │
│ • Decisão X (origem: "trecho citado")    │
│                                          │
│ # Action Items                           │
│ • [Responsável] Ação (prazo)             │
│   📎 Trecho original                     │
│                                          │
└────────────────────────────────────────┘
```

**Crítico:** botão "ver trecho original" abre modal com a citação da transcrição. Usuário audita facilmente.

**Critério de aceite:**
- [ ] Ata renderiza bonita com tipografia clean
- [ ] Toggle pra ver evidências de cada item
- [ ] Botão de exportar (Markdown, PDF — PDF na V2)
- [ ] Botão de regenerar ata (chama LLM de novo)

---

## 1.11 Configuração de API Keys pelo usuário

> **Objetivo:** Usuário pluga as keys dele, app guarda criptografado, usa nas chamadas.

### Etapa 1.11.1 — Armazenamento criptografado

**Passo a passo:**

1. Usar `keyring` (Python lib) que delega pra OS:
   - Windows: Credential Manager
   - macOS: Keychain
   - Linux: Secret Service / KWallet

2. Instalar: `pip install keyring==25.4.1`

3. Criar `app/services/keys.py`:
   ```python
   import keyring
   from typing import Optional

   SERVICE_NAME = "eskuta-app"

   def save_api_key(provider: str, key: str):
       keyring.set_password(SERVICE_NAME, provider, key)

   def get_api_key(provider: str) -> Optional[str]:
       return keyring.get_password(SERVICE_NAME, provider)

   def delete_api_key(provider: str):
       try:
           keyring.delete_password(SERVICE_NAME, provider)
       except keyring.errors.PasswordDeleteError:
           pass

   def list_configured_providers() -> dict[str, bool]:
       return {
           "groq": bool(get_api_key("groq")),
           "assemblyai": bool(get_api_key("assemblyai")),
           "anthropic": bool(get_api_key("anthropic")),
           "openai": bool(get_api_key("openai")),
           "google": bool(get_api_key("google")),
       }
   ```

**Critério de aceite:**
- [ ] Keys salvas no keyring do OS (não em arquivo)
- [ ] Listar providers configurados não revela as keys
- [ ] Funciona em Windows e macOS

---

### Etapa 1.11.2 — UI de configuração com instruções passo a passo

**Objetivo:** Usuário não-técnico consegue plugar a key dele.

**Passo a passo:**

1. Tela `Settings.tsx` com seções:
   - "Transcrição (STT)" — Groq, AssemblyAI
   - "IA pra Ata (LLM)" — Claude, GPT, Gemini
   - "Preferências" — qual LLM usar por padrão, idioma da ata

2. Pra cada provider, mostrar:
   - Estado: configurado ✅ ou não 🟡
   - Botão "Como obter minha chave"
   - Input pra colar a chave
   - Botão "Salvar e testar" (faz uma chamada de teste)

3. Modal de instruções (1 modal por provider). Exemplo pra Groq:

   ```
   # Como conseguir sua chave do Groq

   1. Acesse console.groq.com e crie uma conta (não pede cartão de crédito)
   2. Vá em "API Keys" no menu lateral
   3. Clique em "Create API Key"
   4. Dê um nome (ex: "Eskuta App") e clique em criar
   5. COPIE a chave que aparece (ela só é mostrada UMA vez)
   6. Volte aqui e cole no campo abaixo

   ⚠️ Importante: sua chave é guardada criptografada no seu computador,
   só no seu computador. A gente nunca vê sua chave.

   💰 Custo: O free tier do Groq cobre uso pessoal de boa.
   Reunião de 3h custa ~R$ 0,60 só se você passar do free tier.

   [Abrir console.groq.com]  [Cancelar]
   ```

4. Repetir pros outros providers com links e instruções específicas.

**Critério de aceite:**
- [ ] Instruções claras pra cada provider
- [ ] Botão "abrir site" abre no browser do usuário (não webview do app)
- [ ] Teste de conectividade após salvar (verifica se key é válida)
- [ ] Mensagem de erro útil se key inválida

---

## 1.12 Empacotamento e Distribuição (1 instalador)

> **Objetivo:** Usuário baixa UM .exe (Windows) ou .dmg (macOS), instala como qualquer app, abre, funciona. Sem buildar frontend e backend separadamente.

### Etapa 1.12.1 — Pipeline de build unificado

**Passo a passo:**

1. Criar `scripts/build.sh` (Linux/macOS) e `scripts/build.bat` (Windows):

   ```bash
   #!/bin/bash
   set -e

   echo "🐍 1. Buildando sidecar Python..."
   cd src-python
   source venv/bin/activate
   python build_sidecar.py

   # Detectar target triple do Rust
   TARGET=$(rustc -vV | sed -n 's|host: ||p')
   echo "Target: $TARGET"

   # Copiar binário pro local que Tauri espera
   mkdir -p ../src-tauri/binaries
   cp dist/eskuta-sidecar ../src-tauri/binaries/eskuta-sidecar-$TARGET

   cd ..

   echo "⚛️ 2. Buildando frontend React..."
   npm run build

   echo "🦀 3. Buildando Tauri (que junta tudo)..."
   npm run tauri build

   echo "✅ Build completo!"
   echo "Instaladores em: src-tauri/target/release/bundle/"
   ```

2. Configurar `tauri.conf.json`:
   ```json
   {
     "productName": "Eskuta",
     "version": "0.1.0",
     "identifier": "com.eskuta.app",
     "build": {
       "beforeBuildCommand": "npm run build",
       "frontendDist": "../dist"
     },
     "bundle": {
       "active": true,
       "targets": ["msi", "nsis", "dmg", "app"],
       "icon": ["icons/icon.png", "icons/icon.ico", "icons/icon.icns"],
       "resources": [],
       "externalBin": ["binaries/eskuta-sidecar"],
       "windows": {
         "wix": {
           "language": "pt-BR"
         }
       },
       "macOS": {
         "minimumSystemVersion": "11.0"
       }
     }
   }
   ```

3. Validar o instalador final:
   - Tamanho esperado: ~80-150MB (Python contribui pra maior parte)
   - Tempo de build: 5-10 min na primeira vez

**Critério de aceite:**
- [ ] Comando único (`bash scripts/build.sh`) gera o instalador
- [ ] Instalador funciona em máquina limpa (sem Python instalado)
- [ ] Primeira execução cria diretórios corretos em `~/.eskuta/`
- [ ] App fecha graciosamente (mata sidecar Python)

---

### Etapa 1.12.2 — Auto-update

**Objetivo:** Quando você lança nova versão, usuários atualizam automaticamente.

**Passo a passo:**

1. Habilitar plugin oficial: `cargo add tauri-plugin-updater`

2. Configurar em `tauri.conf.json`:
   ```json
   "plugins": {
     "updater": {
       "endpoints": ["https://eskuta.app/updates/{{target}}/{{current_version}}"],
       "pubkey": "..."
     }
   }
   ```

3. Servidor de update (Cloudflare R2 + JSON manifest)
4. Implementar no frontend o check + prompt de instalação

**Critério de aceite:**
- [ ] App verifica update no startup
- [ ] Notifica usuário quando há nova versão
- [ ] Update aplicado com 1 clique
- [ ] Assinatura digital valida update (segurança)

---

### Etapa 1.12.3 — Logs e diagnóstico

**Objetivo:** Quando algo der errado na máquina do usuário, conseguir debugar.

**Passo a passo:**

1. Botão "Exportar logs" nas configurações
2. Coleta:
   - Logs do Python (`~/.eskuta/logs/`)
   - Logs do Tauri (stderr)
   - Versão do app, OS, configs (mascarando keys)
3. Empacota em ZIP pra usuário enviar

**Critério de aceite:**
- [ ] ZIP gerado contém todos os logs relevantes
- [ ] API keys NÃO aparecem nos logs (mascarar antes)
- [ ] Tamanho razoável (< 10MB normalmente)

---

# Fase 2 — Captura em Tempo Real

> **Objetivo da fase:** Usuário liga o app durante uma reunião (Meet, Zoom, Teams, qualquer um), o app captura áudio do sistema operacional sem entrar como bot, e ao final entrega a ata.
>
> **Pré-requisito:** Fase 1 completamente funcional e validada com pelo menos 10 reuniões reais.

## 2.1 Captura de áudio do sistema (Windows)

> **Por que começar pelo Windows?** APIs mais estáveis, mercado maior, menos complicações com permissões.

### Etapa 2.1.1 — Captura via WASAPI Loopback

**Objetivo:** Capturar tudo que sai pelos alto-falantes do Windows (vozes dos outros participantes da reunião).

**Passo a passo:**

1. Adicionar dependências Rust em `src-tauri/Cargo.toml`:
   ```toml
   [dependencies]
   cpal = "0.15"
   hound = "3.5"  # pra escrever WAV
   ringbuf = "0.4"
   ```

2. Criar `src-tauri/src/audio/system_capture_windows.rs`:
   ```rust
   use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
   use std::sync::mpsc;
   use std::sync::{Arc, Mutex};

   pub struct WindowsSystemCapture {
       stream: Option<cpal::Stream>,
       buffer: Arc<Mutex<Vec<f32>>>,
       sample_rate: u32,
   }

   impl WindowsSystemCapture {
       pub fn new() -> Result<Self, String> {
           let host = cpal::default_host();

           // No Windows, o device default OUTPUT pode ser usado como input em modo loopback
           let device = host
               .default_output_device()
               .ok_or("Nenhum dispositivo de saída encontrado")?;

           let config = device
               .default_output_config()
               .map_err(|e| e.to_string())?;

           let buffer = Arc::new(Mutex::new(Vec::new()));
           let buf_clone = buffer.clone();

           // WASAPI loopback usa device output mas modo input
           let stream = device
               .build_input_stream(
                   &config.into(),
                   move |data: &[f32], _| {
                       let mut buf = buf_clone.lock().unwrap();
                       buf.extend_from_slice(data);
                   },
                   |err| eprintln!("Erro stream: {}", err),
                   None,
               )
               .map_err(|e| e.to_string())?;

           stream.play().map_err(|e| e.to_string())?;

           Ok(Self {
               stream: Some(stream),
               buffer,
               sample_rate: 48000,  // ajustar conforme config
           })
       }

       pub fn drain(&self) -> Vec<f32> {
           let mut buf = self.buffer.lock().unwrap();
           let drained = buf.clone();
           buf.clear();
           drained
       }

       pub fn stop(&mut self) {
           self.stream = None;
       }
   }
   ```

3. **Atenção a issues conhecidos do cpal no Windows:** WASAPI exclusivo vs compartilhado. Use sempre compartilhado.

**Critério de aceite:**
- [ ] App captura áudio do sistema enquanto Spotify toca uma música (teste prático)
- [ ] Buffer cresce conforme áudio é capturado
- [ ] Stop encerra o stream limpo
- [ ] Sample rate documentado pra resampling posterior

---

### Etapa 2.1.2 — Captura do microfone

**Passo a passo:**

1. Criar `src-tauri/src/audio/microphone.rs`:
   ```rust
   pub struct MicrophoneCapture {
       stream: Option<cpal::Stream>,
       buffer: Arc<Mutex<Vec<f32>>>,
       sample_rate: u32,
   }

   impl MicrophoneCapture {
       pub fn new() -> Result<Self, String> {
           let host = cpal::default_host();
           let device = host.default_input_device()
               .ok_or("Nenhum microfone encontrado")?;
           let config = device.default_input_config()
               .map_err(|e| e.to_string())?;
           // ... resto similar à captura do sistema
       }
   }
   ```

2. UI: dropdown pra usuário escolher qual microfone (caso tenha vários).

**Critério de aceite:**
- [ ] Lista de microfones disponíveis aparece na UI
- [ ] Usuário pode trocar mic em tempo real (sem reiniciar app)
- [ ] Indicador visual de "volume" do mic (medidor de pico)

---

## 2.2 Captura de áudio do sistema (macOS)

> **Aqui mora a dor.** macOS não tem API direta como WASAPI. Tem 3 caminhos com trade-offs diferentes.

### Etapa 2.2.1 — Decisão: ScreenCaptureKit (macOS 13+)

**Por que esse caminho?**
- API oficial moderna, sem precisar de driver virtual
- Mas: precisa de permissão de gravação de tela (modal assustador na primeira vez)
- Funciona a partir de macOS 13 Ventura

**Trade-offs:**

| Abordagem | Prós | Contras |
|-----------|------|---------|
| ScreenCaptureKit | API oficial, sem driver | Permissão de tela, macOS 13+ |
| BlackHole (virtual audio driver) | Funciona em qualquer macOS | Usuário instala driver (UX ruim) |
| CoreAudio TAP (macOS 14.4+) | API moderna, sem permissão de tela | Só macOS 14.4+ |

**Decisão recomendada:** ScreenCaptureKit + fallback pra instruções de BlackHole se permissão negada.

### Etapa 2.2.2 — Bindings Rust pra ScreenCaptureKit

**Passo a passo:**

1. Usar crate: `screencapturekit = "0.3"`

2. Criar `src-tauri/src/audio/system_capture_macos.rs`:
   ```rust
   #[cfg(target_os = "macos")]
   use screencapturekit::{
       sc_content_filter::SCContentFilter,
       sc_stream_configuration::SCStreamConfiguration,
       sc_stream::SCStream,
       ...
   };

   pub struct MacOSSystemCapture {
       // ... implementação usando ScreenCaptureKit
   }
   ```

3. Pedir permissão de captura na primeira vez:
   - Detectar se permissão concedida com `CGRequestScreenCaptureAccess()`
   - Se não, mostrar modal explicando: "Pra capturar áudio das reuniões, precisamos da permissão de Gravação de Tela. Não vamos gravar sua tela, só capturar o áudio que sai pelos alto-falantes."

**Critério de aceite:**
- [ ] Funciona no macOS 13+
- [ ] Modal de permissão é amigável
- [ ] Fallback claro pra macOS < 13 (instruções pra BlackHole)
- [ ] Áudio capturado bate em qualidade com mac nativo

---

## 2.3 Mix de microfone + sistema

> **Objetivo:** Combinar duas fontes de áudio em um único stream que pode ser transcrito.

### Etapa 2.3.1 — Resampling pra taxa única

**Problema:** mic pode estar em 44.1kHz, sistema em 48kHz. Não dá pra somar diretamente.

**Passo a passo:**

1. Dep: `rubato = "0.15"` (resampling de alta qualidade em Rust)

2. Resampler que converte tudo pra 16kHz (mesma taxa do Whisper):
   ```rust
   use rubato::{FftFixedIn, Resampler};

   pub fn resample_to_16khz(input: &[f32], input_rate: u32) -> Vec<f32> {
       let mut resampler = FftFixedIn::<f32>::new(
           input_rate as usize,
           16000,
           input.len() / 10,  // chunk size
           2,                  // sub_chunks
           1,                  // channels
       ).unwrap();

       let waves_in = vec![input.to_vec()];
       let waves_out = resampler.process(&waves_in, None).unwrap();
       waves_out[0].clone()
   }
   ```

### Etapa 2.3.2 — Mixagem

**Passo a passo:**

1. Após resampling, ambos os streams estão em 16kHz mono.

2. Mix simples (média dos samples):
   ```rust
   pub fn mix_audio(a: &[f32], b: &[f32]) -> Vec<f32> {
       let len = a.len().min(b.len());
       (0..len).map(|i| (a[i] + b[i]) / 2.0).collect()
   }
   ```

3. **Atenção:** mixagem pode causar clipping se ambos os streams estão altos. Aplicar normalização:
   ```rust
   pub fn normalize(samples: &mut [f32]) {
       let max = samples.iter().map(|s| s.abs()).fold(0.0f32, f32::max);
       if max > 1.0 {
           let factor = 0.99 / max;
           for s in samples.iter_mut() {
               *s *= factor;
           }
       }
   }
   ```

**Critério de aceite:**
- [ ] Audio mixado sem clipping
- [ ] Voz do usuário + voz dos outros participantes ambas audíveis
- [ ] Latência adicionada pela mixagem < 50ms

---

## 2.4 Streaming "quase real-time" com chunks

> **Decisão arquitetural importante:** NÃO vamos fazer streaming verdadeiro (WebSocket persistente) no MVP de tempo real. Vamos fazer chunks de 30s mandados em batch pro Groq.
>
> **Por quê?** Streaming real exige Deepgram pago. Chunks de 30s no Groq batch são:
> - Gratuitos (free tier cobre)
> - Latência aceitável (~5s percebida)
> - Reaproveitam 100% da arquitetura do MVP

### Etapa 2.4.1 — Buffer circular e flush periódico

**Passo a passo:**

1. Buffer de 30s rotativo no Rust:
   ```rust
   pub struct AudioBuffer {
       samples: Vec<f32>,
       sample_rate: u32,
       chunk_duration_sec: f32,
   }

   impl AudioBuffer {
       pub fn push(&mut self, new_samples: &[f32]) {
           self.samples.extend_from_slice(new_samples);
       }

       pub fn try_flush(&mut self) -> Option<Vec<f32>> {
           let chunk_size = (self.sample_rate as f32 * self.chunk_duration_sec) as usize;
           if self.samples.len() >= chunk_size {
               let chunk: Vec<f32> = self.samples.drain(..chunk_size).collect();
               Some(chunk)
           } else {
               None
           }
       }
   }
   ```

2. A cada 30s, exporta o chunk como WAV temporário e manda pro sidecar Python via HTTP:
   ```rust
   #[tauri::command]
   async fn process_audio_chunk(samples: Vec<f32>) -> Result<String, String> {
       // Salvar como WAV temporário
       let wav_path = save_wav(&samples)?;

       // Enviar pro sidecar
       let client = reqwest::Client::new();
       let res = client.post("http://localhost:8765/realtime/chunk")
           .json(&serde_json::json!({"audio_path": wav_path}))
           .send()
           .await
           .map_err(|e| e.to_string())?;

       let result = res.json::<serde_json::Value>().await.map_err(|e| e.to_string())?;
       Ok(result["text"].as_str().unwrap_or("").to_string())
   }
   ```

3. Sidecar Python expõe endpoint `/realtime/chunk` que usa o router de transcrição (mesma camada do MVP).

**Critério de aceite:**
- [ ] Chunks de 30s gerados consistentemente
- [ ] Latência total (fala -> texto na UI) < 10s
- [ ] Sem perda de áudio nas fronteiras dos chunks (overlap de 2s recomendado)

---

### Etapa 2.4.2 — Tratamento de overlaps

**Problema:** se cortar em 30s exatos, palavra pode partir no meio.

**Solução:** chunks de 32s com 2s de overlap. Resultado:
- Chunk 1: [0s - 32s]
- Chunk 2: [30s - 62s]
- ... e assim por diante

Na hora de mesclar transcrições, deduplica o overlap usando algoritmo de alinhamento de strings.

**Critério de aceite:**
- [ ] Palavras nas fronteiras dos chunks aparecem na transcrição final
- [ ] Sem duplicação no merge
- [ ] Timestamps consistentes

---

## 2.5 UI durante reunião

### Etapa 2.5.1 — Janela compacta e discreta

**Layout:**

```
┌──────────────────────────────┐
│ 🔴 Eskuta gravando            │
│ 00:23:45                     │
│                              │
│ Transcrição ao vivo:         │
│ "...e então decidimos        │
│  postpone o lançamento..."   │
│                              │
│ [Pausar] [Encerrar]          │
└──────────────────────────────┘
```

**Características:**
- Janela pequena (~320x400)
- "Always on top" (configurável)
- Posicionável no canto
- Mostra últimas 3-4 frases transcritas
- Hotkey global pra mostrar/esconder

### Etapa 2.5.2 — Hotkeys globais

**Passo a passo:**

1. Plugin: `tauri-plugin-global-shortcut`

2. Registrar shortcuts:
   - `Ctrl+Shift+R` (Windows) / `Cmd+Shift+R` (Mac): iniciar/parar gravação
   - `Ctrl+Shift+H`: mostrar/esconder janela

3. Implementar handlers no Rust

**Critério de aceite:**
- [ ] Hotkeys funcionam mesmo com app minimizado
- [ ] Não conflitam com hotkeys de plataformas comuns (Zoom, Meet)

---

### Etapa 2.5.3 — Indicador na barra de tarefas / menu bar

**Objetivo:** Usuário sempre sabe que o app está rodando.

**Passo a passo:**

1. Plugin: `tauri-plugin-tray`

2. Ícone na tray:
   - Estado "idle": ícone normal
   - Estado "recording": ícone com bolinha vermelha pulsando
   - Click direito: menu rápido (iniciar, parar, abrir app)

**Critério de aceite:**
- [ ] Ícone visível na tray do Windows / menu bar do Mac
- [ ] Estado visual reflete situação real
- [ ] Click esquerdo abre janela principal

---

## 2.6 Reprocessamento pós-reunião

> **Insight chave:** a transcrição "ao vivo" tem qualidade menor (chunks isolados, sem contexto entre eles). Após encerrar a reunião, **reprocessamos o áudio completo** pra ata final de alta qualidade.

### Etapa 2.6.1 — Salvar áudio bruto durante a reunião

**Passo a passo:**

1. Em paralelo aos chunks de 30s sendo transcritos, salvar o áudio completo num arquivo:
   ```rust
   pub struct FullRecorder {
       file: hound::WavWriter<BufWriter<File>>,
   }
   ```

2. Arquivo crescendo em disco: `~/.eskuta/recordings/{meeting_id}.wav`

3. Ao encerrar reunião, esse arquivo é o input do pipeline da Fase 1.

### Etapa 2.6.2 — Pipeline pós-reunião

**Fluxo:**

```
Usuário clica "Encerrar Reunião"
       ↓
Para captura, fecha WAV
       ↓
Mostra "Processando ata final..."
       ↓
Roda pipeline COMPLETO da Fase 1 sobre o WAV
(VAD + chunking + transcrição com Groq + diarização + LLM)
       ↓
Ata final pronta, salva no banco
       ↓
Notifica usuário
```

**Critério de aceite:**
- [ ] Áudio completo é preservado mesmo se app crashar
- [ ] Reprocessamento usa exatamente o mesmo pipeline da Fase 1
- [ ] Ata final tem qualidade MUITO superior à transcrição "ao vivo"
- [ ] Usuário pode comparar versão ao vivo vs versão final

---

# Fase 3 — Produção (App Pago)

> **Quando entrar nessa fase:** depois que Fases 1 e 2 estão maduras, validadas com 20+ usuários reais, e você decidiu transformar em produto comercial.

## 3.1 Mudanças Arquiteturais Necessárias

### 3.1.1 — Migrar SQLite → Postgres

**Por que migrar:**
- Multi-usuário simultâneo
- Backup centralizado
- Sync entre dispositivos
- Analytics

**Como migrar:**

1. **Aplicar migrations Postgres:**
   - As migrations em `/migrations/*.sql` já foram escritas compatíveis com Postgres
   - Aplicar uma a uma na nova instância

2. **Trocar driver no SQLAlchemy:**
   ```python
   # De:
   engine = create_async_engine(f"sqlite+aiosqlite:///{settings.DB_PATH}")
   # Pra:
   engine = create_async_engine(settings.DATABASE_URL)  # postgres://...
   ```

3. **Ajustes de SQL específicos:**
   - `AUTOINCREMENT` (SQLite) → `SERIAL` ou `IDENTITY` (Postgres)
   - `DATETIME` → `TIMESTAMP WITH TIME ZONE`
   - Funções de data (já documentado no schema)

4. **Script de migração de dados** (se necessário levar dados locais pra cloud):
   - Export SQLite → JSON
   - Import JSON → Postgres
   - Validar contagens e checksums

**Critério de aceite:**
- [ ] Mesma aplicação roda em SQLite (dev/local) e Postgres (prod) sem alteração de código
- [ ] Migrations versionadas e idempotentes
- [ ] Tests passam contra ambos

---

### 3.1.2 — Backend hospedado (separar do desktop)

**Arquitetura nova:**

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│  App Tauri  │ ◄────────────► │  Backend Cloud   │
│  (desktop)  │                 │  (FastAPI prod)  │
└─────────────┘                 └──────────────────┘
                                          │
                                          ▼
                                ┌──────────────────┐
                                │  Postgres        │
                                │  Redis (cache)   │
                                │  S3 (áudios)     │
                                └──────────────────┘
```

**Decisões:**
- **Hospedagem:** Railway, Fly.io ou DigitalOcean App Platform (custo baixo pra começar)
- **Storage de áudio:** S3 compatible (R2 da Cloudflare é barato)
- **Auth:** Auth0 ou Clerk (não reinventar a roda)
- **Pagamentos:** Stripe (recurring)

### 3.1.3 — Contas de usuário e auth

**Mudanças:**

1. Adicionar tabelas:
   - `users` (id, email, name, hashed_password, created_at, ...)
   - `subscriptions` (user_id, plan, status, stripe_customer_id, ...)
   - `api_quotas` (user_id, monthly_minutes_used, monthly_minutes_limit, ...)

2. Cada tabela existente ganha `user_id` FK

3. Migrations versionadas pra alteração (`002_add_users.sql`)

4. JWT auth nos endpoints

5. UI de login/registro no app

### 3.1.4 — Modelo de cobrança

**Sugestão de planos:**

| Plano | Preço | Limite | Diferencial |
|-------|-------|--------|-------------|
| Free | R$ 0 | 5h/mês | Marca d'água na ata, fila secundária |
| Pessoal | R$ 29/mês | 30h/mês | Sem marca, prioridade normal |
| Pro | R$ 79/mês | 100h/mês | Diarização, exportação PDF, integrações |
| Empresarial | R$ 199/mês | 500h/mês | Multi-user, SSO, retenção customizada |

**Implementação:**
- Stripe Customer Portal pra gerenciar plano
- Webhooks pra sincronizar status
- Soft-limit (avisa) e hard-limit (bloqueia)

---

### 3.1.5 — Conformidade legal (LGPD/GDPR)

**Necessário:**

- [ ] Política de privacidade
- [ ] Termos de uso
- [ ] DPO (Data Protection Officer) — pode ser terceirizado
- [ ] Export de dados do usuário (LGPD direito de portabilidade)
- [ ] Delete account com purge completo
- [ ] Criptografia at-rest (Postgres TDE)
- [ ] Logs de auditoria de acesso a dados sensíveis
- [ ] Avisos de consentimento no app (gravação de reunião com terceiros)

### 3.1.6 — Suporte e telemetria

**Adicionar:**

1. **Sentry** pra tracking de erros em produção
2. **PostHog** ou **Mixpanel** pra analytics de uso
3. **Crisp** ou **Intercom** pra suporte
4. Sistema de feedback in-app (button "Dar feedback")

### 3.1.7 — CI/CD

**Setup:**

1. **GitHub Actions** com matrix build (Windows + macOS + Linux)
2. **Code signing** (Apple Developer Account + Windows EV cert) — custos: ~$500/ano combinados
3. **Notarização macOS** obrigatória
4. **Release automation:** tag git → build → assina → publica em CDN

---

## 3.2 Roadmap Pós-MVP/Real-time pra Produto Comercial

| Sprint | Foco | Entregável |
|--------|------|------------|
| S1 | Backend cloud + auth | Backend prod no ar, registro e login funcionando |
| S2 | Migração de dados | Tool de migrate SQLite local → cloud |
| S3 | Pagamentos | Stripe integrado, 3 planos funcionando |
| S4 | Quotas e billing | Limites mensais aplicados, downgrade gracioso |
| S5 | Marketing site | Landing page, blog, docs |
| S6 | Beta privado | 20 usuários pagos selecionados |
| S7-8 | Bugs e refinamento | Baseado em feedback do beta |
| S9 | Launch público | Product Hunt, Hacker News, etc |

---

# Apêndices

## Apêndice A — Estratégia de Performance

### Otimizações de alto impacto (fazer no MVP)

1. **Compressão local antes do upload** ✅
   - MP4 1.5GB → MP3 40MB local com ffmpeg
   - Reduz upload em 30-50x

2. **Paralelização de chunks** ✅
   - Asyncio.gather() com semáforo
   - 4 chunks simultâneos por padrão

3. **VAD antes de transcrever** ✅
   - Remove 20-25% do áudio (silêncios)
   - Bonus: reduz alucinação do Whisper

4. **Cache por hash de arquivo** ✅
   - SHA256 do áudio → resultado cacheado
   - Re-upload do mesmo arquivo = resposta instantânea

### Otimizações de impacto médio (V2)

5. **Streaming progressivo de ata**
   - Não esperar transcrição completa pra começar geração
   - Gera ata parcial enquanto resto transcreve

6. **Whisper local em GPU (opcional)**
   - Usuários com GPU NVIDIA podem desligar API
   - Custo zero, latência menor

### Otimizações desnecessárias (NÃO fazer)

- ❌ Otimização prematura do código React
- ❌ Cache distribuído (não tem multi-instance)
- ❌ Microserviços (overengineering pra app desktop)

---

## Apêndice B — Segurança

### Princípios

1. **Áudios e transcrições NUNCA saem da máquina** exceto pra APIs de STT
2. **API keys criptografadas via OS keyring** (não em arquivos)
3. **HTTPS obrigatório** em toda comunicação com APIs externas
4. **Validação de entrada rigorosa** em todos os endpoints
5. **Logs nunca contêm dados sensíveis** (API keys, conteúdo de áudio)

### Checklist de segurança pré-release

- [ ] Nenhuma API key hardcoded no código
- [ ] `.env` no `.gitignore`
- [ ] Dependências sem vulnerabilidades conhecidas (`pip-audit`, `npm audit`)
- [ ] Endpoints validam tipos com Pydantic
- [ ] Limite de tamanho em uploads (500MB)
- [ ] Sanitização de paths (evitar path traversal)
- [ ] Tauri allowlist configurada (não dar acesso total ao FS)
- [ ] Updates assinados digitalmente

---

## Apêndice C — Estratégia de Testes

### Testes unitários (Python — pytest)

**Cobertura mínima:** 70%

Onde focar:
- [ ] Conversão e compressão de áudio
- [ ] VAD e chunking (com fixtures de áudio real)
- [ ] Adapters de transcrição (com mocks de API)
- [ ] Validator de evidências
- [ ] Router de fallback (simulando falhas)

### Testes de integração

- [ ] Upload de arquivo real → status "completed"
- [ ] Falha do Groq → AssemblyAI assume → sucesso
- [ ] Reunião curta (~5 min) ponta a ponta

### Testes end-to-end (Playwright pro frontend)

- [ ] Onboarding completo (configurar 1 STT + 1 LLM)
- [ ] Upload → ver ata
- [ ] Editar/exportar ata

### Testes manuais críticos

Antes de cada release:

- [ ] Instalar do zero em Windows limpo
- [ ] Instalar do zero em macOS limpo
- [ ] Reunião real de 1h+ (uso próprio)
- [ ] Permissions flow no Mac (ScreenCaptureKit)

---

## Apêndice D — Métricas e Sucesso

### Métricas técnicas (sempre monitorar)

| Métrica | Target | Como medir |
|---------|--------|------------|
| Tempo médio de transcrição (1h áudio) | < 90s | Logs do pipeline |
| Taxa de fallback Groq → AssemblyAI | < 5% | Métricas no DB |
| Custo médio por reunião | < $0.10 | API responses |
| Quality score da ata (manual) | 8/10 | Survey após geração |
| % de evidências validadas com sucesso | > 90% | Validator output |
| Crashes / 100 reuniões | < 1 | Sentry |

### Métricas de produto (pós-MVP)

- DAU/MAU (uso ativo)
- Reuniões processadas / usuário / mês
- Net Promoter Score
- Churn (depois que tiver pagantes)

---

## Apêndice E — Decisões Arquiteturais (ADRs)

> Toda decisão importante tem aqui justificativa e contexto. Útil pra futuro "por que a gente fez assim?".

### ADR-001: Tauri ao invés de Electron

**Decisão:** Usar Tauri como wrapper desktop.

**Contexto:** App vai ficar aberto durante reuniões longas, captura de áudio nativa é crítica.

**Razões:**
- Instalador 10x menor (~15MB vs ~200MB)
- 3x menos consumo de RAM
- Acesso direto às APIs nativas via Rust
- Mais alinhado com filosofia "local-first"

**Trade-off aceito:** Comunidade menor que Electron, dev precisa aprender Rust básico.

---

### ADR-002: Groq primário ao invés de OpenAI Whisper

**Decisão:** Groq Whisper Large v3 Turbo como STT primário.

**Razões:**
- Free tier extremamente generoso (2h de áudio por hora)
- 228x velocidade real-time (60min → 16s)
- Mesmo modelo que OpenAI mas 89% mais barato
- Migrável pra OpenAI Whisper API ou self-hosted sem mudar pré/pós-processamento

---

### ADR-003: pyannote local ao invés de diarização via API

**Decisão:** Rodar pyannote.audio localmente.

**Razões:**
- Zero custo por uso
- Privacidade (áudio não sai da máquina)
- Qualidade SOTA

**Trade-off aceito:** 500MB de modelo pra baixar, processamento pesa na CPU.

**Mitigação:** Diarização é feature opcional (toggle), pode ser desativada.

---

### ADR-004: Não fazer streaming WebSocket no MVP de real-time

**Decisão:** Usar chunks batch de 30s ao invés de streaming verdadeiro.

**Razões:**
- Reusa 100% da infra do MVP de upload
- Free tier do Groq cobre
- Latência aceitável (~5s) pra uso do produto

**Quando reconsiderar:** Quando tiver casos de uso reais que pedem latência < 1s (call center, atendimento ao vivo).

---

### ADR-005: SQLite pra MVP, Postgres pra produção

**Decisão:** Começar com SQLite, migrar pra Postgres na Fase 3.

**Razões:**
- Zero config pra app desktop local
- Migrations escritas compatíveis com Postgres desde o dia 1
- Postgres só faz sentido quando tiver multi-user real

---

## Apêndice F — Como Resolver Problemas Comuns

### "Sidecar não inicia"

1. Verificar logs em `~/.eskuta/logs/`
2. Tentar rodar o binário manualmente
3. Checar antivírus (Windows às vezes bloqueia)
4. Reinstalar app

### "Transcrição muito lenta"

1. Verificar conexão de internet
2. Checar status da Groq (status.groq.com)
3. Forçar fallback pra AssemblyAI
4. Verificar tamanho do arquivo (>500MB pode demorar)

### "Ata genérica ou inventando coisas"

1. Verificar qualidade da transcrição (ver na aba Transcrição)
2. Ver se as evidências batem (botão "ver trecho original")
3. Trocar LLM (Claude tende a alucinar menos que GPT em PT-BR)
4. Regenerar a ata

### "Áudio não captura no Mac"

1. Verificar permissões em Sistema > Privacidade > Gravação de Tela
2. macOS 13 ou superior?
3. Tentar BlackHole como fallback

---

## Apêndice G — Links e Recursos

### Documentação oficial

- Tauri: https://tauri.app/start
- FastAPI: https://fastapi.tiangolo.com
- Groq Whisper: https://console.groq.com/docs/speech-text
- AssemblyAI: https://www.assemblyai.com/docs
- pyannote: https://github.com/pyannote/pyannote-audio
- Anthropic: https://docs.anthropic.com
- OpenAI: https://platform.openai.com/docs
- Google Gemini: https://ai.google.dev/docs

### Referências de inspiração

- Granola (UX de captura local): https://granola.ai
- Cluely (overlay invisível): https://cluely.com
- WhisperX (chunking + diarização): https://github.com/m-bain/whisperX

### Aprendizado

- Rust pra iniciantes: https://doc.rust-lang.org/book/
- Tauri + Python sidecar: https://github.com/dieharders/example-tauri-v2-python-server-sidecar
- Anti-hallucination em LLMs: https://arxiv.org/abs/2311.05232

---

## 🎯 Checklist Final do MVP (Fase 1)

Quando todas essas caixinhas estiverem marcadas, MVP tá pronto pra usuário real:

### Funcional
- [ ] Upload de MP3/MP4 até 500MB funciona
- [ ] Transcrição de 1h leva < 90s
- [ ] Ata gerada tem decisões e action items
- [ ] Evidências citadas batem com transcrição
- [ ] 3 LLMs configuráveis (Claude/GPT/Gemini)
- [ ] Fallback Groq → AssemblyAI funciona
- [ ] Onboarding guia usuário não-técnico
- [ ] Configurações salvas persistem

### Técnico
- [ ] Build gera 1 instalador único por SO
- [ ] Sidecar Python inicia e fecha graciosamente
- [ ] Logs em `~/.eskuta/logs/` rotacionam
- [ ] API keys no keyring do OS (criptografadas)
- [ ] Migrations versionadas SQLite + Postgres-compatíveis
- [ ] Testes unitários > 70% cobertura
- [ ] Zero vulnerabilidades em `npm audit` e `pip-audit`

### UX
- [ ] App abre em < 3 segundos
- [ ] Progresso visível em todo processamento longo
- [ ] Mensagens de erro em português claro
- [ ] Pelo menos 3 telas (Home, Upload, Detalhe) responsivas
- [ ] Onboarding leva < 2 min pra alguém destreinado

### Documentação
- [ ] Este relatório técnico atualizado
- [ ] README com instruções de dev
- [ ] CHANGELOG das versões
- [ ] LICENSE definida

---

## 🎯 Checklist Final do Real-time (Fase 2)

- [ ] Captura áudio sistema no Windows
- [ ] Captura áudio sistema no macOS (com fallback BlackHole)
- [ ] Mix mic + sistema funciona
- [ ] Janela compacta durante reunião
- [ ] Hotkeys globais funcionam
- [ ] Áudio bruto preservado (recovery em caso de crash)
- [ ] Reprocessamento pós-reunião gera ata final de qualidade
- [ ] Indicador na tray/menu bar

---

## 🎯 Checklist Final da Produção (Fase 3)

- [ ] Postgres em produção
- [ ] Auth (login, registro, recovery)
- [ ] 3 planos no Stripe
- [ ] Quotas mensais aplicadas
- [ ] LGPD/GDPR compliant
- [ ] Sentry + analytics configurados
- [ ] CI/CD com code signing
- [ ] Marketing site no ar
- [ ] Política de privacidade e termos
- [ ] Sistema de suporte (Crisp/Intercom)

---

## 📌 Notas Finais Pra Quem Vai Desenvolver

1. **Não pula etapas.** Cada uma constrói em cima da anterior. Se você "fizer rápido" a Fase 1, vai pagar caro na 2.

2. **Critérios de aceite são literais.** Se a etapa diz "transcrição de 1h em < 90s", testa antes de marcar como pronto.

3. **Documente decisões novas.** Se você precisou mudar algo, adiciona uma ADR no Apêndice E.

4. **Quando travar, leia de novo o relatório.** 70% dos problemas estão respondidos aqui.

5. **Quando achar algo que pode otimizar pra escala, MAS não é prioridade pro MVP — não faça.** Anota numa lista de "depois" e segue.

**Bora construir. 🚀**
