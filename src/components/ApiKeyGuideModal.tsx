/**
 * Modal de instruções passo a passo de como obter uma API key
 * pra cada um dos 5 providers suportados pelo Eskuta.
 *
 * Princípios:
 * - Texto claro pra usuário não-técnico
 * - Botão pra abrir o console do provider em nova aba
 * - Screenshots reais embedados (public/api-key-guides/{provider}/)
 * - Sem dependência externa (sem Shadcn Dialog, é HTML+CSS puro)
 */

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ApiKeyProvider } from "@/types/meeting";

/**
 * Hotspot é uma anotação visual sobreposta ao screenshot — indica
 * com um círculo vermelho pulsante onde o usuário deve clicar.
 * Coordenadas em % (responsivo) ao tamanho original da imagem.
 */
interface GuideHotspot {
  /** Posição X do CENTRO do círculo, ex: "62%" */
  x: string;
  /** Posição Y do CENTRO do círculo, ex: "38%" */
  y: string;
  /** Tamanho do círculo (CSS), ex: "48px" (default) */
  size?: string;
  /** Texto exibido ao lado do círculo, ex: "Clique aqui" */
  label?: string;
  /** Posição do label: "right" | "left" | "below" | "above" (default: "right") */
  labelPosition?: "right" | "left" | "below" | "above";
}

interface GuideStep {
  text: string;
  screenshot?: string; // path relativo a public/
  hotspot?: GuideHotspot;
}

interface ProviderGuide {
  name: string;
  consoleUrl: string;
  cost: string;
  steps: GuideStep[];
  notes?: string;
}

const GUIDES: Record<ApiKeyProvider, ProviderGuide> = {
  groq: {
    name: "Groq",
    consoleUrl: "https://console.groq.com/keys",
    cost: "Free tier generoso (reuniões pessoais costumam ficar de boa). Acima do free, ~US$ 0,04 por hora de áudio.",
    steps: [
      {
        text: "Acesse console.groq.com e crie uma conta (não pede cartão de crédito).",
        screenshot: "/api-key-guides/groq/01-signup.png",
      },
      {
        text: "Após login, vá no menu lateral em 'API Keys'.",
        screenshot: "/api-key-guides/groq/02-menu.png",
      },
      {
        text: "Clique em 'Create API Key'. Dê um nome (ex: 'Eskuta App') e confirme.",
        screenshot: "/api-key-guides/groq/03-create.png",
      },
      {
        text: "COPIE a chave que aparece — ela só é mostrada UMA vez. Comece com 'gsk_'.",
        screenshot: "/api-key-guides/groq/04-copy.png",
      },
      {
        text: "Volte aqui e cole no campo abaixo. Clique em 'Salvar e testar'.",
      },
    ],
    notes:
      "Modelo usado: whisper-large-v3-turbo (transcrição rápida e barata).",
  },
  assemblyai: {
    name: "AssemblyAI",
    consoleUrl: "https://www.assemblyai.com/app/api-keys",
    cost: "100 horas/mês grátis. Acima disso, ~US$ 0,12 por hora.",
    steps: [
      {
        text: "Acesse assemblyai.com e crie uma conta (oferece teste grátis sem cartão).",
        screenshot: "/api-key-guides/assemblyai/01-signup.png",
      },
      {
        text: "Após login, vá em 'API Keys' no menu (sidebar à esquerda).",
        screenshot: "/api-key-guides/assemblyai/02-menu.png",
      },
      {
        text: "Copie a chave que aparece no topo da página.",
        screenshot: "/api-key-guides/assemblyai/03-copy.png",
      },
      {
        text: "Volte aqui e cole no campo abaixo. Clique em 'Salvar e testar'.",
      },
    ],
    notes:
      "Usado como fallback automático quando Groq retorna erro ou está fora.",
  },
  anthropic: {
    name: "Anthropic (Claude)",
    consoleUrl: "https://console.anthropic.com/settings/keys",
    cost: "Sem free tier. Reunião de 1h consome ~US$ 0,02 em tokens.",
    steps: [
      {
        text: "Acesse console.anthropic.com e crie uma conta.",
        screenshot: "/api-key-guides/anthropic/01-signup.png",
      },
      {
        text: "Adicione crédito (mínimo US$ 5) — é necessário pra gerar a key.",
        screenshot: "/api-key-guides/anthropic/02-credits.png",
      },
      {
        text: "Vá em 'API Keys' nas configurações e clique em 'Create Key'.",
        screenshot: "/api-key-guides/anthropic/03-create.png",
      },
      {
        text: "Dê um nome (ex: 'Eskuta') e COPIE a chave (começa com 'sk-ant-').",
        screenshot: "/api-key-guides/anthropic/04-copy.png",
      },
      {
        text: "Volte aqui, cole no campo abaixo e clique em 'Salvar e testar'.",
      },
    ],
    notes:
      "Modelo: claude-sonnet-4-5. Melhor relação qualidade/custo pra atas.",
  },
  openai: {
    name: "OpenAI (GPT)",
    consoleUrl: "https://platform.openai.com/api-keys",
    cost: "Sem free tier estável. Reunião de 1h consome ~US$ 0,03 em tokens.",
    steps: [
      {
        text: "Acesse platform.openai.com e faça login (ou crie conta).",
        screenshot: "/api-key-guides/openai/01-signup.png",
      },
      {
        text: "Adicione crédito em 'Billing' (mínimo US$ 5).",
        screenshot: "/api-key-guides/openai/02-billing.png",
      },
      {
        text: "Vá em 'API keys' e clique em '+ Create new secret key'.",
        screenshot: "/api-key-guides/openai/03-create.png",
      },
      {
        text: "Dê um nome (ex: 'Eskuta') e COPIE a chave (começa com 'sk-proj-').",
        screenshot: "/api-key-guides/openai/04-copy.png",
      },
      {
        text: "Volte aqui, cole no campo abaixo e clique em 'Salvar e testar'.",
      },
    ],
    notes: "Modelo: gpt-4o (mais barato que Claude, qualidade comparável).",
  },
  google: {
    name: "Google (Gemini)",
    consoleUrl: "https://aistudio.google.com/apikey",
    cost: "Free tier amplo (1500 requisições/dia). Pagas, ~US$ 0,01 por reunião de 1h.",
    steps: [
      {
        text: "Acesse aistudio.google.com e faça login com sua conta Google.",
        screenshot: "/api-key-guides/google/01-signin.png",
      },
      {
        text: "Clique em 'Get API key' no menu lateral.",
        screenshot: "/api-key-guides/google/02-menu.png",
      },
      {
        text: "Clique em 'Create API key' e selecione um projeto (ou crie um novo).",
        screenshot: "/api-key-guides/google/03-create.png",
      },
      {
        text: "COPIE a chave que aparece (começa com 'AIza').",
        screenshot: "/api-key-guides/google/04-copy.png",
      },
      {
        text: "Volte aqui, cole no campo abaixo e clique em 'Salvar e testar'.",
      },
    ],
    notes:
      "Modelo: gemini-2.0-flash. Opção mais barata, qualidade boa pra atas simples.",
  },
};

