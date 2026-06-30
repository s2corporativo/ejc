import React from "react";

// Renderizador de Markdown leve e SEGURO para respostas de IA do EJC.
// Constrói elementos React (NÃO usa dangerouslySetInnerHTML → imune a XSS).
// Cobre: títulos (#..######), negrito (**/__), itálico (*/_), negrito-itálico
// (***), código inline (`), listas (- * + e 1.), citações (>), réguas (---),
// e links seguros ([texto](url)). NÃO remove asteriscos isolados (preserva
// operadores de cálculo/itens técnicos): só converte marcações bem-formadas.

// Os pares exigem caractere NÃO-espaço logo após a abertura e antes do
// fechamento (markdown válido). Isso evita casar operadores de cálculo como
// "R$ 1.500 * 12 * 4" (que têm espaço junto ao asterisco) — preserva o texto.
const INLINE_RE =
  /`([^`]+)`|\*\*\*(\S|\S[^*]*?\S)\*\*\*|\*\*(\S|\S[^*]*?\S)\*\*|__(\S|\S[^_]*?\S)__|\*(\S|\S[^*\n]*?\S)\*|(?<![A-Za-z0-9])_(\S|\S[^_\n]*?\S)_(?![A-Za-z0-9])|\[([^\]]+)\]\(([^)\s]+)\)/g;

function hrefSeguro(url: string): string | null {
  const u = url.trim();
  if (/^(https?:\/\/|mailto:|\/)/i.test(u)) return u;
  return null; // bloqueia javascript:, data:, etc.
}

function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const key = `${keyBase}-${i++}`;
    if (m[1] !== undefined) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] text-slate-800"
        >
          {m[1]}
        </code>
      );
    } else if (m[2] !== undefined) {
      nodes.push(
        <strong key={key} className="font-semibold text-slate-900">
          <em>{m[2]}</em>
        </strong>
      );
    } else if (m[3] !== undefined || m[4] !== undefined) {
      nodes.push(
        <strong key={key} className="font-semibold text-slate-900">
          {m[3] ?? m[4]}
        </strong>
      );
    } else if (m[5] !== undefined || m[6] !== undefined) {
      nodes.push(<em key={key}>{m[5] ?? m[6]}</em>);
    } else if (m[7] !== undefined) {
      const href = hrefSeguro(m[8] || "");
      nodes.push(
        href ? (
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-bronze-700 underline underline-offset-2 hover:text-bronze-800"
          >
            {m[7]}
          </a>
        ) : (
          m[7]
        )
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function Markdown({
  source,
  className = "",
}: {
  source?: string | null;
  className?: string;
}) {
  if (!source) return null;
  const lines = String(source).replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];
  let listOrdered = false;
  let inList = false;
  let para: string[] = [];
  let quote: string[] = [];
  let k = 0;

  const flushPara = () => {
    if (para.length) {
      blocks.push(
        <p key={"p" + k} className="mb-2 leading-relaxed">
          {renderInline(para.join(" "), "p" + k)}
        </p>
      );
      k++;
      para = [];
    }
  };
  const flushQuote = () => {
    if (quote.length) {
      blocks.push(
        <blockquote
          key={"q" + k}
          className="mb-2 border-l-2 border-bronze-300 bg-slate-50 px-3 py-1 italic text-slate-600"
        >
          {renderInline(quote.join(" "), "q" + k)}
        </blockquote>
      );
      k++;
      quote = [];
    }
  };
  const flushList = () => {
    if (inList) {
      const items = listItems.map((it, idx) => (
        <li key={idx}>{renderInline(it, "li" + k + "-" + idx)}</li>
      ));
      blocks.push(
        listOrdered ? (
          <ol key={"l" + k} className="mb-2 list-decimal space-y-1 pl-5">
            {items}
          </ol>
        ) : (
          <ul key={"l" + k} className="mb-2 list-disc space-y-1 pl-5">
            {items}
          </ul>
        )
      );
      k++;
      listItems = [];
      inList = false;
    }
  };
  const flushAll = () => {
    flushPara();
    flushQuote();
    flushList();
  };

  for (const raw of lines) {
    const t = raw.trim();
    if (!t) {
      flushAll();
      continue;
    }
    // Régua horizontal (---, ***, ___)
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) {
      flushAll();
      blocks.push(<hr key={"hr" + k++} className="my-3 border-slate-200" />);
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(t);
    const q = /^>\s?(.*)$/.exec(t);
    const ul = /^[-*+]\s+(.*)$/.exec(t);
    const ol = /^\d+[.)]\s+(.*)$/.exec(t);
    if (h) {
      flushAll();
      const lvl = h[1].length;
      const cls =
        lvl <= 1
          ? "mb-1 mt-3 text-base font-bold text-slate-900"
          : lvl === 2
          ? "mb-1 mt-3 text-sm font-semibold text-slate-900"
          : "mb-1 mt-2 text-sm font-medium text-slate-800";
      blocks.push(
        <div key={"h" + k} className={cls}>
          {renderInline(h[2], "h" + k)}
        </div>
      );
      k++;
    } else if (q) {
      flushPara();
      flushList();
      quote.push(q[1]);
    } else if (ul) {
      flushPara();
      flushQuote();
      if (inList && listOrdered) flushList();
      inList = true;
      listOrdered = false;
      listItems.push(ul[1]);
    } else if (ol) {
      flushPara();
      flushQuote();
      if (inList && !listOrdered) flushList();
      inList = true;
      listOrdered = true;
      listItems.push(ol[1]);
    } else {
      flushQuote();
      flushList();
      para.push(t);
    }
  }
  flushAll();
  return <div className={className}>{blocks}</div>;
}

export default Markdown;
