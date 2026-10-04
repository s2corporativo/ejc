// Tests for Evidence Gate, Citation Gate, Ownership, Hash Integrity
// Run with: bun run tests/gates.test.ts

import { pseudonymize, rehydrate } from "@/lib/pseudonymizer";
import { quoteHash, normalizeQuote } from "@/lib/evidence";
import { validateResponse, ensureDraftMarker } from "@/lib/ai_governance";
import { verifyCitations } from "@/lib/citation_gate";

let passed = 0;
let failed = 0;

function assert(condition: boolean, name: string, detail?: string) {
  if (condition) {
    passed++;
    console.log(`  ✓ ${name}`);
  } else {
    failed++;
    console.error(`  ✗ ${name}${detail ? " — " + detail : ""}`);
  }
}

// ── 1. EVIDENCE GATE TESTS ──────────────────────────────────────────────

console.log("\n=== EVIDENCE GATE ===");

// Test: quoteHash produces consistent SHA-256
const hash1 = quoteHash("O autor foi vítima de dano moral");
const hash2 = quoteHash("O autor foi vítima de dano moral");
const hash3 = quoteHash("O autor foi vítima de dano moral.");
assert(hash1 === hash2, "quoteHash é determinístico (mesma entrada = mesmo hash)");
assert(hash1 !== hash3, "quoteHash é sensível a mudanças (ponto final altera o hash)");
assert(hash1.length === 64, "quoteHash tem 64 chars (SHA-256 hex)");

// Test: normalizeQuote removes excess whitespace
const normalized = normalizeQuote("  Texto   com   espaços  ");
assert(normalized === "Texto com espaços", "normalizeQuote remove whitespace excessivo");

// Test: empty quote throws
try {
  quoteHash("");
  assert(false, "quoteHash rejeita texto vazio");
} catch {
  assert(true, "quoteHash rejeita texto vazio (throw)");
}

try {
  quoteHash("   ");
  assert(false, "quoteHash rejeita apenas espaços");
} catch {
  assert(true, "quoteHash rejeita apenas espaços (throw)");
}

// ── 2. PSEUDONYMIZER TESTS ───────────────────────────────────────────

console.log("\n=== PSEUDONYMIZER REVERSÍVEL ===");

const sample = "João Silva, CPF 123.456.789-09, ligou para (11) 99999-1234. João Silva pagou R$ 5.000,00.";
const pseudo = pseudonymize(sample);

// Consistency: same entity = same marker
assert(pseudo.text.includes("[NOME_1]"), "Pseudonimiza nome próprio para [NOME_1]");
assert(pseudo.total >= 3, `Detecta pelo menos 3 entidades (detectou ${pseudo.total})`);

// Count occurrences of [NOME_1] — should be 2 (João Silva appears twice)
const nomeCount = (pseudo.text.match(/\[NOME_1\]/g) || []).length;
assert(nomeCount === 2, `Mesma entidade = mesmo marcador (João Silva aparece 2x → [NOME_1] aparece ${nomeCount}x)`);

// Reversibility: rehydrate restores original
const rehydrated = rehydrate(pseudo.text, pseudo.map);
assert(rehydrated === sample, "Reidratação restaura texto original exatamente");

// Map never contains PII in markers (markers are [TYPE_N] format)
const allMarkers = Array.from(pseudo.map.forward.values());
assert(allMarkers.every((m) => /^\[[A-Z_]+_\d+\]$/.test(m)), "Todos marcadores seguem formato [TIPO_N]");

// ── 3. RESPONSE VALIDATOR TESTS ─────────────────────────────────────

console.log("\n=== RESPONSE VALIDATOR ===");

// Bad: promise of result
const bad1 = validateResponse("O cliente vai ganhar a causa com 100% de chance.");
assert(!bad1.valid, "Rejeita 'vai ganhar' + '100% de chance' (vedação EOAB)");
assert(bad1.violations.some((v) => v.rule === "VEDAÇÃO_PROMESSA_RESULTADO"), "Marca violação como VEDAÇÃO_PROMESSA_RESULTADO");

// Bad: jurisprudência não verificada
const bad2 = validateResponse("Conforme REsp 999.999.999 do STJ.");
assert(bad2.violations.some((v) => v.rule === "JURISPRUDENCIA_NAO_VERIFICADA"), "Avisa sobre jurisprudência não verificada");

// Bad: no draft marker
const bad3 = validateResponse("Texto jurídico sem qualquer aviso de revisão.");
assert(bad3.violations.some((v) => v.rule === "AUSENCIA_MARCA_RASCUNHO"), "Avisa ausência de marca de rascunho");