export interface ApiKeyGuideModalProps {
  provider: ApiKeyProvider;
  onClose: () => void;
}

export function ApiKeyGuideModal({ provider, onClose }: ApiKeyGuideModalProps) {
  const guide = GUIDES[provider];
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Foco automático no botão de fechar quando o modal abre
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, []);

  // Fecha com Esc
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const openConsole = () => {
    // window.open com noopener,noreferrer pra segurança
    window.open(guide.consoleUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="api-key-guide-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        // Click no backdrop fecha
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-lg border bg-background p-6 shadow-lg">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="api-key-guide-title"
              className="text-xl font-semibold tracking-tight"
            >
              Como obter sua chave do {guide.name}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              <strong>Custo:</strong> {guide.cost}
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </header>

        <ol className="mt-6 space-y-5">
          {guide.steps.map((step, idx) => (
            <li key={idx} className="flex gap-3">
              <span
                aria-hidden="true"
                className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground"
              >
                {idx + 1}
              </span>
              <div className="flex-1">
                <p className="text-sm">{step.text}</p>
                {step.screenshot && (
                  <ScreenshotWithHotspot
                    src={step.screenshot}
                    alt={`Passo ${idx + 1}: ${step.text}`}
                    hotspot={step.hotspot}
                  />
                )}
              </div>
            </li>
          ))}
        </ol>

        {guide.notes && (
          <div className="mt-6 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-900 dark:text-amber-200">
            <strong>Nota:</strong> {guide.notes}
          </div>
        )}

        <div className="mt-6 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs">
          🔒{" "}
          <strong>
            Sua chave fica criptografada no keyring do seu sistema
          </strong>{" "}
          (Credential Manager no Windows, Keychain no macOS). Nunca em arquivo,
          nunca no nosso servidor — a gente não tem servidor.
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" onClick={openConsole}>
            Abrir {guide.consoleUrl.replace(/^https?:\/\//, "")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Screenshot + overlay opcional de hotspot — desenha um círculo
 * vermelho pulsante na posição (x, y) em % da imagem + label "Clique aqui".
 * Se hotspot é undefined ou o PNG não existe, renderiza só a imagem
 * (ou nada, em caso de erro 404).
 */
function ScreenshotWithHotspot({
  src,
  alt,
  hotspot,
}: {
  src: string;
  alt: string;
  hotspot?: GuideHotspot;
}) {
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;

  const size = hotspot?.size ?? "48px";
  const labelPos = hotspot?.labelPosition ?? "right";
  const labelStyle: Record<string, string> = {};
  if (labelPos === "right") {
    labelStyle.left = `calc(${hotspot?.x} + ${size} / 2 + 12px)`;
    labelStyle.top = hotspot?.y ?? "0";
    labelStyle.transform = "translateY(-50%)";
  } else if (labelPos === "left") {
    labelStyle.right = `calc(100% - ${hotspot?.x} + ${size} / 2 + 12px)`;
    labelStyle.top = hotspot?.y ?? "0";
    labelStyle.transform = "translateY(-50%)";
  } else if (labelPos === "below") {
    labelStyle.left = hotspot?.x ?? "0";
    labelStyle.top = `calc(${hotspot?.y} + ${size} / 2 + 8px)`;
    labelStyle.transform = "translateX(-50%)";
  } else {
    labelStyle.left = hotspot?.x ?? "0";
    labelStyle.bottom = `calc(100% - ${hotspot?.y} + ${size} / 2 + 8px)`;
    labelStyle.transform = "translateX(-50%)";
  }

  return (
    <div className="relative mt-2 inline-block max-w-full">
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className="block max-w-full rounded border shadow-sm"
        onError={() => setHidden(true)}
      />
      {hotspot && (
        <>
          {/* Círculo pulsante centrado em (x, y) */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute rounded-full border-[3px] border-red-500 animate-pulse shadow-[0_0_0_3px_rgba(239,68,68,0.25)]"
            style={{
              left: hotspot.x,
              top: hotspot.y,
              width: size,
              height: size,
              transform: "translate(-50%, -50%)",
            }}
          />
          {hotspot.label && (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute whitespace-nowrap rounded bg-red-500 px-2 py-0.5 text-xs font-semibold text-white shadow"
              style={labelStyle}
            >
              {hotspot.label}
            </div>
          )}
        </>
      )}
    </div>
  );
}
