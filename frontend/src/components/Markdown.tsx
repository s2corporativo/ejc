import React from "react";

// Renderizador de Markdown leve e SEGURO para respostas de IA do EJC.
// Sem dependencia externa e sem dangerouslySetInnerHTML: constroi elementos
// React (nao injeta HTML). Cobre titulos, negrito, italico, listas e
// paragrafos, preservando o conteudo.

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const regex = /\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\n]+)\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const bold = m[1] || m[2];
    if (bold) {
      nodes.push(
        <strong key={i} className="font-semibold text-slate-900">
          {bold}
        </strong>
      );
    } else {
      nodes.push(<em key={i}>{m[3]}</em>);
    }
    last = m.index + m[0].length;
    i++;
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
  let k = 0;

  const flushPara = () => {
    if (para.length) {
      blocks.push(
        <p key={"p" + k++} className="mb-2 leading-relaxed">
          {renderInline(para.join(" "))}
        </p>
      );
      para = [];
    }
  };
  const flushList = () => {
    if (inList) {
      const items = listItems.map((it, idx) => <li key={idx}>{renderInline(it)}</li>);
      blocks.push(
        listOrdered ? (
          <ol key={"l" + k++} className="mb-2 list-decimal space-y-1 pl-5">
            {items}
          </ol>
        ) : (
          <ul key={"l" + k++} className="mb-2 list-disc space-y-1 pl-5">
            {items}
          </ul>
        )
      );
      listItems = [];
      inList = false;
    }
  };

  for (const raw of lines) {
    const t = raw.trim();
    if (!t) {
      flushPara();
      flushList();
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(t);
    const ul = /^[-*+]\s+(.*)$/.exec(t);
    const ol = /^\d+[.)]\s+(.*)$/.exec(t);
    if (h) {
      flushPara();
      flushList();
      const lvl = h[1].length;
      const cls =
        lvl <= 1
          ? "mb-1 mt-3 text-base font-semibold text-slate-900"
          : lvl === 2
          ? "mb-1 mt-3 text-sm font-semibold text-slate-900"
          : "mb-1 mt-2 text-sm font-medium text-slate-800";
      blocks.push(
        <div key={"h" + k++} className={cls}>
          {renderInline(h[2])}
        </div>
      );
    } else if (ul) {
      flushPara();
      if (inList && listOrdered) flushList();
      inList = true;
      listOrdered = false;
      listItems.push(ul[1]);
    } else if (ol) {
      flushPara();
      if (inList && !listOrdered) flushList();
      inList = true;
      listOrdered = true;
      listItems.push(ol[1]);
    } else {
      flushList();
      para.push(t);
    }
  }
  flushPara();
  flushList();
  return <div className={className}>{blocks}</div>;
}

export default Markdown;
