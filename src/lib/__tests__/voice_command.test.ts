// voice_command.test.ts — Testes do parser de comandos de voz.

import { test } from "node:test";
import assert from "node:assert/strict";
import { parseVoiceCommand } from "@/lib/voice_command";

test("Reconhece 'inclua Súmula 479 do STJ'", () => {
  const r = parseVoiceCommand("inclua Súmula 479 do STJ na petição");
  assert.equal(r.action, "include_citation");
  assert.equal(r.citation?.diploma, "Súmula STJ");
  assert.equal(r.citation?.numero, "479");
});

test("Reconhece 'inclua art. 927 do CC'", () => {
  const r = parseVoiceCommand("inclua art. 927 do CC nos fundamentos");
  assert.equal(r.action, "include_citation");
  assert.equal(r.citation?.diploma, "CC");
  assert.equal(r.citation?.numero, "927");
});

test("Reconhece 'adicione texto: ...'", () => {
  const r = parseVoiceCommand("adicione texto: também pede indenização por dano moral");
  assert.equal(r.action, "append_text");
  assert.equal(r.text, "também pede indenização por dano moral");
});

test("Desconhece comando não-padrão", () => {
  const r = parseVoiceCommand("olá, como vai?");
  assert.equal(r.action, "unknown");
  assert.equal(r.raw, "olá, como vai?");
});

test("Case-insensitive", () => {
  const r = parseVoiceCommand("INCLUA SÚMULA 359 DO STJ");
  assert.equal(r.action, "include_citation");
  assert.equal(r.citation?.numero, "359");
});