// ⚠️  DEPRECATED — NÃO RODAR EM PRODUÇÃO
// Este script popula o banco com dados fictícios (skills, fontes, advogados fake, etc.)
// Para produção, use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).
// Em desenvolvimento: pode rodar para popular a base de conhecimento,
// mas NÃO deve ser incluído em deploy scripts ou CI/CD.
import { db } from "@/lib/db";
import { createHash } from "crypto";
import { readFileSync, readdirSync } from "fs";
import { join } from "path";

// ── GUARD: bloqueia execução em produção ──────────────────────────────────
if (process.env.NODE_ENV === "production") {
  console.error("❌ Este script de seed NÃO deve rodar em produção.");
  console.error("   Use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).");
  process.exit(1);
}


// Importa as 11 skills do LexValida (Markdown com frontmatter + lei seca + estrutura + erros a evitar)
// Fonte: /tmp/lexvalida/lexvalida/skills/

const SKILLS_DIR = "/tmp/lexvalida/lexvalida/skills";

function parseFrontmatter(content: string): { meta: Record<string, string>; body: string } {
  const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return { meta: {}, body: content };
  const meta: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const m = line.match(/^(\w+):\s*(.+)$/);
    if (m) {
      // Parse arrays like [a, b, c]
      if (m[2].startsWith("[")) {
        meta[m[1]] = m[2];
      } else {
        meta[m[1]] = m[2].replace(/^["']|["']$/g, "");
      }
    }
  }
  return { meta, body: match[2] };
}

async function importSkills() {
  console.log("🌱 Importando 11 skills do LexValida...\n");
  let created = 0, skipped = 0;

  const dirs = ["materia", "forma"];
  for (const dir of dirs) {
    const dirPath = join(SKILLS_DIR, dir);
    let files: string[];
    try { files = readdirSync(dirPath).filter((f) => f.endsWith(".md")); }
    catch { console.log(`  ⏭ Diretório ${dir} não encontrado`); continue; }

    for (const file of files) {
      const filePath = join(dirPath, file);
      const raw = readFileSync(filePath, "utf8");
      const { meta, body } = parseFrontmatter(raw);

      const slug = meta.slug || file.replace(".md", "");
      const content = `# ${meta.titulo || slug}\n\n## Área: ${meta.area || "civil"}\n## Tipo: ${meta.tipo || dir}\n\n${body.trim()}`;
      const contentHash = createHash("sha256").update(content, "utf8").digest("hex");

      const existing = await db.skillVersion.findFirst({
        where: { slug },
        orderBy: { version: "desc" },
      });

      if (existing && existing.contentHash === contentHash) {
        skipped++;
        console.log(`  ⏭ ${slug} (já existe, hash igual)`);
        continue;
      }

      const nextVersion = (existing?.version || 0) + 1;

      try {
        await db.skillVersion.create({
          data: {
            slug,
            version: nextVersion,
            area: meta.area || "civil",
            description: meta.descricao || meta.titulo || slug,
            content,
            triggers: JSON.stringify({ keywords: meta.gatilhos || [], tipo: meta.tipo || dir, titulo: meta.titulo || "" }),
            rules: JSON.stringify([]),
            exceptions: JSON.stringify([]),
            forbiddenClaims: JSON.stringify(["promessa_resultado", "lei_inventada", "fato_inventado"]),
            allowedTools: JSON.stringify([]),
            outputSchema: JSON.stringify({ type: "text" }),
            status: "approved",
            contentHash,
            approvedBy: "importacao-lexvalida",
            approvedAt: new Date(),
          },
        });
        created++;
        console.log(`  ✓ ${slug} v${nextVersion} → approved (${meta.area || "civil"}) — ${meta.titulo}`);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "";
        if (msg.includes("Unique constraint")) { skipped++; }
        else { console.error(`  ✗ ${slug}:`, msg); }
      }
    }
  }

  console.log(`\n✅ ${created} skills importadas, ${skipped} já existiam`);
  console.log(`📊 Total SkillVersions: ${await db.skillVersion.count()}`);
  const areas = await db.skillVersion.groupBy({ by: ["area"], _count: true, where: { status: "approved" } });
  console.log("\nSkills por área:");
  areas.forEach((a) => console.log(`  ${a.area}: ${a._count} approved`));
}

importSkills()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
