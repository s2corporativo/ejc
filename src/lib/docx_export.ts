// docx_export.ts — Geração minimalista de .docx sem dependências externas.
//
// .docx é um ZIP com arquivos XML seguindo o OOXML schema. Implementamos
// só o essencial: document.xml (parágrafos), styles.xml, content_types,
// relationships e _rels. Suporta texto, parágrafos, headings e listas.
//
// Para uso real com tabelas/imagens complexas, substituir por 'docx' ou
// 'pandoc'. Para o nosso caso (peças jurídicas em markdown → .docx) esta
// implementação cobre 95% das necessidades.

interface DocxParagraph {
  text: string;
  style?: "Title" | "Heading1" | "Heading2" | "Heading3" | "Body" | "Quote";
  bold?: boolean;
  italic?: boolean;
  align?: "left" | "center" | "right" | "both";
  listLevel?: number; // 0 = bullet, 1 = número
}

/** Converte markdown simples em parágrafos do .docx. */
export function markdownToParagraphs(md: string): DocxParagraph[] {
  const lines = md.split(/\r?\n/);
  const paras: DocxParagraph[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^#{1,6}\s+/.test(line)) {
      // Heading
      const m = line.match(/^(#{1,6})\s+(.+)$/)!;
      const level = m[1].length;
      const style = (level === 1 ? "Heading1" : level === 2 ? "Heading2" : "Heading3") as DocxParagraph["style"];
      paras.push({ text: m[2].trim(), style });
      i++;
      continue;
    }
    if (/^>\s+/.test(line)) {
      // Blockquote
      paras.push({ text: line.replace(/^>\s+/, ""), style: "Quote" });
      i++;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      // Bullet
      paras.push({ text: line.replace(/^[-*]\s+/, ""), listLevel: 0 });
      i++;
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      // Numbered list
      paras.push({ text: line.replace(/^\d+\.\s+/, ""), listLevel: 1 });
      i++;
      continue;
    }
    if (line.trim() === "") {
      // Linha em branco → parágrafo vazio
      i++;
      continue;
    }
    // Linha normal — pode ser bold/italic em **
    const { text, bold, italic } = parseInline(line);
    paras.push({ text, bold, italic });
    i++;
  }
  return paras;
}

function parseInline(line: string): { text: string; bold?: boolean; italic?: boolean } {
  // Remove **bold**, *italic*, `code` — manter simples para v1
  const text = line.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\*(.+?)\*/g, "$1").replace(/`(.+?)`/g, "$1");
  return { text };
}

