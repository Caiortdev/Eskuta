# Como contribuir com o Eskuta

> Pra dev humano ou IA. Este doc ensina como abrir um PR que passa nos
> gates do projeto _antes_ de gastar tempo no CI.

---

## Setup inicial (uma vez por máquina)

```powershell
# 1. Validar ferramentas
pwsh scripts/preflight.ps1

# 2. Frontend
npm install

# 3. Sidecar Python
py -3.11 -m venv src-python/venv
src-python/venv/Scripts/python -m pip install -r src-python/requirements.txt
src-python/venv/Scripts/python -m pip install -r src-python/requirements-dev.txt

# 4. Ativar pre-commit (instala git hooks locais)
src-python/venv/Scripts/python -m pre_commit install
```

---

## Fluxo padrão de uma fase do RELATORIO_TECNICO

1. **Branch a partir de `main` atualizado**

   ```
   git checkout main && git pull
   git checkout -b phase-1.2-database   # ou feat/, fix/, chore/
   ```

2. **Trabalhar nas etapas** seguindo o `docs/RELATORIO_TECNICO.md`.

3. **Antes de cada commit** os hooks rodam automaticamente. Pra rodar
   manualmente em todo o repo:

   ```
   pre-commit run --all-files
   ```

4. **Antes do push**, valide a "régua de pré-PR":

   ```powershell
   pwsh scripts/preflight.ps1                                 # 9/9 OK
   npm run lint                                                # 0 warnings
   npm run format:check
   npm run lint:rust                                           # cargo fmt + clippy
   npm run test:coverage                                       # cov ≥ 70%
   cd src-python; venv/Scripts/python -m pytest; cd ..         # cov ≥ 70%
   npm audit
   src-python/venv/Scripts/python -m pip_audit -r src-python/requirements.txt
   ```

5. **Push** e abra o PR. O template em `.github/pull_request_template.md`
   guia o checklist.

6. **CI roda automaticamente.** São 7 jobs:
   - `python-sidecar` — lint Python + pytest com gate de coverage 70%
   - `frontend` — TypeScript + Vitest com gate 70% branches
   - `lint-frontend` — ESLint + Prettier check
   - `rust` — cargo fmt + clippy (deny warnings)
   - `security` — npm audit + pip-audit
   - `pre-commit` — sanity (mesmo que rodou local)
   - `tauri-build` — só em PR pra `main`: build do Tauri em Windows
     com sidecar empacotado pelo PyInstaller

7. **Merge é bloqueado** pelas branch protection rules em `main` até
   que **todos os checks acima estejam verde**. Não tente bypassar.

---

## Branch protection rules

Aplicadas via `scripts/setup-branch-protection.ps1`. Idempotente, pode
rodar de novo.

**Configuração atual (solo-friendly):**

- ✅ Status checks obrigatórios: todos os 7 jobs do CI
- ✅ `strict` mode: branch tem que estar atualizada com `main` antes do merge
- ✅ Bloqueia force-push em `main`
- ✅ Bloqueia deletion de `main`
- ✅ Exige conversations resolvidas no PR
- ✅ Owner (admin) pode bypassar em emergência (`enforce_admins=false`)
- ⏳ 0 reviews humanas obrigatórias (porque é solo no momento)

**Quando ficar com time, apertar:**

```powershell
pwsh scripts/setup-branch-protection.ps1 -RequireReviews 1
```

Aí passa a exigir 1 aprovação por PR + dismiss stale reviews on push.

---

## Convenção de mensagens de commit

Conventional Commits (não validado por CI, é só padrão de equipe):

- `feat(escopo): ...` — nova feature
- `fix(escopo): ...` — bug fix
- `chore(escopo): ...` — tooling, deps, CI
- `docs: ...` — apenas docs
- `refactor(escopo): ...` — refactor sem mudar comportamento
- `test(escopo): ...` — só testes

Escopos comuns: `phase-N.M`, `sidecar`, `frontend`, `tauri`, `ci`,
`docs`.

---

## Quando algo dá errado

- **Pre-commit bloqueia commit?** Os hooks tentam autocorrigir. Olhe o
  diff, dê `git add` nos arquivos que foram modificados, e commite de
  novo.
- **CI vermelho em algo que passa local?** Provavelmente diferença de
  line endings (CRLF vs LF), versão de tool, ou cache stale. Rode
  `pre-commit run --all-files` localmente — geralmente reproduz.
- **PR diz "behind main"?** Faça `git pull --rebase origin main` e push.
- **Branch protection bloqueia merge?** Olhe quais checks estão
  vermelhos no PR. O usuário humano não consegue (e não deve) bypassar.

---

## Decisões arquiteturais (ADRs)

Estão no `RELATORIO_TECNICO.md` §"Apêndice E — Decisões Arquiteturais".
Quando você desviar do mapa do projeto, adicione uma ADR nova
explicando _por quê_.

Exemplo recente: ADR informal de 2026-05-21 — versões de `fastapi`/
`starlette`/`python-multipart` foram bumpadas das versões pinadas no
relatório (tinham CVEs). Detalhes em `docs/AUDIT-FASE-0.md`.
