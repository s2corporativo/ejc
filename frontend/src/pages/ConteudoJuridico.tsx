// ── FAQ & Glossário (E1) ─────────────────────────────────────────────────────
// O backend (/conteudo/faq e /conteudo/glossario) devolve rascunho de IA com
// `is_rascunho`, `aviso`, `aviso_hitl` e `log_id` (trilha HITL). Esta tela
// mostra a faixa âmbar de revisão humana, guarda o `log_id` para auditoria e
// tenta apresentar o conteúdo estruturado (JSON com `faq[]`/`glossario[]`)
// antes de cair no texto cru. Erros passam por `mensagemErroIA` — nunca o
// `detail` técnico.
import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";
import { mensagemErroIA } from "../lib/iaErro";
import { AREAS_OPCOES_DESTAQUE } from "../lib/taxonomia";

export type ItemFaq = { pergunta: string; resposta: string };
export type ItemGlossario = { termo: string; definicao: string };

export type ResultadoConteudo = {
  conteudo: string;
  is_rascunho: boolean;
  aviso: string;
  aviso_hitl: string;
  log_id: string | null;
  modelo?: string;
};

export const AVISO_RASCUNHO_PADRAO =
  "Rascunho gerado por IA — revisar antes de publicar (pode conter imprecisões).";

