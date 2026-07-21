import { ArrowLeft, BellRing, ExternalLink, ListChecks, Send } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { SiteHeader } from "@/components/SiteHeader";
import { getCategoryStyle } from "@/lib/categoryStyles";
import { BOT_COMMANDS, BOT_URL, BOT_USERNAME } from "@/lib/telegram";
import type { CategoryCount } from "@/lib/types";

export const metadata: Metadata = {
  title: "Alertas no Telegram — Outlet Watch",
  description:
    "Receba no Telegram um aviso sempre que um notebook do outlet Lenovo mudar de preço.",
};

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:5000";

// Lines shown when the API can't be reached — this page is instructions, so it
// must still render if the monitor is down.
const FALLBACK_LINES = ["ThinkPad", "IdeaPad", "Yoga", "Legion", "LOQ", "V Series", "ThinkBook"];

async function getLines(): Promise<string[]> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/categories`, { cache: "no-store" });
    if (!res.ok) return FALLBACK_LINES;
    const categories = (await res.json()) as CategoryCount[];
    return categories.length > 0 ? categories.map((c) => c.category) : FALLBACK_LINES;
  } catch {
    return FALLBACK_LINES;
  }
}

const STEPS = [
  {
    icon: Send,
    title: "Abra o bot no Telegram",
    body: (
      <>
        Toque no botão acima ou procure por <Code>@{BOT_USERNAME}</Code> no aplicativo.
      </>
    ),
  },
  {
    icon: BellRing,
    title: "Envie /start",
    body: (
      <>
        Pronto, você já está inscrito. A partir daí recebe um relatório sempre que algum
        preço mudar.
      </>
    ),
  },
  {
    icon: ListChecks,
    title: "Escolha o que acompanhar",
    body: (
      <>
        No menu que aparece, toque nas linhas que te interessam. Sem nenhuma marcada, você
        recebe <strong className="font-medium text-ink">todas</strong> as mudanças.
      </>
    ),
  },
];

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-[0.9em] text-ink">
      {children}
    </code>
  );
}

function TelegramButton({ className = "" }: { className?: string }) {
  return (
    <a
      href={BOT_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={`flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-transform hover:scale-[1.03] ${className}`}
    >
      <Send className="h-4 w-4" />
      Abrir o bot no Telegram
      <ExternalLink className="h-3.5 w-3.5 opacity-70" />
    </a>
  );
}

export default async function AlertasPage() {
  const lines = await getLines();

  return (
    <div className="flex min-h-screen flex-col bg-page">
      <SiteHeader>
        <Link
          href="/"
          className="flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm font-medium text-ink-secondary transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          Ver preços
        </Link>
      </SiteHeader>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-12 px-6 py-12">
        <section className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <span className="flex items-center gap-2 text-sm font-medium text-accent">
              <BellRing className="h-4 w-4" />
              Alertas de preço
            </span>
            <h1 className="text-4xl font-semibold tracking-tight text-ink md:text-5xl">
              Receba as quedas de preço no <span className="text-accent">Telegram</span>
            </h1>
            <p className="max-w-xl text-base text-ink-secondary">
              Toda vez que um notebook do outlet muda de preço ou aparece pela primeira vez,
              o bot te manda um relatório. Você escolhe quais linhas quer acompanhar.
            </p>
          </div>
          <TelegramButton className="self-start" />
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-ink">Como se cadastrar</h2>
          <ol className="flex flex-col gap-3">
            {STEPS.map(({ icon: Icon, title, body }, index) => (
              <li
                key={title}
                className="flex gap-4 rounded-2xl border border-border bg-surface p-5"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-ink">
                  {index + 1}
                </span>
                <div className="flex flex-col gap-1">
                  <span className="flex items-center gap-2 font-medium text-ink">
                    <Icon className="h-4 w-4 text-accent" />
                    {title}
                  </span>
                  <p className="text-sm text-ink-secondary">{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold text-ink">Linhas que você pode acompanhar</h2>
            <p className="text-sm text-ink-secondary">
              As mesmas categorias do catálogo. Marque quantas quiser em <Code>/produtos</Code>.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {lines.map((line) => (
              <span
                key={line}
                className="flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 text-sm text-ink-secondary"
              >
                <span className={`h-2 w-2 rounded-full ${getCategoryStyle(line).dotClassName}`} />
                {line}
              </span>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-ink">Comandos do bot</h2>
          <div className="overflow-hidden rounded-2xl border border-border">
            {BOT_COMMANDS.map(({ command, description, aliases }, index) => (
              <div
                key={command}
                className={`flex flex-col gap-1 bg-surface p-4 sm:flex-row sm:items-baseline sm:gap-4 ${
                  index > 0 ? "border-t border-border" : ""
                }`}
              >
                <span className="shrink-0 sm:w-24">
                  <Code>{command}</Code>
                </span>
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm text-ink">{description}</span>
                  <span className="text-xs text-ink-muted">
                    Também funciona como {aliases.join(", ")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-6">
          <h2 className="font-medium text-ink">O que o bot guarda sobre você</h2>
          <p className="text-sm text-ink-secondary">
            Apenas o identificador da sua conversa com ele e as linhas que você marcou — o
            suficiente para saber para onde mandar o alerta. Nada de nome, telefone ou
            e-mail. Enviar <Code>/parar</Code> apaga tudo isso.
          </p>
          <TelegramButton className="self-start" />
        </section>
      </main>
    </div>
  );
}
