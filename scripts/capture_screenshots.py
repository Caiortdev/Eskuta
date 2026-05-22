"""
Captura screenshots dos consoles de 5 providers (Groq, AssemblyAI,
Anthropic, OpenAI, Google) para popular o ApiKeyGuideModal do Eskuta.

Usa Playwright com perfil persistente isolado em ./tmp/pw-profile/.
Esse perfil é separado do seu Chrome normal — você precisa logar UMA
vez em cada provider via o setup mode, e os cookies ficam salvos.

Uso:
    python scripts/capture_screenshots.py setup
        # Abre janela do Chromium. Loga manualmente nos 5 providers.
        # Quando terminar TODOS, FECHA a janela do browser.
        # Cookies persistem em ./tmp/pw-profile/.

    python scripts/capture_screenshots.py capture
        # Modo automated. Reusa o profile da fase setup.
        # Navega nas URLs específicas e tira os 19 screenshots.

Notas de privacidade:
- O perfil em ./tmp/pw-profile/ contém suas sessões logadas. Está no
  .gitignore (tmp/). Não comite.
- Pra screenshots que mostram o valor REAL da key (04-copy.png), o
  script NÃO tenta criar uma key nova — apenas navega na tela. Se
  você quiser anotar com uma key real visível, capture manual + borre.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Força UTF-8 no stdout/stderr (Windows default é cp1252)
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from playwright.async_api import Page, async_playwright  # noqa: E402

PROJECT_ROOT = Path(__file__).parent.parent
PROFILE_DIR = PROJECT_ROOT / "tmp" / "pw-profile"
OUTPUT_DIR = PROJECT_ROOT / "public" / "api-key-guides"

# Configuração de cada provider:
# - "id": pasta em public/api-key-guides/
# - "name": label pra logs
# - "login_url": URL pra abrir no setup mode (o user loga aqui)
# - "captures": lista de screenshots a tirar no capture mode
#   - "file": nome do arquivo (sem extensão é .png)
#   - "url": URL pra navegar
#   - "wait_ms": ms a esperar após networkidle (default 1000)
#   - "click": seletor opcional pra clicar antes da screenshot (ex: revelar dialog)
PROVIDERS = [
    {
        "id": "groq",
        "name": "Groq",
        "login_url": "https://console.groq.com/keys",
        "captures": [
            {"file": "01-signup.png", "url": "https://console.groq.com/login"},
            {"file": "02-menu.png", "url": "https://console.groq.com/keys"},
            {
                "file": "03-create.png",
                "url": "https://console.groq.com/keys",
                "click": "text=/Create.*API Key/i",
                "wait_ms": 1500,
            },
            # 04-copy não é capturado automaticamente — exige criar key real
        ],
    },
    {
        "id": "assemblyai",
        "name": "AssemblyAI",
        "login_url": "https://www.assemblyai.com/app",
        "captures": [
            {"file": "01-signup.png", "url": "https://www.assemblyai.com/app/login"},
            {"file": "02-menu.png", "url": "https://www.assemblyai.com/app/api-keys"},
            {"file": "03-copy.png", "url": "https://www.assemblyai.com/app/api-keys"},
        ],
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "login_url": "https://console.anthropic.com/",
        "captures": [
            {"file": "01-signup.png", "url": "https://console.anthropic.com/login"},
            {"file": "02-credits.png", "url": "https://console.anthropic.com/settings/billing"},
            {
                "file": "03-create.png",
                "url": "https://console.anthropic.com/settings/keys",
                "click": "text=/Create Key/i",
                "wait_ms": 1500,
            },
        ],
    },
    {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "login_url": "https://platform.openai.com/",
        "captures": [
            {"file": "01-signup.png", "url": "https://platform.openai.com/login"},
            {"file": "02-billing.png", "url": "https://platform.openai.com/settings/organization/billing/overview"},
            {
                "file": "03-create.png",
                "url": "https://platform.openai.com/api-keys",
                "click": "text=/Create new secret key/i",
                "wait_ms": 1500,
            },
        ],
    },
    {
        "id": "google",
        "name": "Google (Gemini / AI Studio)",
        "login_url": "https://aistudio.google.com/",
        "captures": [
            {"file": "01-signin.png", "url": "https://aistudio.google.com/"},
            {"file": "02-menu.png", "url": "https://aistudio.google.com/apikey"},
            {
                "file": "03-create.png",
                "url": "https://aistudio.google.com/apikey",
                "click": "text=/Create API key/i",
                "wait_ms": 1500,
            },
        ],
    },
]


VIEWPORT = {"width": 1400, "height": 900}


async def _launch_context(p, headless: bool = False):
    """Inicia Chromium com flags anti-detecção pra logins funcionarem.

    Tenta primeiro o Chrome real do sistema (channel=chrome) que é menos
    detectável; se não estiver disponível, cai pro Chromium do Playwright.
    """
    common_args = {
        "headless": headless,
        "viewport": VIEWPORT,
        "args": [
            # Esconde a flag navigator.webdriver=true (principal sinal de automação)
            "--disable-blink-features=AutomationControlled",
        ],
        # User agent realista (sem "HeadlessChrome")
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "ignore_default_args": ["--enable-automation"],
    }

    # Tenta usar Chrome real do sistema primeiro — menos detectável
    try:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            channel="chrome",
            **common_args,
        )
        print("(usando Chrome real do sistema — channel=chrome)")
        return context
    except Exception as exc:
        print(f"(Chrome real não disponível: {exc.__class__.__name__}, usando Chromium do Playwright)")
        return await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            **common_args,
        )


async def setup_mode() -> None:
    """Abre browser headed. Você loga em cada provider manualmente."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print("\n🎬 SETUP MODE")
    print("=" * 60)
    print(f"Profile: {PROFILE_DIR}")
    print()
    print("Vou abrir uma janela do browser com 5 abas (uma por provider).")
    print("Pra cada aba, faça login no seu provider.")
    print()
    print("⚠️  IMPORTANTE: Quando terminar de logar TODOS,")
    print("    FECHE a janela do browser (botão X).")
    print()
    print("O script detecta o close e salva os cookies em tmp/pw-profile/.")
    print()

    async with async_playwright() as p:
        context = await _launch_context(p, headless=False)

        # Esconde o flag navigator.webdriver via JS init (cobertura extra)
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        # Abre uma aba pra cada provider
        for provider in PROVIDERS:
            page = await context.new_page()
            try:
                await page.goto(
                    provider["login_url"], wait_until="domcontentloaded", timeout=30000
                )
            except Exception as exc:
                print(f"  ⚠️ {provider['name']}: erro navegando ({exc.__class__.__name__})")
                continue
            print(f"  • {provider['name']}: aba aberta em {provider['login_url']}")

        print()
        print("⏳ Aguardando você terminar de logar e fechar o browser...")
        print()

        # Polling até o context fechar (user fechou janela)
        try:
            while True:
                if not context.pages:
                    break
                await asyncio.sleep(2)
        except Exception:
            pass

        print()
        print("✅ Setup OK — cookies salvos em", PROFILE_DIR)
        print("   Agora rode: python scripts/capture_screenshots.py capture")


