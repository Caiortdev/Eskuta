# Eskuta

> App desktop que vira áudio de reunião em **ata estruturada profissional** —
> upload de MP3/MP4 (Fase 1) e captura em tempo real durante Meet/Zoom/Teams
> (Fase 2). Local-first, em português brasileiro, com LLM configurável
> (Claude/GPT/Gemini).

## Stack

- **Frontend:** React 19 + TypeScript + Vite 7 + TailwindCSS v4 + Shadcn/UI
- **Wrapper desktop:** Tauri 2 (Rust)
- **Backend local (sidecar):** Python 3.11 + FastAPI, empacotado com PyInstaller
- **Banco:** SQLite (MVP) → Postgres (produção). Migrations bilíngues.

## Quick start

Pré-requisitos: Node ≥ 20, Rust stable, Python **3.11.x** (não 3.12+),
FFmpeg, Git, VS C++ Build Tools (Windows). Rode o preflight para validar:

```powershell
pwsh scripts/preflight.ps1
```

Depois:

```bash
# 1. Frontend + Tauri
npm install

# 2. Sidecar Python (uma vez)
py -3.11 -m venv src-python/venv
src-python/venv/Scripts/python -m pip install -r src-python/requirements.txt
src-python/venv/Scripts/python -m pip install -r src-python/requirements-dev.txt

# 3. Empacotar o sidecar (gera src-python/dist/eskuta-sidecar.exe)
src-python/venv/Scripts/python src-python/build_sidecar.py

# 4. Copiar pro local que o Tauri espera (Windows x64)
cp src-python/dist/eskuta-sidecar.exe \
   src-tauri/binaries/eskuta-sidecar-x86_64-pc-windows-msvc.exe

# 5. Rodar em dev
npm run tauri dev

# 6. Build de instalador
npm run tauri build
# saída: src-tauri/target/release/bundle/{msi,nsis}/
```

## Testes

```bash
npm test                                      # frontend (Vitest)
src-python/venv/Scripts/python -m pytest      # sidecar (pytest, cov 90%)
```

CI roda os mesmos testes em GitHub Actions
(`.github/workflows/ci.yml`).

## Estrutura

```
src/                React + TS (frontend)
src-tauri/          Rust core (Tauri)
src-python/         FastAPI sidecar (Python 3.11)
migrations/         SQL versionado (compat SQLite + Postgres)
scripts/            Build helpers (preflight, etc)
docs/               Mapa do projeto, relatório técnico, schema, auditoria
.github/workflows/  CI
```

## Roadmap

Fase 0 (Setup) ✅ • Fase 1 (MVP Upload) 🚧 • Fase 2 (Tempo real) • Fase 3 (Arquitetura de Servidor)
