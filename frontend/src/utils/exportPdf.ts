/**
 * Export PDF via impressao do browser, sem dependencia externa.
 * Usa padrao Visual Law EJC para relatorios tabulares e escapa HTML dinamico.
 */
function escapeHtml(value: string | number | null | undefined) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function exportPdf(
  title: string,
  headers: string[],
  rows: (string | number | null | undefined)[][],
  filename = "export.pdf",
) {
  const safeTitle = escapeHtml(title);
  const exportedAt = escapeHtml(
    new Date().toLocaleDateString("pt-BR", { dateStyle: "full" }),
  );
  const tableRows = rows
    .map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`)
    .join("");
  const safeHeaders = headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("");

  const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>${safeTitle}</title>
  <style>
    @page { margin: 1.6cm 1.35cm; }
    body {
      font-family: Inter, 'Segoe UI', Arial, sans-serif;
      font-size: 11px;
      color: #111827;
      padding: 0;
      background: #fff;
    }
    .letterhead {
      border-bottom: 3px solid #0f172a;
      padding-bottom: 10px;
      margin-bottom: 14px;
    }
    .brand { font-size: 17px; font-weight: 800; color: #111827; }
    .sub { font-size: 10px; color: #6b7280; margin-top: 3px; }
    .cover {
      border: 1px solid #dbe3ef;
      border-radius: 10px;
      background: #f8fafc;
      padding: 14px;
      margin-bottom: 14px;
    }
    .kicker {
      color: #F4574D;
      font-size: 9px;
      font-weight: 800;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    h1 { font-size: 18px; color: #111827; margin: 0; line-height: 1.25; }
    .review {
      border: 1px solid #c7d2fe;
      border-left: 4px solid #F4574D;
      background: #eef2ff;
      color: #3730a3;
      padding: 8px 10px;
      border-radius: 8px;
      margin-bottom: 12px;
      font-size: 10px;
    }
    table { width: 100%; border-collapse: collapse; page-break-inside: auto; }
    th {
      background: #0f172a;
      color: #fff;
      padding: 7px 8px;
      text-align: left;
      font-size: 9px;
      text-transform: uppercase;
      font-weight: 800;
    }
    td { padding: 6px 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
    tr:nth-child(even) td { background: #f8fafc; }
    .footer { margin-top: 18px; border-top: 1px solid #e5e7eb; padding-top: 8px; color: #6b7280; font-size: 9px; }
  </style>
</head>
<body>
  <div class="letterhead">
    <div class="brand">De Paula Teixeira Advogados Associados</div>
    <div class="sub">Sistema EJC | Relatorio gerado em ${exportedAt}</div>
  </div>
  <section class="cover">
    <div class="kicker">Relatorio | Padrao Visual Law EJC</div>
    <h1>${safeTitle}</h1>
  </section>
  <div class="review">Documento gerado automaticamente. Conferir dados antes de envio externo, protocolo ou tomada de decisao.</div>
  <table>
    <thead><tr>${safeHeaders}</tr></thead>
    <tbody>${tableRows || '<tr><td colspan="99">Nenhum registro encontrado.</td></tr>'}</tbody>
  </table>
  <div class="footer">Uso interno - confidencial. Nome sugerido: ${escapeHtml(filename)}</div>
</body>
</html>`;

  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(html);
  w.document.close();
  w.focus();
  setTimeout(() => {
    w.print();
  }, 300);
}
