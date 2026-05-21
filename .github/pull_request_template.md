<!--
Obrigado por contribuir com o Eskuta! 🎯
Preencha as seções abaixo. PRs que não passam no checklist são bloqueados
pelas branch protection rules do GitHub.
-->

## Resumo

<!-- 1-3 frases descrevendo o que muda e por quê. -->

## Tipo de mudança

- [ ] 🚀 Nova fase do RELATORIO_TECNICO.md (qual?)
- [ ] ✨ Feature dentro de uma fase em andamento
- [ ] 🐛 Bug fix
- [ ] 🔒 Correção de segurança
- [ ] 🧹 Refactor / cleanup (sem mudar comportamento)
- [ ] 📝 Documentação
- [ ] 🤖 CI/CD ou tooling
- [ ] ⬆️ Upgrade de dependência

## Como testei

<!-- Quais comandos rodou. Sempre inclua o equivalente local dos checks de CI. -->

- [ ] `pwsh scripts/preflight.ps1` (9/9 OK)
- [ ] `npm run lint` (sem warnings)
- [ ] `npm run format:check`
- [ ] `npm run test:coverage` (cov ≥ 70%)
- [ ] `npm run lint:rust`
- [ ] `cd src-python && venv/Scripts/python -m pytest` (cov ≥ 70%)
- [ ] `pre-commit run --all-files` (todos hooks verde)
- [ ] Smoke manual do app (se a mudança afeta UI ou bootstrap):
      `npm run tauri dev`, fechar a janela, conferir que o sidecar morre

## Checklist de qualidade

<!-- Deixe marcado o que se aplica. PR não merge enquanto algo crítico estiver desmarcado. -->

- [ ] Os critérios de aceite da fase / etapa do `RELATORIO_TECNICO.md` estão cobertos por testes
- [ ] Coverage não regrediu (Python ≥ 70% / Frontend ≥ 70% branches)
- [ ] Sem secrets / API keys hardcoded
- [ ] Mudanças de schema têm migration SQL versionada (compat SQLite + Postgres)
- [ ] Decisões arquiteturais novas têm ADR no Apêndice E do `RELATORIO_TECNICO.md` se desviam do mapa
- [ ] `docs/` atualizado se a mudança afeta comportamento documentado
- [ ] Sem `// TODO` ou `// FIXME` sem issue vinculada
- [ ] Sem dependências novas com vulnerabilidades (`npm audit` / `pip-audit` verde)

## Issues relacionadas

<!-- Closes #123, Refs #456, etc -->

## Screenshots / Vídeos

<!-- Se mudou UI, anexe antes/depois. Senão remova esta seção. -->

---

🤖 _Gerado a partir do template em `.github/pull_request_template.md`. Atualize aqui se o fluxo do projeto evoluir._
