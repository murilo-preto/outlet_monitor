// The bot users are sent to. Overridable so a fork or a staging bot doesn't
// need a code change.
export const BOT_USERNAME = process.env.TELEGRAM_BOT_USERNAME ?? "lenovo_outlet_bot";

export const BOT_URL = `https://t.me/${BOT_USERNAME}`;

interface BotCommand {
  command: string;
  description: string;
  aliases: string[];
}

// Mirrors the handlers registered in telegram_notifier/app/bot.py.
export const BOT_COMMANDS: BotCommand[] = [
  {
    command: "/start",
    description: "Começa a receber os alertas",
    aliases: ["/inscrever", "/assinar", "/iniciar", "/comecar"],
  },
  {
    command: "/produtos",
    description: "Abre o menu para escolher as linhas que você acompanha",
    aliases: ["/filtros", "/seguir", "/linhas", "/escolher"],
  },
  {
    command: "/ajuda",
    description: "Mostra se você está inscrito e o que está acompanhando",
    aliases: ["/help", "/status", "/comandos"],
  },
  {
    command: "/parar",
    description: "Cancela os alertas",
    aliases: ["/stop", "/cancelar", "/sair", "/descadastrar"],
  },
];
