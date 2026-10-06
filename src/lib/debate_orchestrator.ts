// debate_orchestrator.ts — Máquina de estados do Tribunal multi-agente.
//
// Fluxo canônico (5 turnos, com ramos condicionais):
//   T1 Advogado (tese)
//   T2 Promotor (contrário)
//   T3 Juiz (admissibilidade) — se INADMITIR, fim
//   T4 Advogado (réplica)
//   T5 Juiz (sentença)
//
// Decisão de execução: o turno é despachado para a persona correspondente
// via debate_audit (persiste) + runXTurn (executa). Mantém compatibilidade
// com orquestrador se for substituído por BullMQ no futuro.

import { runAdvocateTurn, type AdvocateTurnInput, type AdvocateTurnOutput } from "@/lib/advocate";
import { runProsecutorTurn, type ProsecutorTurnInput, type ProsecutorTurnOutput } from "@/lib/prosecutor";
import { runJudgeTurn, type JudgeTurnInput, type JudgeTurnOutput, type JudgeRole } from "@/lib/judge_turn";
import { saveDebateTurn, type DebateTurnRecord } from "@/lib/debate_audit";
import type { PersonaSlug } from "@/lib/personas";

export type TurnSlot =
  | { kind: "advogado_tese"; index: 1; side: "autor" | "reu" }
  | { kind: "promotor_tese"; index: 2 }
  | { kind: "juiz_admissibilidade"; index: 3 }
  | { kind: "advogado_replica"; index: 4; side: "autor" | "reu" }
  | { kind: "juiz_sentenca"; index: 5 };

export interface StartDebateInput {
  debateId: string;
  caseId: string | null;
  ramoJuridico: string; // área jurídica — "penal", "civil", etc.
  facts: string;
  parteAutora: string; // nome fictício/anonimizado
  parteRe: string;     // nome fictício/anonimizado
  ladoAdvogado: "autor" | "reu"; // default autor
}

export interface AdvanceDebateInput {
  debateId: string;
  ramoJuridico: string;
  facts: string;
  parteAutora: string;
  parteRe: string;
  ladoAdvogado: "autor" | "reu";
  nextIndex: number; // 2, 3, 4 ou 5
  turnsAnteriores: DebateTurnRecord[];
}

export interface DebateTurnResponse {
  index: number;
  persona: PersonaSlug;
  content: string;
  artifactKind?: string;
  citations: DebateTurnRecord["citations"];
  tokensUsed: number;
  latencyMs: number;
  inadmitido?: boolean; // juiz_admissibilidade
  finished?: boolean;   // se inadmitido ou sentença concluída
  savedTurnId: string;
}

const SLOTS: TurnSlot[] = [
  { kind: "advogado_tese", index: 1, side: "autor" },
  { kind: "promotor_tese", index: 2 },
  { kind: "juiz_admissibilidade", index: 3 },
  { kind: "advogado_replica", index: 4, side: "autor" },
  { kind: "juiz_sentenca", index: 5 },
];

function slotByIndex(index: number): TurnSlot | null {
  return SLOTS.find((s) => s.index === index) ?? null;
}

/** Turno 1 — Advogado tese (petição inicial ou defesa). */
export async function executeTurn1(input: StartDebateInput): Promise<DebateTurnResponse> {
  const slot = slotByIndex(1);
  if (!slot || slot.kind !== "advogado_tese") throw new Error("Slot 1 inesperado");

  const advInput: AdvocateTurnInput = {
    facts: input.facts,
    lado: input.ladoAdvogado,
    nomeParte: input.ladoAdvogado === "autor" ? input.parteAutora : input.parteRe,
    nomeAdversario: input.ladoAdvogado === "autor" ? input.parteRe : input.parteAutora,
    area: input.ramoJuridico,
    turno: 1,
  };

  const out: AdvocateTurnOutput = await runAdvocateTurn(advInput);

  const saved = await saveDebateTurn({
    debateId: input.debateId,
    turnNumber: 1,
    persona: "advogado",
    subRole: "tese",
    content: out.content,
    citations: out.citations,
    tokensUsed: out.tokensUsed,
    latencyMs: out.latencyMs,
  });

  return {
    index: 1,
    persona: "advogado",
    content: out.content,
    artifactKind: input.ladoAdvogado === "autor" ? "peticao_inicial" : "contestacao",
    citations: out.citations,
    tokensUsed: out.tokensUsed,
    latencyMs: out.latencyMs,
    finished: false,
    savedTurnId: saved.id,
  };
}