async def capture_single(page: Page, capture: dict) -> None:
    """Executa uma captura individual: navigate → wait → optional click → screenshot."""
    url = capture["url"]
    out_path = OUTPUT_DIR / capture["_provider"] / capture["file"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as exc:
        # Páginas com SSE/long-poll nunca chegam em networkidle
        print(f"   ⚠️ {url}: networkidle timeout ({exc.__class__.__name__}), tentando domcontentloaded")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    wait_ms = capture.get("wait_ms", 1000)
    await page.wait_for_timeout(wait_ms)

    if capture.get("click"):
        selector = capture["click"]
        try:
            await page.click(selector, timeout=5000)
            await page.wait_for_timeout(1500)
        except Exception as exc:
            print(f"   ⚠️ click '{selector}' falhou: {exc.__class__.__name__}")

    await page.screenshot(path=str(out_path), full_page=False)
    rel_path = out_path.relative_to(PROJECT_ROOT)
    print(f"   ✓ {rel_path}")


async def capture_mode() -> None:
    """Reusa profile logado e captura os screenshots."""
    if not PROFILE_DIR.exists():
        print("❌ Profile não existe. Rode primeiro:")
        print("   python scripts/capture_screenshots.py setup")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n📸 CAPTURE MODE")
    print("=" * 60)
    total = sum(len(p["captures"]) for p in PROVIDERS)
    print(f"Vou capturar {total} screenshots em {OUTPUT_DIR.relative_to(PROJECT_ROOT)}/")
    print()

    async with async_playwright() as p:
        context = await _launch_context(p, headless=False)
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        # Usa a primeira aba do persistent context
        page = context.pages[0] if context.pages else await context.new_page()

        for provider in PROVIDERS:
            print(f"\n→ {provider['name']}")
            for cap in provider["captures"]:
                # Injeta o provider id pra capture_single saber onde salvar
                cap_with_provider = {**cap, "_provider": provider["id"]}
                await capture_single(page, cap_with_provider)

        await context.close()
        print()
        print(f"✅ Captura concluída em {OUTPUT_DIR.relative_to(PROJECT_ROOT)}/")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "setup":
        asyncio.run(setup_mode())
    elif mode == "capture":
        asyncio.run(capture_mode())
    else:
        print(f"Modo desconhecido: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
