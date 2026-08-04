export type DailyMessage = {
  text: string;
  reference?: string;
  kind: "versiculo" | "motivacao";
};

// Mensagens curtas e auditáveis. Os textos bíblicos são paráfrases breves,
// acompanhadas da referência, para evitar dependência de API externa.
export const DAILY_MESSAGES: readonly DailyMessage[] = [
  {
    text: "Confie no Senhor de todo o coração e siga com sabedoria.",
    reference: "Provérbios 3:5-6",
    kind: "versiculo",
  },
  {
    text: "A justiça e a verdade sustentam o trabalho bem realizado.",
    reference: "Salmos 89:14",
    kind: "versiculo",
  },
  {
    text: "Seja firme, corajoso e não desanime diante dos desafios.",
    reference: "Josué 1:9",
    kind: "versiculo",
  },
  {
    text: "Entregue seus planos ao Senhor e trabalhe com propósito.",
    reference: "Provérbios 16:3",
    kind: "versiculo",
  },
  {
    text: "A resposta serena e prudente abre caminhos para a solução.",
    reference: "Provérbios 15:1",
    kind: "versiculo",
  },
  {
    text: "Faça tudo com dedicação, responsabilidade e excelência.",
    reference: "Colossenses 3:23",
    kind: "versiculo",
  },
  {
    text: "A sabedoria começa pela disposição de ouvir e aprender.",
    reference: "Provérbios 1:5",
    kind: "versiculo",
  },
  {
    text: "Planejamento claro transforma esforço em resultado consistente.",
    kind: "motivacao",
  },
  {
    text: "Priorize o essencial, conclua o urgente e registre cada avanço.",
    kind: "motivacao",
  },
  {
    text: "Excelência jurídica nasce da atenção aos detalhes.",
    kind: "motivacao",
  },
  {
    text: "Organização hoje evita urgências desnecessárias amanhã.",
    kind: "motivacao",
  },
  {
    text: "Decisões seguras combinam técnica, prudência e responsabilidade.",
    kind: "motivacao",
  },
  {
    text: "Cada providência registrada fortalece a segurança do trabalho.",
    kind: "motivacao",
  },
  {
    text: "Clareza no processo traz tranquilidade para a equipe e o cliente.",
    kind: "motivacao",
  },
];

export function getDailyMessage(date = new Date()): DailyMessage {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0);
  const current = Date.UTC(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate(),
  );
  const dayOfYear = Math.floor((current - start) / 86_400_000);
  return DAILY_MESSAGES[dayOfYear % DAILY_MESSAGES.length];
}
