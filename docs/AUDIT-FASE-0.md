# Auditoria de integridade e segurança — Fase 0

> **Data:** 2026-05-21
> **Escopo:** scaffold da Fase 0 (Etapas 0.2 a 0.6 do `RELATORIO_TECNICO.md`)
> **Resultado final:** ✅ aprovado para commit

Este documento registra os achados da auditoria executada como parte do
fluxo "1 testes → auditoria → PR" da Fase 0. Pequenas remediações foram
aplicadas inline durante a auditoria (ver seção "Remediações") e estão
incluídas no mesmo commit.

---

## 1. Vulnerabilidades de dependências

| Ecossistema | Ferramenta | Resultado |
|-------------|------------|-----------|
| Node (`package.json`) | `npm audit --json` | **0 vulnerabilidades** (info/low/moderate/high/critical = 0) |
| Python (`src-python/requirements.txt`) | `pip-audit -r requirements.txt` | **No known vulnerabilities found** após remediação |

### Achados iniciais — Python (antes da remediação)

`pip-audit` reportou 6 CVEs em 2 pacotes nas versões pinadas pelo
`RELATORIO_TECNICO.md`:

| Pacote | Versão original | CVE / Advisory | Fix |
|--------|------------------|----------------|-----|
| `python-multipart` | 0.0.12 | GHSA-59g5-xgcq-4qw3 | 0.0.18 |
| `python-multipart` | 0.0.12 | GHSA-wp53-j4wj-2cfg | 0.0.22 |
| `python-multipart` | 0.0.12 | GHSA-mj87-hwqh-73pj | 0.0.26 |
| `python-multipart` | 0.0.12 | GHSA-pp6c-gr5w-3c5g | 0.0.27 |
| `starlette` (via FastAPI) | 0.38.6 | GHSA-f96h-pmfr-66vw | 0.40.0 |
| `starlette` | 0.38.6 | GHSA-2c2j-9gv5-cj73 | 0.47.2 |

### Remediação

`src-python/requirements.txt` atualizado para:
- `fastapi` 0.115.0 → **0.136.1**
- `starlette` 0.38.6 (transitiva) → **1.0.0** (fixada explicitamente)
- `python-multipart` 0.0.12 → **0.0.29**

Os 18 testes pytest continuam passando após o upgrade (cobertura 90%).

O `RELATORIO_TECNICO.md` foi escrito assumindo as versões antigas — esta
é a primeira ADR informal de "evoluímos a ideia": versões pinned devem
ser revisitadas a cada nova fase via `pip-audit` no CI.

---

## 2. Secrets hardcoded

Grep cego de prefixos comuns (`sk-…`, `gsk_…`, `AIza…`, `ghp_…`, `xoxb-…`)
e de padrões `KEY|SECRET|PASSWORD|TOKEN = "<16+ chars>"` em todo o repo
(excluindo `node_modules`, `target`, `venv`, `dist`, `build`, `.git`):

**Nenhum match.** Repositório limpo.

O design já prevê:
- Chaves de API nunca em `.env` em produção — só em `OS keyring` via lib `keyring` (Etapa 1.11)
- Tabela `api_keys` no SQLite armazena só `is_configured`/timestamps, nunca a chave em si

---

## 3. Superfície de ataque do sidecar (FastAPI)

| Verificação | Configuração atual | Status |
|-------------|--------------------|--------|
| Bind do socket | `127.0.0.1` (default) — só localhost | ✅ |
| Bind em `0.0.0.0` | Sem ocorrências reais (única referência é o help text "nunca expor em 0.0.0.0") | ✅ |
| CORS `allow_origins` | Lista explícita: `localhost:1420`, `tauri.localhost`, `tauri://localhost`, `https://tauri.localhost` — **sem wildcard `*`** | ✅ |
| CORS testes | 9 cases parametrizados em `tests/test_cors.py` cobrem origens permitidas e rejeitadas | ✅ |
| Validação de inputs | Pydantic models obrigatórios em todos os endpoints (será garantido por convenção em Fase 1+) | ⚠️ avaliar a cada novo endpoint |
| Logging de payloads | Loguru previsto pra Fase 1.1.1 (ainda não em uso) — política: nunca logar conteúdo de áudio nem API keys | ⏳ pendente Fase 1 |