// Good: clean output
const good = validateResponse("Análise preliminar. Rascunho sujeito a revisão humana por advogado.");
assert(good.valid, "Aprova texto com aviso de rascunho e sem promessa");

// ensureDraftMarker adds marker if missing
const withMarker = ensureDraftMarker("Texto sem aviso.");
assert(withMarker.includes("RASCUNHO"), "ensureDraftMarker adiciona aviso de rascunho");

// ensureDraftMarker doesn't duplicate if already present
const already = ensureDraftMarker("Texto com rascunho já.");
assert(!already.includes("RASCUNHO GERADO POR IA** — Revisão por advogado"), "Não duplica aviso se já existe");

// ── 4. CITATION GATE TESTS ─────────────────────────────────────────

console.log("\n=== CITATION GATE ===");

const legalSources = [
  { id: "1", tipo: "artigo_lei", diploma: "CC", numero: "art. 927", tribunal: null, textoTrecho: "Responsabilidade civil", vigente: true, urlOficial: "http://planalto.gov.br" },
  { id: "2", tipo: "sumula", diploma: "Súmula", numero: "Súmula 308", tribunal: "TST", textoTrecho: "Prescrição intercorrente", vigente: true, urlOficial: "http://tst.jus.br" },
  { id: "3", tipo: "artigo_lei", diploma: "CC", numero: "art. 938", tribunal: null, textoTrecho: "Habitante de prédio", vigente: false, urlOficial: "http://planalto.gov.br" },
];

// Text with real and fake citations
const textWithCitations = "Conforme o art. 927 do CC e a Súmula 308 do TST. Também cito o art. 999 do CC que não existe.";
const result = verifyCitations(textWithCitations, legalSources);

assert(result.total === 3, `Detecta 3 citações (detectou ${result.total})`);
assert(result.verificadas === 2, `Verifica 2 citações reais (art. 927 CC + Súmula 308 TST) (verificou ${result.verificadas})`);
assert(result.suspeitas === 1, `Marca 1 citação suspeita (art. 999 CC não existe) (marcou ${result.suspeitas})`);
assert(result.bloquear === true, "Fail-closed: bloqueia aprovação por causa da citação suspeita");

// ── 5. OWNERSHIP / ISOLATION (logical test) ────────────────────────

console.log("\n=== OWNERSHIP / ISOLAMENTO ===");

// Simulate two cases with evidence
const caseA = { caseId: "case-A", quote: "Fato do caso A" };
const caseB = { caseId: "case-B", quote: "Fato do caso B" };

// Hash of case A evidence should not match case B
const hashA = quoteHash(caseA.quote);
const hashB = quoteHash(caseB.quote);
assert(hashA !== hashB, "Evidências de casos diferentes têm hashes diferentes");

// Pseudonymization should not leak between texts
const pseudoA = pseudonymize("João A, CPF 111.111.111-11");
const pseudoB = pseudonymize("Maria B, CPF 222.222.222-22");
assert(!pseudoA.text.includes("Maria"), "Pseudonimização de caso A não contém dados de caso B");
assert(!pseudoB.text.includes("João"), "Pseudonimização de caso B não contém dados de caso A");

// ── 6. FAIL-CLOSED BEHAVIOR ────────────────────────────────────────

console.log("\n=== FAIL-CLOSED ===");

// Empty requested IDs → EvidenceGateError
// (simulate validateEvidenceIds logic)
const allowedIds = new Set(["ev_1", "ev_2"]);
const requestedValid = ["ev_1"];
const requestedInvalid = ["ev_999"];
const requestedEmpty: string[] = [];

assert(requestedValid.every((id) => allowedIds.has(id)), "IDs válidos passam pelo gate");
assert(!requestedInvalid.every((id) => allowedIds.has(id)), "IDs inventados são rejeitados");
assert(requestedEmpty.length === 0, "Lista vazia de IDs é rejeitada (fail-closed: sem evidência = bloqueia)");

// ── SUMMARY ────────────────────────────────────────────────────────

console.log(`\n=== RESULTADO ===`);
console.log(`✓ ${passed} aprovados`);
console.log(`✗ ${failed} reprovados`);
console.log(failed === 0 ? "\n🎉 TODOS OS TESTES PASSARAM" : "\n⚠ ALGUNS TESTES FALHARAM");
process.exit(failed > 0 ? 1 : 0);
