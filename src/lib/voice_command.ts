// voice_command.ts — Stub para comando de voz no navegador.
//
// Usa a Web Speech API (nativa do Chrome/Edge) para capturar fala e
// transcrever em texto. O usuário pode falar "inclua Súmula 479 do STJ"
// e o sistema injeta a citação no campo de texto correspondente.

"use client";

export interface VoiceCommandCallbacks {
  onResult: (transcript: string, isFinal: boolean) => void;
  onError: (error: string) => void;
  onStart?: () => void;
  onEnd?: () => void;
}

export class VoiceCommandSession {
  private recognition: unknown | null = null;
  private active: boolean = false;
  private callbacks: VoiceCommandCallbacks;

  constructor(callbacks: VoiceCommandCallbacks) {
    this.callbacks = callbacks;
  }

  isSupported(): boolean {
    if (typeof window === "undefined") return false;
    return Boolean((window as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown }).SpeechRecognition) ||
      Boolean((window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition);
  }

  start(): void {
    if (!this.isSupported()) {
      this.callbacks.onError("Reconhecimento de voz não suportado neste navegador. Use Chrome, Edge ou Safari.");
      return;
    }
    if (this.active) return;
    const Ctor = (window as { SpeechRecognition?: new () => unknown }).SpeechRecognition ||
      (window as { webkitSpeechRecognition?: new () => unknown }).webkitSpeechRecognition;
    if (!Ctor) {
      this.callbacks.onError("Reconhecimento de voz indisponível.");
      return;
    }
    const r = new Ctor() as {
      lang: string;
      continuous: boolean;
      interimResults: boolean;
      onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>>; resultIndex: number }) => void;
      onerror: (e: { error: string }) => void;
      onstart: () => void;
      onend: () => void;
      start(): void;
      stop(): void;
    };
    r.lang = "pt-BR";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        const transcript = result[0]?.transcript || "";
        const isFinal = result.isFinal ?? i === e.results.length - 1;
        this.callbacks.onResult(transcript, isFinal);
      }
    };
    r.onerror = (e) => this.callbacks.onError(e.error || "Erro desconhecido");
    r.onstart = () => { this.active = true; this.callbacks.onStart?.(); };
    r.onend = () => { this.active = false; this.callbacks.onEnd?.(); };
    this.recognition = r;
    r.start();
  }

  stop(): void {
    if (this.recognition && typeof (this.recognition as { stop?: () => void }).stop === "function") {
      (this.recognition as { stop: () => void }).stop();
    }
    this.active = false;
  }

  isActive(): boolean {
    return this.active;
  }
}

/** Detecção de comando de voz → ação na peça.
 * Procura padrões como "inclua Súmula X do Y" e converte em ação estruturada. */
export interface ParsedCommand {
  action: "include_citation" | "append_text" | "unknown";
  raw: string;
  citation?: { diploma: string; numero: string };
  text?: string;
}

export function parseVoiceCommand(transcript: string): ParsedCommand {
  const t = transcript.trim();
  // "inclua Súmula 479 do STJ"
  const sumula = t.match(/inclu[ia]\s+s[úu]mula\s+(\d+)\s+d[oe]\s+(STF|STJ|TST|TRF)/i);
  if (sumula) {
    return { action: "include_citation", raw: t, citation: { diploma: `Súmula ${sumula[2].toUpperCase()}`, numero: sumula[1] } };
  }
  // "inclua art. 927 do CC"
  const artigo = t.match(/inclu[ia]\s+art(?:igo)?\.?\s+(\d+(?:[-.]\d+)?)\s+d[oe]\s+(CC|CPC|CP|CDC|CLT|CTN|CLT|CF|Lei\s+[\d.]+\/\d+)/i);
  if (artigo) {
    return { action: "include_citation", raw: t, citation: { diploma: artigo[2].toUpperCase().replace(/\s/g, ""), numero: artigo[1] } };
  }
  // "adicione texto: ..."
  const text = t.match(/adicione\s+texto[:\s]+(.+)/i);
  if (text) {
    return { action: "append_text", raw: t, text: text[1] };
  }
  return { action: "unknown", raw: t };
}