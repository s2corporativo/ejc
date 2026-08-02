// Persistência do rascunho da Entrada Única em sessionStorage: a proposta
// editada sobrevive ao F5, mas morre com a aba (dados pessoais extraídos de
// documentos não devem durar além da sessão — LGPD).
import type { Proposta } from "./types";

const PONTEIRO = "ejc_entrada_rascunho_atual";
const PREFIXO = "ejc_entrada_rascunho:";

export function salvarRascunho(p: Proposta): void {
  try {
    sessionStorage.setItem(PONTEIRO, p.rascunhoId);
    sessionStorage.setItem(PREFIXO + p.rascunhoId, JSON.stringify(p));
  } catch {
    // Storage cheio/indisponível não pode derrubar a tela.
  }
}

export function carregarRascunho(): Proposta | null {
  try {
    const id = sessionStorage.getItem(PONTEIRO);
    if (!id) return null;
    const raw = sessionStorage.getItem(PREFIXO + id);
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
    const id = sessionStorage.getItem(PONTEIRO);
    if (id) sessionStorage.removeItem(PREFIXO + id);
    sessionStorage.removeItem(PONTEIRO);
  } catch {
    // idem
  }
}
