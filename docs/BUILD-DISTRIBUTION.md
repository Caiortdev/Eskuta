# Build & Distribuição — Eskuta (Windows)

Este documento explica como compilar o Eskuta para um instalador único
(MSI + NSIS) que outros usuários conseguem baixar e rodar como qualquer
app Windows, sem precisar de Python ou Node instalados na máquina deles.

> **Plataforma alvo do MVP:** Windows 10/11 x86_64. macOS/Linux são
> tecnicamente suportados pelo Tauri mas não automatizados ainda no CI.

---

## Pré-requisitos (uma vez)

Em uma máquina Windows limpa:

1. **Python 3.11** — https://www.python.org/downloads/release/python-3119/
2. **Node 20+** — https://nodejs.org/
3. **Rust** — https://rustup.rs/ (instalar com toolchain `stable-x86_64-pc-windows-msvc`)
4. **Visual Studio Build Tools 2022** — para o linker MSVC ([download](https://visualstudio.microsoft.com/downloads/?q=build+tools))
   - Selecione "Desktop development with C++"
5. **WebView2 Runtime** — geralmente já vem no Windows 11; pra Win 10, instalar do site da Microsoft

### Setup do venv Python

```powershell
cd src-python
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt -r requirements-build.txt
```

---

## Build local

Um comando único:

```powershell
pwsh scripts/build.ps1
```

O que ele faz (4 etapas):

| Etapa | Tempo aprox. | O que acontece |
|-------|--------------|----------------|
| 1. Sidecar Python | 2-4 min | PyInstaller empacota `app/` + deps em `src-python/dist/eskuta-sidecar.exe` |
| 2. Copy + rename | <1s | Renomeia pra `src-tauri/binaries/eskuta-sidecar-<target>.exe` |
| 3. Frontend React | 10-30s | `npm run build` gera `dist/` com bundle minificado |
| 4. Tauri | 3-8 min | Compila Rust, junta tudo, gera MSI + NSIS |

**Total:** ~6-12 minutos na primeira vez. Builds incrementais (sem
`-CleanFirst`) costumam ficar em ~3-5 min.

### Flags úteis

```powershell
pwsh scripts/build.ps1 -SkipSidecar   # se nada mudou no Python
pwsh scripts/build.ps1 -CleanFirst    # rm -rf build/ + dist/ antes
```

### Saída

Após sucesso, os instaladores ficam em:

```
src-tauri/target/release/bundle/
├── msi/
│   └── Eskuta_0.1.0_x64_pt-BR.msi          # 80-120 MB
└── nsis/
    └── Eskuta_0.1.0_x64-setup.exe          # 70-110 MB
```

- **MSI** — instalador "corporativo" do Windows. Suporta GPO, instalação silenciosa (`msiexec /i ... /quiet`), e desinstalação via Painel de Controle.
- **NSIS** — instalador "tradicional" estilo Windows, menor, melhor para usuários finais.

---

## Verificação pós-build

Em uma máquina limpa (sem Python/Node/Rust):

1. Copie o `.msi` (ou `.exe`) pra essa máquina.
2. Instale.
3. Abra o app pelo menu Iniciar.
4. Verifique:
   - [ ] App abre sem erros
   - [ ] Splash "Aguardando sidecar..." some em <10s
   - [ ] Sidebar com 3 itens aparece
   - [ ] `~/.eskuta/` foi criado (com `db/`, `logs/`, `audio/`)
   - [ ] Upload de áudio funciona
   - [ ] Fechar o app encerra o sidecar (verifique no Task Manager — não pode ficar `eskuta-sidecar.exe` rodando órfão)

---

## Troubleshooting

### "ImportError: DLL load failed" ao rodar sidecar empacotado

Algum módulo Python não foi detectado por PyInstaller. Adicione em
`HIDDEN_IMPORTS` (`src-python/build_sidecar.py`) e rebuilde.

### "MSVCR140.dll missing" no MSI

Falta o **Visual C++ Redistributable 2015-2022** na máquina alvo. O MSI
do Tauri NÃO inclui o VCRedist — usuários precisam instalar separado
(geralmente já vem no Win 10/11 atualizado).

> Pra automatizar isso, adicionar `installer_args` no bloco `wix` do
> tauri.conf.json puxando o VCRedist como dependency. Fora do escopo do
> MVP por simplicidade.

### Sidecar fica órfão depois de fechar o app

O Tauri 2 + plugin shell já mata processos filhos no shutdown via
`shutdown_handler`. Se ficar órfão, é provavelmente porque o
`AppHandle::cleanup` não foi chamado — verifique `src-tauri/src/main.rs`.

### "Code signing" warning ao rodar o instalador

O instalador **não é assinado digitalmente** (precisa de um certificado
de Code Signing pago, ~US$ 200/ano). Windows mostra o SmartScreen
warning "Windows protected your PC" — usuário precisa clicar em "Mais
informações" → "Executar mesmo assim".

Pra produção (público amplo), comprar um certificado EV ou OV e
configurar `tauri.conf.json`:

```json
"bundle": {
  "windows": {
    "signCommand": "signtool sign /f cert.pfx /p $env:PFX_PASSWORD /tr http://timestamp.digicert.com /td sha256 /fd sha256 %1"
  }
}
```

---

## Roadmap pós-MVP

- [ ] Cross-platform (macOS + Linux) — precisa de CI matrix multi-OS
- [ ] Code signing (Windows EV cert + macOS Apple Developer ID)
- [ ] Notarization no macOS
- [ ] Auto-update via tauri-plugin-updater (planejado em fase 1.12.2)
- [ ] CI release workflow — tag `v*` dispara build + upload pra GitHub Releases
