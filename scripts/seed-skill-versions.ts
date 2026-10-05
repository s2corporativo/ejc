// ⚠️  DEPRECATED — NÃO RODAR EM PRODUÇÃO
// Este script popula o banco com dados fictícios (skills, fontes, advogados fake, etc.)
// Para produção, use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).
// Em desenvolvimento: pode rodar para popular a base de conhecimento,
// mas NÃO deve ser incluído em deploy scripts ou CI/CD.
import { db } from "@/lib/db";
import { createHash } from "crypto";

// ── GUARD: bloqueia execução em produção ──────────────────────────────────
if (process.env.NODE_ENV === "production") {
  console.error("❌ Este script de seed NÃO deve rodar em produção.");
  console.error("   Use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).");
  process.exit(1);
}


async function seedSkillVersions() {
  console.log("🌱 Migrando skills para SkillVersion...");

  // Carrega skills existentes do modelo Skill (estático)
  const skills = await db.skill.findMany();

  let created = 0;
  let skipped = 0;

  for (const s of skills) {
    const contentHash = createHash("sha256").update(s.content, "utf8").digest("hex");

    // Verifica se já existe uma SkillVersion para este slug
    const existing = await db.skillVersion.findFirst({
      where: { slug: s.slug },
      orderBy: { version: "desc" },
    });

    if (existing && existing.contentHash === contentHash) {
      skipped++;
      continue;
    }

    const nextVersion = (existing?.version || 0) + 1;

    try {
      await db.skillVersion.create({
        data: {
          slug: s.slug,
          version: nextVersion,
          area: s.category,
          description: s.description,
          content: s.content,
          triggers: JSON.stringify({ keywords: [s.category] }),
          rules: JSON.stringify([]),
          exceptions: JSON.stringify([]),
          forbiddenClaims: JSON.stringify(["promessa_resultado", "lei_inventada"]),
          allowedTools: JSON.stringify([]),
          outputSchema: JSON.stringify({ type: "text" }),
          status: "approved", // migra como approved (já estavam em uso)
          contentHash,
          approvedBy: "migration",
          approvedAt: new Date(),
        },
      });
      created++;
      console.log(`  ✓ ${s.slug} v${nextVersion} → approved`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("Unique constraint")) {
        skipped++;
      } else {
        console.error(`  ✗ ${s.slug}:`, msg);
      }
    }
  }

  console.log(`\n✅ ${created} SkillVersions criadas (approved), ${skipped} já existiam`);
  console.log(`📊 Total: ${await db.skillVersion.count()}`);
}

seedSkillVersions()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