/** Despacho central dos turnos 2..5. */
export async function executeTurn(input: AdvanceDebateInput): Promise<DebateTurnResponse> {
  const slot = slotByIndex(input.nextIndex);
  if (!slot) throw new Error(`Turno inexistente: ${input.nextIndex}`);

  switch (slot.kind) {
    case "promotor_tese": {
      const out: ProsecutorTurnOutput = await runProsecutorTurn({
        facts: input.facts,
        area: input.ramoJuridico,
        nomeVitima: input.ramoJuridico.includes("penal") ? input.parteAutora : undefined,
        nomeAutor: input.ramoJuridico.includes("penal") ? undefined : input.parteAutora,
        nomeAdversario: input.parteRe,
        turnAnteriorAdvogado: lastFromPersona(input.turnsAnteriores, "advogado"),
      });
      const saved = await saveDebateTurn({
        debateId: input.debateId,
        turnNumber: 2,
        persona: "promotor",
        subRole: "contrario",
        content: out.content,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
      });
      return {
        index: 2,
        persona: "promotor",
        content: out.content,
        artifactKind: out.artifactKind,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
        finished: false,
        savedTurnId: saved.id,
      };
    }

    case "juiz_admissibilidade": {
      const role: JudgeRole = "admissibilidade";
      const out: JudgeTurnOutput = await runJudgeTurn({
        facts: input.facts,
        area: input.ramoJuridico,
        role,
        parteAutora: input.parteAutora,
        parteRe: input.parteRe,
        turnsAnteriores: input.turnsAnteriores.map((t) => ({
          persona: t.persona,
          content: t.content,
        })),
      });
      const saved = await saveDebateTurn({
        debateId: input.debateId,
        turnNumber: 3,
        persona: "juiz",
        subRole: "admissibilidade",
        content: out.content,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
        status: out.inadmitido ? "error" : "ok",
      });
      return {
        index: 3,
        persona: "juiz",
        content: out.content,
        artifactKind: out.artifactKind,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
        inadmitido: out.inadmitido,
        finished: out.inadmitido, // se inadmitiu, fim
        savedTurnId: saved.id,
      };
    }

    case "advogado_replica": {
      const out: AdvocateTurnOutput = await runAdvocateTurn({
        facts: input.facts,
        lado: input.ladoAdvogado,
        nomeParte: input.ladoAdvogado === "autor" ? input.parteAutora : input.parteRe,
        nomeAdversario: input.ladoAdvogado === "autor" ? input.parteRe : input.parteAutora,
        area: input.ramoJuridico,
        turno: 3,
        turnsAnteriores: input.turnsAnteriores.map((t) => ({
          persona: t.persona,
          content: t.content,
        })),
      });
      const saved = await saveDebateTurn({
        debateId: input.debateId,
        turnNumber: 4,
        persona: "advogado",
        subRole: "replica",
        content: out.content,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
      });
      return {
        index: 4,
        persona: "advogado",
        content: out.content,
        artifactKind: "replica",
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
        finished: false,
        savedTurnId: saved.id,
      };
    }

    case "juiz_sentenca": {
      const out: JudgeTurnOutput = await runJudgeTurn({
        facts: input.facts,
        area: input.ramoJuridico,
        role: "sentenca",
        parteAutora: input.parteAutora,
        parteRe: input.parteRe,
        turnsAnteriores: input.turnsAnteriores.map((t) => ({
          persona: t.persona,
          content: t.content,
        })),
      });
      const saved = await saveDebateTurn({
        debateId: input.debateId,
        turnNumber: 5,
        persona: "juiz",
        subRole: "sentenca",
        content: out.content,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
      });
      return {
        index: 5,
        persona: "juiz",
        content: out.content,
        artifactKind: out.artifactKind,
        citations: out.citations,
        tokensUsed: out.tokensUsed,
        latencyMs: out.latencyMs,
        finished: true,
        savedTurnId: saved.id,
      };
    }

    default:
      throw new Error(`Slot sem executor: ${(slot as TurnSlot).kind}`);
  }
}

function lastFromPersona(turns: DebateTurnRecord[], persona: PersonaSlug): string | undefined {
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].persona === persona) return turns[i].content;
  }
  return undefined;
}

/** Próximo índice válido, ou null se debate concluído. */
export function nextTurnIndex(currentIndex: number, inadmitido: boolean): number | null {
  if (inadmitido && currentIndex === 3) return null; // inadmitido → fim
  if (currentIndex >= 5) return null;
  return currentIndex + 1;
}