/** Serializa os arquivos do .docx em um Blob. */
export async function buildDocx(markdown: string, options: {
  titulo?: string;
  autor?: string;
  oab?: string;
} = {}): Promise<Blob> {
  const paragraphs = markdownToParagraphs(markdown);

  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${options.titulo ? `<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="36"/></w:rPr><w:t xml:space="preserve">${escapeXml(options.titulo)}</w:t></w:r></w:p>` : ""}
    ${paragraphs.map(renderParagraphXml).join("\n")}
    ${options.autor ? `<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">${escapeXml(options.autor)}</w:t></w:r></w:p>` : ""}
    ${options.oab ? `<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:t xml:space="preserve">${escapeXml(options.oab)}</w:t></w:r></w:p>` : ""}
    <w:p><w:r><w:t xml:space="preserve">Documento gerado por JuridIA — RASCUNHO sujeito a revisão humana (art. 1º EOAB).</w:t></w:r></w:p>
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" w:header="708" w:footer="708" w:gutter="0"/>
      <w:jc w:val="both"/>
    </w:sectPr>
  </w:body>
</w:document>`;

  const stylesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:i/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Quote">
    <w:name w:val="Quote"/>
    <w:pPr><w:ind w:left="720"/><w:spacing w:after="120"/></w:pPr>
    <w:rPr><w:i/></w:rPr>
  </w:style>
</w:styles>`;

  const contentTypesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>`;

  const relsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>`;

  const docRelsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;

  const coreXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:title>${escapeXml(options.titulo || "Minuta Jurídica")}</dc:title>
  <dc:creator>${escapeXml(options.autor || "JuridIA")}</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">${new Date().toISOString()}</dcterms:created>
</cp:coreProperties>`;

  // Build ZIP minimalista (sem compressão — Office aceita)
  const zip = buildZip([
    { name: "[Content_Types].xml", content: contentTypesXml },
    { name: "_rels/.rels", content: relsXml },
    { name: "word/document.xml", content: documentXml },
    { name: "word/_rels/document.xml.rels", content: docRelsXml },
    { name: "word/styles.xml", content: stylesXml },
    { name: "docProps/core.xml", content: coreXml },
  ]);
  return new Blob([zip], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
}

function renderParagraphXml(p: DocxParagraph): string {
  const styleAttr = p.style ? `<w:pStyle w:val="${p.style}"/>` : "";
  const alignAttr = p.align && !p.style ? `<w:jc w:val="${p.align}"/>` : "";
  const rPr = p.bold || p.italic ? `<w:rPr>${p.bold ? "<w:b/>" : ""}${p.italic ? "<w:i/>" : ""}</w:rPr>` : "";
  const styleOpen = `<w:pPr>${styleAttr}${alignAttr}</w:pPr>`;
  return `<w:p>${styleOpen}<w:r>${rPr}<w:t xml:space="preserve">${escapeXml(p.text)}</w:t></w:r></w:p>`;
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

// ── ZIP writer (PKZIP minimalista) ──────────────────────────────────────────

interface ZipEntry {
  name: string;
  content: string;
}

function buildZip(entries: ZipEntry[]): Uint8Array {
  // Converte strings para UTF-8 bytes
  const utf8 = (s: string) => new TextEncoder().encode(s);
  const localHeaders: Uint8Array[] = [];
  const centralHeaders: Uint8Array[] = [];
  const fileData: Uint8Array[] = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = utf8(entry.name);
    const contentBytes = utf8(entry.content);
    // CRC32
    const crc = crc32(contentBytes);
    // Local file header
    const localHeader = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(localHeader.buffer);
    lv.setUint32(0, 0x04034b50, true);  // signature
    lv.setUint16(4, 20, true);           // version needed
    lv.setUint16(6, 0x0800, true);       // flag (UTF-8)
    lv.setUint16(8, 0, true);            // compression method (0 = stored)
    lv.setUint16(10, 0, true);           // mod time
    lv.setUint16(12, 0, true);           // mod date
    lv.setUint32(14, crc, true);         // CRC32
    lv.setUint32(18, contentBytes.length, true);  // compressed size
    lv.setUint32(22, contentBytes.length, true);  // uncompressed size
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);           // extra length
    localHeader.set(nameBytes, 30);
    localHeaders.push(localHeader);
    fileData.push(contentBytes);

    // Central directory header
    const central = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(central.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, 0, true);
    cv.setUint16(14, 0, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, contentBytes.length, true);
    cv.setUint32(24, contentBytes.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint16(30, 0, true);
    cv.setUint16(32, 0, true);
    cv.setUint16(34, 0, true);
    cv.setUint16(36, 0, true);
    cv.setUint32(38, 0, true);
    cv.setUint32(42, offset, true);
    central.set(nameBytes, 46);
    centralHeaders.push(central);
    offset += localHeader.length + contentBytes.length;
  }

  const centralOffset = offset;
  let centralSize = 0;
  for (const c of centralHeaders) centralSize += c.length;

  // End of central directory record
  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(4, 0, true);
  ev.setUint16(6, 0, true);
  ev.setUint16(8, entries.length, true);
  ev.setUint16(10, entries.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, centralOffset, true);
  ev.setUint16(20, 0, true);

  // Concat
  const total = offset + centralSize + 22;
  const out = new Uint8Array(total);
  let p = 0;
  for (let i = 0; i < entries.length; i++) {
    out.set(localHeaders[i], p);
    p += localHeaders[i].length;
    out.set(fileData[i], p);
    p += fileData[i].length;
  }
  for (const c of centralHeaders) {
    out.set(c, p);
    p += c.length;
  }
  out.set(eocd, p);
  return out;
}

// CRC32 table
const CRC_TABLE = new Uint32Array(256);
for (let i = 0; i < 256; i++) {
  let c = i;
  for (let j = 0; j < 8; j++) {
    c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  }
  CRC_TABLE[i] = c;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ bytes[i]) & 0xff];
  }
  return (crc ^ 0xffffffff) >>> 0;
}