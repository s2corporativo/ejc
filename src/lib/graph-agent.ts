// graph-agent.ts — Agente de grafo de inteligência jurídica (sistema + caso)
//
// Duas funções principais:
//  - buildSystemGraph(): percorre src/app/api, src/components/{app,ui}, src/lib;
//    extrai imports via regex; parse prisma/schema.prisma p/ models + relations.
//    Retorna {nodes, edges, stats}.
//  - buildCaseGraph(caseId): consulta Prisma (Case + Documents + Movements + Hearings
//    + Honorarios + Deadlines + Intimacoes via AuditEvent action=intimacao_djen);
//    monta arestas case_link/temporal/mentions.
//
// NodeTypes: api, component, lib, model, ui, page, layout, case, document,
//            movement, hearing, deadline, honorario, client, intimacao, user.
// EdgeTypes: imports, depends_on, model_relation, case_link, temporal, mentions, renders.

import fs from "node:fs";
import path from "node:path";
import { db } from "@/lib/db";

// ─────────────────────────────────── Tipos

export type NodeType =
  | "api"
  | "component"
  | "lib"
  | "model"
  | "ui"
  | "page"
  | "layout"
  | "case"
  | "document"
  | "movement"
  | "hearing"
  | "deadline"
  | "honorario"
  | "client"
  | "intimacao"
  | "user";

export type EdgeType =
  | "imports"
  | "depends_on"
  | "model_relation"
  | "case_link"
  | "temporal"
  | "mentions"
  | "renders";

export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  path?: string;
  meta?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  label?: string;
}

export interface GraphStats {
  totalNodes: number;
  totalEdges: number;
  byType: Record<string, number>;
  byEdgeType: Record<string, number>;
}

export interface GraphResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

// ─────────────────────────────────── Helpers

const SRC_ROOT = path.join(process.cwd(), "src");
const SCHEMA_PATH = path.join(process.cwd(), "prisma", "schema.prisma");

// Regex de imports (Next.js TS): `import ... from "..."` e `import "..."`
const RX_IMPORT_FROM = /from\s+["']([^"']+)["']/g;
const RX_BARE_IMPORT = /import\s+["']([^"']+)["']/g;

function readSafe(p: string): string {
  try {
    return fs.readFileSync(p, "utf-8");
  } catch {
    return "";
  }
}

function listFilesRecursive(dir: string, exts: string[], out: string[] = []): string[] {
  let entries: fs.Dirent[] = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      // pula node_modules, .next, .git
      if (["node_modules", ".next", ".git", "dist", "build"].includes(e.name)) continue;
      listFilesRecursive(full, exts, out);
    } else if (e.isFile()) {
      if (exts.some((x) => e.name.endsWith(x))) out.push(full);
    }
  }
  return out;
}

// Resolve alias "@/..." → caminho real em src/
function resolveAlias(spec: string): string | null {
  if (!spec.startsWith("@/")) return null;
  const rel = spec.slice(2);
  const candidates = [
    path.join(SRC_ROOT, rel),
    path.join(SRC_ROOT, rel + ".ts"),
    path.join(SRC_ROOT, rel + ".tsx"),
    path.join(SRC_ROOT, rel, "index.ts"),
    path.join(SRC_ROOT, rel, "index.tsx"),
  ];
  for (const c of candidates) {
    try {
      if (fs.existsSync(c) && fs.statSync(c).isFile()) return c;
    } catch {
      // ignore
    }
  }
  return null;
}

// ─────────────────────────────────── System graph