---

## 4. Permissões do Tauri (`capabilities/default.json`)

Permissões habilitadas explicitamente:

- `core:default` — APIs mínimas do Tauri
- `opener:default` — abrir URLs no browser do sistema (modais de instruções
  de API keys na Etapa 1.11.2)
- `shell:allow-execute` **com scope restrito**: só permite executar o
  sidecar `binaries/eskuta-sidecar` (sidecar verdadeiro, não shell arbitrário)

Sem `fs:default`, sem `dialog:default` global, sem `http:default`. O
princípio é: cada plugin que adicionarmos numa fase futura entra com
scope explícito, nunca com defaults amplos.

---

## 5. Lock files e reprodutibilidade

| Arquivo | Comitado? | Motivo |
|---------|-----------|--------|
| `package-lock.json` | ✅ | Reprodutibilidade exata do frontend |
| `src-tauri/Cargo.lock` | ✅ | Recomendação oficial Rust pra binários (não libs) |
| `src-python/requirements.txt` | ✅ | Versões pinned por linha |
| `src-python/requirements-dev.txt` | ✅ | Idem |
| `src-python/requirements-build.txt` | ✅ | Idem (PyInstaller) |

Sem `Pipfile`, `poetry.lock` ou outros lockers — a Fase 0 ficou com
`pip install -r` puro, decisão deliberada pra evitar mais uma camada
no setup do sidecar.

---

## 6. `.gitignore`

Cobre:
- Node: `node_modules/`, `dist/`, `.vite/`, `.cache/`
- Rust: `src-tauri/target/`, `src-tauri/gen/schemas/`, `src-tauri/binaries/`
  (binários do PyInstaller são build artifacts, não fonte)
- Python: `venv/`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `dist/`,
  `build/`, `*.spec`
- Secrets: `.env`, `.env.*` (exceto `.env.example`), `*.pem`, `*.key`,
  `credentials.json`, `secrets.json`
- Dados de dev em paths que o app cria (`~/.eskuta/`, `~/.atena/`)
- OS files: `.DS_Store`, `Thumbs.db`, `desktop.ini`

---

## 7. Critérios de aceite da Fase 0 (segurança)

Checklist do `RELATORIO_TECNICO.md` §"Apêndice B — Segurança", aplicáveis
nesta fase:

- [x] Nenhuma API key hardcoded no código
- [x] `.env` no `.gitignore`
- [x] Dependências sem vulnerabilidades conhecidas (`pip-audit`, `npm audit`)
- [x] Tauri allowlist configurada (não dar acesso total ao FS)
- [ ] Endpoints validam tipos com Pydantic — **N/A na Fase 0** (só temos
      `/health` sem inputs). Garantir nas próximas fases.
- [ ] Limite de tamanho em uploads (500MB) — **N/A na Fase 0** (sem
      endpoint de upload ainda). Etapa 1.10.3.
- [ ] Sanitização de paths — **N/A na Fase 0**. Garantir em Etapa 1.3+.
- [ ] Updates assinados digitalmente — Etapa 1.12.2 (Fase 1).

---

## 8. Aprovação

✅ **Auditoria aprovada para commit + PR.**

Re-rodar antes de cada PR de fase futura:
```powershell
npm audit
& src-python/venv/Scripts/python.exe -m pip_audit -r src-python/requirements.txt
& src-python/venv/Scripts/python.exe -m pytest
npm test
pwsh scripts/preflight.ps1
```

Esses 5 comandos formam a "régua de pré-PR" do projeto. CI rodará os
mesmos no GitHub Actions (`.github/workflows/ci.yml`).
