/**
 * Utilitário de exportação CSV no browser.
 * Uso: exportCsv(rows, "casos_2026.csv")
 *
 * Segurança: neutraliza Formula Injection em células textuais antes de gerar
 * o arquivo (Excel/LibreOffice interpretam =, +, - e @ como fórmulas).
 */
const FORMULA_PREFIX = /^[\t\r\n ]*[=+\-@]/;

export function sanitizeCsvCell(v: unknown): string {
  let s = v == null ? "" : String(v);
  if (typeof v === "string" && FORMULA_PREFIX.test(v)) {
    s = `'${s}`;
  }
  return s.includes(",") || s.includes('"') || s.includes("\n") || s.includes("\r")
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

export function exportCsv(
  rows: Record<string, unknown>[],
  filename = "export.csv",
) {
  if (!rows.length) return;

  const headers = Object.keys(rows[0]);
  const lines = [
    headers.map((h) => sanitizeCsvCell(h)).join(","),
    ...rows.map((r) => headers.map((h) => sanitizeCsvCell(r[h])).join(",")),
  ];

  const blob = new Blob(["﻿" + lines.join("\r\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