function parsePrismaModels(schema: string): { name: string; fields: { name: string; refModel?: string }[] }[] {
  const models: { name: string; fields: { name: string; refModel?: string }[] }[] = [];
  const modelRe = /model\s+(\w+)\s*\{([^}]+)\}/g;
  let mm: RegExpExecArray | null;
  while ((mm = modelRe.exec(schema)) !== null) {
    const name = mm[1];
    const body = mm[2];
    const fields: { name: string; refModel?: string }[] = [];
    const fieldRe = /^\s*(\w+)\s+\w+/gm;
    const relRe = /@relation\(fields:\s*\[([^\]]+)\],\s*references:\s*\[([^\]]+)\][^)]*\)/g;
    // primeiro extrai campos com relation
    let rm: RegExpExecArray | null;
    const relFields = new Map<string, string>();
    while ((rm = relRe.exec(body)) !== null) {
      // mapeia campos locais → referencia (não usamos aqui, mas guardamos para futuro)
      relFields.set(rm[1].trim(), rm[2].trim());
    }
    let fm: RegExpExecArray | null;
    while ((fm = fieldRe.exec(body)) !== null) {
      // pula linhas que são atributos (começam com @) ou comentários (//)
      const lineStart = fm.index;
      const lineEnd = body.indexOf("\n", lineStart);
      const line = body.slice(lineStart, lineEnd === -1 ? undefined : lineEnd);
      if (/^\s*\/\//.test(line) || /^\s*@/.test(line)) continue;
      fields.push({ name: fm[1] });
    }
    models.push({ name, fields });
  }
  return models;
}

function parsePrismaRelations(schema: string): { from: string; to: string; label: string }[] {
  const out: { from: string; to: string; label: string }[] = [];
  // detecta relações @relation com referência a outro model (a partir da presença do tipo)
  const modelRe = /model\s+(\w+)\s*\{([^}]+)\}/g;
  let mm: RegExpExecArray | null;
  while ((mm = modelRe.exec(schema)) !== null) {
    const fromModel = mm[1];
    const body = mm[2];
    // cada linha de campo que referencia outro model: `name Type? @relation(fields: [...], references: [...])`
    const relRe = /(\w+)\s+(\w+)\??\s+@relation\(\s*fields:\s*\[([^\]]+)\],\s*references:\s*\[([^\]]+)\][^)]*?\)/g;
    let rm: RegExpExecArray | null;
    while ((rm = relRe.exec(body)) !== null) {
      //推断 target model a partir do tipo do campo (rm[2])
      const targetModel = rm[2];
      out.push({ from: fromModel, to: targetModel, label: `${rm[1]}→${targetModel}` });
    }
  }
  return out;
}

