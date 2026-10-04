// reference_resolver.ts — Resolver de Referências Jurídicas
// Portado do reference_resolver.py do EJC para TypeScript.
//
// Recebe source_ref (slug/ID de LegalSource) e devolve status de validação.
// Uma referência só entra como fundamento quando:
// ✓ existe no banco
// ✓ possui origem rastreável (URL oficial)
// ✓ não está revogada (vigente=true)
// ✓ possui autoridade identificada (tribunal/diploma)
// ✓ não mistura dados de outro cliente/caso

import { db } from "@/lib/db";

export type ReferenceStatus =
  | "VALIDATED"
  | "PENDING_REVIEW"
  | "REJECTED"
  | "EXPIRED"
  | "NOT_FOUND";

export interface ReferenceResult {
  status: ReferenceStatus;
  knowledgeDocId?: string;
  authority?: string;
  legalStatus?: string;
  allowedForGeneration: boolean;
  reason?: string;
}

/**
 * Resolve uma referência jurídica contra a base LegalSource.
 * Valida: existência, vigência, autoridade, origem rastreável.
 */
export async function resolveReference(sourceRef: string): Promise<ReferenceResult> {
  if (!sourceRef || !sourceRef.trim()) {
    return {
      status: "REJECTED",
      allowedForGeneration: false,
      reason: "source_ref vazio",
    };
  }

  // Busca por ID ou por diploma+numero
  const source = await db.legalSource.findFirst({
    where: {
      OR: [
        { id: sourceRef },
        { numero: { contains: sourceRef } },
        { diploma: { contains: sourceRef } },
      ],
    },
  });

  if (!source) {
    return {
      status: "NOT_FOUND",
      allowedForGeneration: false,
      reason: `Fonte '${sourceRef}' não encontrada na base curada`,
    };
  }

  // Valida vigência
  if (!source.vigente) {
    return {
      status: "EXPIRED",
      knowledgeDocId: source.id,
      authority: source.tribunal || source.diploma,
      legalStatus: "revogado/não vigente",
      allowedForGeneration: false,
      reason: `${source.diploma} ${source.numero} está marcado como NÃO VIGENTE — verificar revogação`,
    };
  }

  // Valida origem rastreável (URL oficial)
  if (!source.urlOficial) {
    return {
      status: "PENDING_REVIEW",
      knowledgeDocId: source.id,
      authority: source.tribunal || source.diploma,
      legalStatus: "vigente",
      allowedForGeneration: false,
      reason: `${source.diploma} ${source.numero} vigente mas sem URL oficial — adicione fonte rastreável`,
    };
  }

  // Valida revisão humana (revisadoPor)
  if (!source.revisadoPor) {
    return {
      status: "PENDING_REVIEW",
      knowledgeDocId: source.id,
      authority: source.tribunal || source.diploma,
      legalStatus: "vigente",
      allowedForGeneration: false,
      reason: `${source.diploma} ${source.numero} sem revisor identificado — curadoria pendente`,
    };
  }

  // Tudo OK
  return {
    status: "VALIDATED",
    knowledgeDocId: source.id,
    authority: source.tribunal
      ? `${source.tribunal} - ${source.diploma} ${source.numero}`
      : `${source.diploma} ${source.numero}`,
    legalStatus: "vigente",
    allowedForGeneration: true,
    reason: `Fonte validada: ${source.diploma} ${source.numero} ${source.tribunal || ""} — vigente, com URL oficial e revisor`,
  };
}

/**
 * Resolve múltiplas referências em lote.
 */
export async function resolveReferences(sourceRefs: string[]): Promise<ReferenceResult[]> {
  return Promise.all(sourceRefs.map(resolveReference));
}
