// Persistência do rascunho da Entrada Única em sessionStorage: a proposta
// editada sobrevive ao F5, mas morre com a aba (dados pessoais extraídos de
// documentos não devem durar além da sessão — LGPD).
//
// Onda B (contrato único de rascunho): as chaves derivam do prefixo fonte
// única (lib/rascunho/contrato.ts). A limpeza de logout deste rascunho NÃO
// mora aqui — está registrada em lib/rascunho/registro.ts (varredura do
// prefixo), pois o módulo da página é lazy: só carrega quando o usuário
// abre a Entrada Única, e o logout não pode depender disso.
import {
  RASCUNHO_ENTRADA_PREFIXO,
  storageSessao,
} from "../../lib/rascunho/contrato";
import type { Proposta } from "./types";

const PONTEIRO = `${RASCUNHO_ENTRADA_PREFIXO}_atual`;
const PREFIXO = `${RASCUNHO_ENTRADA_PREFIXO}:`;

export function salvarRascunho(p: Proposta): void {
  try {
    const s = storageSessao();
    if (!s) return;
    s.setItem(PONTEIRO, p.rascunhoId);
    s.setItem(PREFIXO + p.rascunhoId, JSON.stringify(p));
  } catch {
    // Storage cheio/indisponível não pode derrubar a tela.
  }
}

export function carregarRascunho(): Proposta | null {
  try {
    const s = storageSessao();
    if (!s) return null;
    const id = s.getItem(PONTEIRO);
    if (!id) return null;
    const raw = s.getItem(PREFIXO + id);
    if (!raw) return null;
    const p = JSON.parse(raw) as Proposta;
    if (!p || typeof p !== "object" || typeof p.rascunhoId !== "string") {
      return null;
    }
    return p;
  } catch {
    return null;
  }
}

export function limparRascunho(): void {
  try {
    const s = storageSessao();
    if (!s) return;
    const id = s.getItem(PONTEIRO);
    if (id) s.removeItem(PREFIXO + id);
    s.removeItem(PONTEIRO);
  } catch {
    // idem
  }
}
