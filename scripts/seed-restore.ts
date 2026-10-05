// ⚠️  DEPRECATED — NÃO RODAR EM PRODUÇÃO
// Este script popula o banco com dados fictícios (skills, fontes, advogados fake, etc.)
// Para produção, use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).
// Em desenvolvimento: pode rodar para popular a base de conhecimento,
// mas NÃO deve ser incluído em deploy scripts ou CI/CD.
// Backfill OAB numbers + advogados + test cases after schema reset.
// Run with: bun run scripts/seed-restore.ts

import { PrismaClient } from "@prisma/client";

// ── GUARD: bloqueia execução em produção ──────────────────────────────────
if (process.env.NODE_ENV === "production") {
  console.error("❌ Este script de seed NÃO deve rodar em produção.");
  console.error("   Use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).");
  process.exit(1);
}


const db = new PrismaClient();

const ADVOGADOS = [
  { email: "demo@juridia.com.br",        name: "Advogado Demo",  oabNumero: "287451", oabEstado: "SP", plan: "individual_2", minutasUsed: 51, minutasLimit: 200 },
  { email: "maria.silva@juridia.com.br", name: "Maria Silva",   oabNumero: "312058", oabEstado: "RJ", plan: "individual_2", minutasUsed: 47, minutasLimit: 100 },
  { email: "carlos.lima@juridia.com.br", name: "Carlos Lima",   oabNumero: "189234", oabEstado: "MG", plan: "individual_3", minutasUsed: 34, minutasLimit: 200 },
  { email: "joao.pereira@juridia.com.br",name: "João Pereira",  oabNumero: "415789", oabEstado: "SP", plan: "individual_1", minutasUsed: 33, minutasLimit: 100 },
  { email: "ana.santos@juridia.com.br",  name: "Ana Santos",    oabNumero: "256743", oabEstado: "PR", plan: "enterprise",   minutasUsed: 29, minutasLimit: 1000 },
  { email: "pedro.mendes@juridia.com.br",name: "Pedro Mendes",  oabNumero: "345678", oabEstado: "RS", plan: "individual_2", minutasUsed: 0,  minutasLimit: 100 },
  { email: "beatriz@juridia.com.br",     name: "Dra. Beatriz C",oabNumero: "478231", oabEstado: "BA", plan: "individual_1", minutasUsed: 0,  minutasLimit: 50 },
];

async function seedRestore() {
  console.log("🔧 Restaurando advogados com OAB...");
  for (const adv of ADVOGADOS) {
    const existing = await db.user.findUnique({ where: { email: adv.email } });
    if (existing) {
      // Update — adiciona oabNumero/oabEstado ao user existente
      await db.user.update({
        where: { id: existing.id },
        data: { oabNumero: adv.oabNumero, oabEstado: adv.oabEstado, name: adv.name, plan: adv.plan, minutasUsed: adv.minutasUsed, minutasLimit: adv.minutasLimit },
      });
      console.log(`  ✓ Updated: ${adv.name} → OAB/${adv.oabEstado} ${adv.oabNumero}`);
    } else {
      await db.user.create({ data: adv });
      console.log(`  ✓ Created: ${adv.name} → OAB/${adv.oabEstado} ${adv.oabNumero}`);
    }
  }

  // Verifica resultado
  const total = await db.user.count();
  const comOAB = await db.user.count({ where: { oabNumero: { not: null } } });
  console.log(`\n📊 Total de usuários: ${total}`);
  console.log(`📊 Com OAB: ${comOAB}`);
  console.log("✅ Restore concluído");
}

seedRestore()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