function texto(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

/** Normaliza a resposta do backend preservando os campos HITL. */
export function normalizarConteudo(data: unknown): ResultadoConteudo {
  const d = (data ?? {}) as Record<string, unknown>;
  const aviso = texto(d.aviso) || texto(d.aviso_hitl) || AVISO_RASCUNHO_PADRAO;
  return {
    conteudo: texto(d.conteudo),
    // Ausência do campo não significa "revisado": rascunho por padrão.
    is_rascunho: d.is_rascunho === false ? false : true,
    aviso,
    aviso_hitl: texto(d.aviso_hitl) || aviso,
    log_id: typeof d.log_id === "string" ? d.log_id : null,
    modelo: typeof d.modelo === "string" ? d.modelo : undefined,
  };
}

function extrairJson(conteudo: string): unknown {
  const bruto = conteudo.trim();
  const candidatos = [bruto];
  const cerca = bruto.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (cerca?.[1]) candidatos.unshift(cerca[1].trim());
  const ini = bruto.search(/[[{]/);
  if (ini > 0) candidatos.push(bruto.slice(ini));
  for (const c of candidatos) {
    try {
      return JSON.parse(c);
    } catch {
      /* tenta o próximo candidato */
    }
  }
  return null;
}

/** `faq[]` a partir do conteúdo (JSON `{faq:[...]}` ou array); `null` = texto. */
export function parsearFaq(conteudo: string): ItemFaq[] | null {
  const json = extrairJson(conteudo);
  const lista = Array.isArray(json)
    ? json
    : json && typeof json === "object"
      ? (json as { faq?: unknown; itens?: unknown; perguntas?: unknown }).faq ??
        (json as { itens?: unknown }).itens ??
        (json as { perguntas?: unknown }).perguntas
      : null;
  if (!Array.isArray(lista)) return null;
  const itens = lista.flatMap((it) => {
    if (!it || typeof it !== "object") return [];
    const o = it as Record<string, unknown>;
    const pergunta = texto(o.pergunta ?? o.question ?? o.q);
    const resposta = texto(o.resposta ?? o.answer ?? o.a);
    return pergunta && resposta ? [{ pergunta, resposta }] : [];
  });
  return itens.length ? itens : null;
}

/** `glossario[]` a partir do conteúdo; `null` = texto. */
export function parsearGlossario(conteudo: string): ItemGlossario[] | null {
  const json = extrairJson(conteudo);
  const lista = Array.isArray(json)
    ? json
    : json && typeof json === "object"
      ? (json as { glossario?: unknown }).glossario ??
        (json as { termos?: unknown }).termos ??
        (json as { itens?: unknown }).itens
      : null;
  if (!Array.isArray(lista)) return null;
  const itens = lista.flatMap((it) => {
    if (!it || typeof it !== "object") return [];
    const o = it as Record<string, unknown>;
    const termo = texto(o.termo ?? o.term ?? o.nome);
    const definicao = texto(o.definicao ?? o.definition ?? o.significado);
    return termo && definicao ? [{ termo, definicao }] : [];
  });
  return itens.length ? itens : null;
}

function FaixaRascunho({ r }: { r: ResultadoConteudo }) {
  if (!r.is_rascunho) return null;
  return (
    <div
      role="status"
      className="mb-3 flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800"
    >
      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      <div>
        <p className="font-semibold">Rascunho de IA — revisão humana obrigatória</p>
        <p>{r.aviso_hitl || r.aviso}</p>
        {r.log_id && (
          <p className="mt-1 text-[11px] text-warn-700">
            Registro HITL: <span className="font-mono">{r.log_id}</span>
            {r.modelo ? ` · ${r.modelo}` : ""}
          </p>
        )}
      </div>
    </div>
  );
}

export default function ConteudoJuridico() {
  const [area, setArea] = useState("consumidor");
  const [faq, setFaq] = useState<ResultadoConteudo | null>(null);
  const [glos, setGlos] = useState<ResultadoConteudo | null>(null);
  const [erroFaq, setErroFaq] = useState<string | null>(null);
  const [erroGlos, setErroGlos] = useState<string | null>(null);
  const [termos, setTermos] = useState("");
  const [lf, setLf] = useState(false);
  const [lg, setLg] = useState(false);

  const gerarFaq = () => {
    setLf(true);
    setErroFaq(null);
    api
      .post("/conteudo/faq", { area, quantidade: 6 })
      .then((r) => setFaq(normalizarConteudo(r.data)))
      .catch((e) => {
        setFaq(null);
        setErroFaq(mensagemErroIA(e, "Não foi possível gerar o FAQ."));
      })
      .finally(() => setLf(false));
  };
  const gerarGlos = () => {
    setLg(true);
    setErroGlos(null);
    const lista = termos
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const body = lista.length ? { termos: lista } : { area };
    api
      .post("/conteudo/glossario", body)
      .then((r) => setGlos(normalizarConteudo(r.data)))
      .catch((e) => {
        setGlos(null);
        setErroGlos(mensagemErroIA(e, "Não foi possível gerar o glossário."));
      })
      .finally(() => setLg(false));
  };

  const faqItens = faq ? parsearFaq(faq.conteudo) : null;
  const glosItens = glos ? parsearGlossario(glos.conteudo) : null;

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="FAQ & Glossário"
        subtitle="Conteúdo jurídico para portal/equipe — rascunho IA, revisar antes de publicar"
      />

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-4">
          <h3 className="font-semibold text-ink mb-2">FAQ por área</h3>
          <div className="flex gap-2 mb-3">
            <select
              className="input text-sm flex-1"
              value={area}
              onChange={(e) => setArea(e.target.value)}
              aria-label="Área do direito"
            >
              {AREAS_OPCOES_DESTAQUE.map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.nome}
                </option>
              ))}
            </select>
            <button
              className="btn-primary text-sm"
              onClick={gerarFaq}
              disabled={lf}
            >
              {lf ? "Gerando…" : "Gerar FAQ"}
            </button>
          </div>
          {erroFaq && (
            <p role="alert" className="mb-3 text-sm text-danger-600">
              {erroFaq}
            </p>
          )}
          {faq && <FaixaRascunho r={faq} />}
          {faq &&
            (faqItens ? (
              <dl className="max-h-[28rem] space-y-3 overflow-auto rounded-lg bg-bronze-30 p-3 text-sm">
                {faqItens.map((it, i) => (
                  <div key={i}>
                    <dt className="font-semibold text-navy">{it.pergunta}</dt>
                    <dd className="text-slate-700">{it.resposta}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <pre className="text-sm whitespace-pre-wrap text-slate-700 bg-bronze-30 p-3 rounded-lg max-h-[28rem] overflow-auto">
                {faq.conteudo}
              </pre>
            ))}
        </div>

        <div className="card p-4">
          <h3 className="font-semibold text-ink mb-2">Glossário</h3>
          <input
            className="input w-full text-sm mb-2"
            placeholder="Termos separados por vírgula (vazio = usar a área)"
            value={termos}
            onChange={(e) => setTermos(e.target.value)}
          />
          <button
            className="btn-primary text-sm mb-3"
            onClick={gerarGlos}
            disabled={lg}
          >
            {lg ? "Gerando…" : "Gerar glossário"}
          </button>
          {erroGlos && (
            <p role="alert" className="mb-3 text-sm text-danger-600">
              {erroGlos}
            </p>
          )}
          {glos && <FaixaRascunho r={glos} />}
          {glos &&
            (glosItens ? (
              <dl className="max-h-[28rem] space-y-3 overflow-auto rounded-lg bg-bronze-30 p-3 text-sm">
                {glosItens.map((it, i) => (
                  <div key={i}>
                    <dt className="font-semibold text-navy">{it.termo}</dt>
                    <dd className="text-slate-700">{it.definicao}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <pre className="text-sm whitespace-pre-wrap text-slate-700 bg-bronze-30 p-3 rounded-lg max-h-[28rem] overflow-auto">
                {glos.conteudo}
              </pre>
            ))}
        </div>
      </div>
    </div>
  );
}
