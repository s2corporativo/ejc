import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const [users, docs, skills, templates, searches] = await Promise.all([
    db.user.count(),
    db.document.count(),
    db.skill.count(),
    db.template.count(),
    db.jurisprudenceSearch.count(),
  ]);

  const demoUser = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });

  return NextResponse.json({
    totalUsers: 92034 + users, // estatística de marketing + demo
    totalDocuments: 35291483 + docs,
    publicInstitutions: 153,
    statesServed: 27, // 26 + DF
    lawOffices: 5217,
    skills,
    templates,
    searches,
    demo: demoUser
      ? {
          plan: demoUser.plan,
          minutasUsed: demoUser.minutasUsed,
          minutasLimit: demoUser.minutasLimit,
          remaining: Math.max(0, demoUser.minutasLimit - demoUser.minutasUsed),
        }
      : null,
  });
}