function nodeId(p: string): string {
  return p.replace(/\.(t|j)sx?$/, "").replace(/\//g, ".").replace(/^\.+/, "");
}

function edgeId(s: string, t: string, type: string): string {
  return `${s}__${type}__${t}`;
}

export async function buildSystemGraph(): Promise<GraphResult> {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();

  const addNode = (n: GraphNode) => {
    if (seen.has(n.id)) return;
    seen.add(n.id);
    nodes.push(n);
  };

  const addEdge = (s: string, t: string, type: EdgeType, label?: string) => {
    const id = edgeId(s, t, type);
    if (seen.has(id)) return;
    seen.add(id);
    edges.push({ id, source: s, target: t, type, label });
  };

  // 1. src/app/api (routes) → NodeType "api"
  const apiDir = path.join(SRC_ROOT, "app", "api");
  const apiFiles = listFilesRecursive(apiDir, [".ts", ".tsx"]);
  for (const f of apiFiles) {
    if (!f.endsWith("route.ts") && !f.endsWith("route.tsx")) continue;
    const rel = path.relative(SRC_ROOT, f).replace(/\\/g, "/");
    const id = nodeId(rel);
    const label = rel.replace(/\/route\.(t|j)sx?$/, "");
    addNode({ id, type: "api", label, path: rel });
    parseImports(f, id, addEdge);
  }

  // 2. src/components/app → NodeType "component"
  const compAppDir = path.join(SRC_ROOT, "components", "app");
  const compAppFiles = listFilesRecursive(compAppDir, [".ts", ".tsx"]);
  for (const f of compAppFiles) {
    if (f.endsWith(".d.ts")) continue;
    const rel = path.relative(SRC_ROOT, f).replace(/\\/g, "/");
    const id = nodeId(rel);
    addNode({ id, type: "component", label: path.basename(f).replace(/\.(t|j)sx?$/, ""), path: rel });
    parseImports(f, id, addEdge);
  }

  // 3. src/components/ui → NodeType "ui"
  const uiDir = path.join(SRC_ROOT, "components", "ui");
  const uiFiles = listFilesRecursive(uiDir, [".ts", ".tsx"]);
  for (const f of uiFiles) {
    if (f.endsWith(".d.ts")) continue;
    const rel = path.relative(SRC_ROOT, f).replace(/\\/g, "/");
    const id = nodeId(rel);
    addNode({ id, type: "ui", label: path.basename(f).replace(/\.(t|j)sx?$/, ""), path: rel });
    parseImports(f, id, addEdge);
  }

  // 4. src/lib → NodeType "lib"
  const libDir = path.join(SRC_ROOT, "lib");
  const libFiles = listFilesRecursive(libDir, [".ts", ".tsx"]);
  for (const f of libFiles) {
    if (f.endsWith(".d.ts")) continue;
    const rel = path.relative(SRC_ROOT, f).replace(/\\/g, "/");
    const id = nodeId(rel);
    addNode({ id, type: "lib", label: path.basename(f).replace(/\.(t|j)sx?$/, ""), path: rel });
    parseImports(f, id, addEdge);
  }

  // 5. src/app layouts e pages → NodeType "layout" / "page"
  const layoutFiles = listFilesRecursive(path.join(SRC_ROOT, "app"), [".tsx", ".ts"]);
  for (const f of layoutFiles) {
    const base = path.basename(f);
    if (base !== "layout.tsx" && base !== "page.tsx") continue;
    const rel = path.relative(SRC_ROOT, f).replace(/\\/g, "/");
    const id = nodeId(rel);
    addNode({
      id,
      type: base === "layout.tsx" ? "layout" : "page",
      label: base.replace(/\.(t|j)sx?$/, ""),
      path: rel,
    });
    parseImports(f, id, addEdge);
  }

  // 6. Prisma models → NodeType "model" + arestas model_relation
  const schemaText = readSafe(SCHEMA_PATH);
  if (schemaText) {
    const models = parsePrismaModels(schemaText);
    for (const m of models) {
      addNode({ id: `prisma.${m.name}`, type: "model", label: m.name, meta: { fields: m.fields.map((f) => f.name) } });
    }
    const rels = parsePrismaRelations(schemaText);
    for (const r of rels) {
      addEdge(`prisma.${r.from}`, `prisma.${r.to}`, "model_relation", r.label);
    }
  }

  // stats
  const byType: Record<string, number> = {};
  for (const n of nodes) byType[n.type] = (byType[n.type] || 0) + 1;
  const byEdgeType: Record<string, number> = {};
  for (const e of edges) byEdgeType[e.type] = (byEdgeType[e.type] || 0) + 1;

  return {
    nodes,
    edges,
    stats: { totalNodes: nodes.length, totalEdges: edges.length, byType, byEdgeType },
  };
}

function parseImports(filePath: string, sourceId: string, addEdge: (s: string, t: string, type: EdgeType, label?: string) => void) {
  const content = readSafe(filePath);
  if (!content) return;
  const specs = new Set<string>();
  let m: RegExpExecArray | null;
  const reFrom = new RegExp(RX_IMPORT_FROM.source, RX_IMPORT_FROM.flags);
  while ((m = reFrom.exec(content)) !== null) specs.add(m[1]);
  const reBare = new RegExp(RX_BARE_IMPORT.source, RX_BARE_IMPORT.flags);
  while ((m = reBare.exec(content)) !== null) specs.add(m[1]);
  for (const spec of specs) {
    const resolved = resolveAlias(spec);
    if (resolved) {
      const rel = path.relative(SRC_ROOT, resolved).replace(/\\/g, "/");
      const targetId = nodeId(rel);
      addEdge(sourceId, targetId, "imports", spec);
    } else if (/^\.\.?\/?/.test(spec)) {
      // import relativo
      const baseDir = path.dirname(filePath);
      const resolvedRel = path.resolve(baseDir, spec);
      // tenta extesões
      const candidates = [resolvedRel, resolvedRel + ".ts", resolvedRel + ".tsx", path.join(resolvedRel, "index.ts"), path.join(resolvedRel, "index.tsx")];
      for (const c of candidates) {
        try {
          if (fs.existsSync(c) && fs.statSync(c).isFile()) {
            const rel = path.relative(SRC_ROOT, c).replace(/\\/g, "/");
            addEdge(sourceId, nodeId(rel), "imports", spec);
            break;
          }
        } catch {
          // ignore
        }
      }
    }
    // packages externos: depend_on (sem criar nó de destino)
    if (!spec.startsWith("@/") && !spec.startsWith(".") && !spec.startsWith("..")) {
      const externalId = `pkg.${spec.split("/")[0]}`;
      addEdge(sourceId, externalId, "depends_on", spec);
    }
  }
}

// ─────────────────────────────────── Case graph

interface CaseGraphNode {
  id: string;
  type: NodeType;
  label: string;
  meta?: Record<string, unknown>;
}

export async function buildCaseGraph(caseId: string): Promise<GraphResult> {
  const nodes: CaseGraphNode[] = [];
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();

  const addNode = (n: CaseGraphNode) => {
    if (seen.has(n.id)) return;
    seen.add(n.id);
    nodes.push(n);
  };
  const addEdge = (s: string, t: string, type: EdgeType, label?: string) => {
    const id = edgeId(s, t, type);
    if (seen.has(id)) return;
    seen.add(id);
    edges.push({ id, source: s, target: t, type, label });
  };

  // Carrega o caso e relações
  const c = await db.case.findUnique({
    where: { id: caseId },
    include: {
      documents: true,
      movimentos: true,
      audiencias: true,
      client: true,
    },
  });
  if (!c) {
    return { nodes: [], edges: [], stats: { totalNodes: 0, totalEdges: 0, byType: {}, byEdgeType: {} } };
  }

  // Deadlines (CaseDeadline)
  const deadlines = await db.caseDeadline.findMany({ where: { caseId } });
  // Honorarios: schema não tem Honorario como tabela — usamos AuditEvent action=honorario_* se existir
  // (mantemos flexível: se a tabela não existir, ignoramos).
  let honorarios: { id: string; action: string; resourceId: string | null; metadata: string; createdAt: Date }[] = [];
  try {
    honorarios = await db.auditEvent.findMany({
      where: { OR: [{ action: "honorario_create" }, { action: "honorario_update" }] },
    });
  } catch {
    honorarios = [];
  }
  // Intimacoes: parseia AuditEvent action=intimacao_djen
  let intimacoes: { id: string; action: string; resourceId: string | null; metadata: string; createdAt: Date }[] = [];
  try {
    intimacoes = await db.auditEvent.findMany({ where: { action: "intimacao_djen" } });
  } catch {
    intimacoes = [];
  }
  // User responsável (se houver oabEstado+oabNumero)
  let userNode: { id: string; type: NodeType; label: string; meta?: Record<string, unknown> } | null = null;
  if (c.responsavel) {
    // tenta achar User por name
    const u = await db.user.findFirst({ where: { name: { contains: c.responsavel } } });
    if (u) {
      userNode = { id: `user.${u.id}`, type: "user", label: u.name || u.email, meta: { plan: u.plan, oabEstado: u.oabEstado, oabNumero: u.oabNumero } };
      addNode(userNode);
      addEdge(`case.${c.id}`, userNode.id, "case_link", "responsavel");
    }
  }

  // Case node
  addNode({
    id: `case.${c.id}`,
    type: "case",
    label: c.title,
    meta: { area: c.area, status: c.status, valor: c.valor, number: c.number },
  });

  // Client
  if (c.client) {
    addNode({ id: `client.${c.client.id}`, type: "client", label: c.client.name, meta: { email: c.client.email, document: c.client.document } });
    addEdge(`case.${c.id}`, `client.${c.client.id}`, "case_link", "client");
  }

  // Documents
  for (const d of c.documents) {
    addNode({ id: `doc.${d.id}`, type: "document", label: d.title, meta: { templateSlug: d.templateSlug, status: d.status, createdAt: d.createdAt.toISOString() } });
    addEdge(`case.${c.id}`, `doc.${d.id}`, "case_link", "document");
  }

  // Movements (com timeline temporal entre eles)
  const movsSorted = [...c.movimentos].sort((a, b) => a.data.getTime() - b.data.getTime());
  movsSorted.forEach((m, i) => {
    addNode({
      id: `mov.${m.id}`,
      type: "movement",
      label: m.descricao.slice(0, 60),
      meta: { tipo: m.tipo, data: m.data.toISOString(), numeroProc: m.numeroProc },
    });
    addEdge(`case.${c.id}`, `mov.${m.id}`, "case_link", "movement");
    // encadeia temporal
    if (i > 0) {
      addEdge(`mov.${movsSorted[i - 1].id}`, `mov.${m.id}`, "temporal", "next");
    }
  });

  // Hearings
  for (const h of c.audiencias) {
    addNode({
      id: `hear.${h.id}`,
      type: "hearing",
      label: `${h.tipo} ${h.data.toISOString().slice(0, 10)}`,
      meta: { tipo: h.tipo, data: h.data.toISOString(), status: h.status, local: h.local, orgao: h.orgao },
    });
    addEdge(`case.${c.id}`, `hear.${h.id}`, "case_link", "hearing");
    // menciona em movimentos do mesmo dia (mentions)
    const sameDayMov = movsSorted.find((m) => m.data.toISOString().slice(0, 10) === h.data.toISOString().slice(0, 10));
    if (sameDayMov) addEdge(`mov.${sameDayMov.id}`, `hear.${h.id}`, "mentions", "same-day");
  }

  // Deadlines
  for (const d of deadlines) {
    addNode({
      id: `deadline.${d.id}`,
      type: "deadline",
      label: d.descricao.slice(0, 60),
      meta: { tipo: d.tipo, vencimento: d.vencimento.toISOString(), prazoDias: d.prazoDias, tipoContagem: d.tipoContagem },
    });
    addEdge(`case.${c.id}`, `deadline.${d.id}`, "case_link", "deadline");
    // menciona audiências próximas (5 dias)
    const near = c.audiencias.find((h) => Math.abs(h.data.getTime() - d.vencimento.getTime()) < 5 * 86400000);
    if (near) addEdge(`deadline.${d.id}`, `hear.${near.id}`, "temporal", "near");
  }

  // Honorarios (via AuditEvent)
  for (const h of honorarios) {
    const meta = safeParse(h.metadata);
    addNode({ id: `honor.${h.id}`, type: "honorario", label: String(meta.descricao || "Honorário"), meta: { ...meta, createdAt: h.createdAt.toISOString() } });
    addEdge(`case.${c.id}`, `honor.${h.id}`, "case_link", "honorario");
  }

  // Intimacoes (via AuditEvent)
  for (const it of intimacoes) {
    const meta = safeParse(it.metadata);
    addNode({ id: `intim.${it.id}`, type: "intimacao", label: String(meta.conteudo || "Intimação DJEN").slice(0, 60), meta: { ...meta, createdAt: it.createdAt.toISOString() } });
    addEdge(`case.${c.id}`, `intim.${it.id}`, "case_link", "intimacao");
    // menciona CNJ do caso se case.number estiver no conteúdo
    if (c.number && String(meta.conteudo || "").includes(c.number)) {
      addEdge(`intim.${it.id}`, `case.${c.id}`, "mentions", "cnj");
    }
  }

  const byType: Record<string, number> = {};
  for (const n of nodes) byType[n.type] = (byType[n.type] || 0) + 1;
  const byEdgeType: Record<string, number> = {};
  for (const e of edges) byEdgeType[e.type] = (byEdgeType[e.type] || 0) + 1;

  return {
    nodes,
    edges,
    stats: { totalNodes: nodes.length, totalEdges: edges.length, byType, byEdgeType },
  };
}

function safeParse(raw: string): Record<string, unknown> {
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}
