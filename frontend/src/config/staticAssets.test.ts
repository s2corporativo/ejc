import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const FRONTEND_DIR = join(dirname(fileURLToPath(import.meta.url)), "../..");
const robots = readFileSync(join(FRONTEND_DIR, "public/robots.txt"), "utf-8");
const nginx = readFileSync(join(FRONTEND_DIR, "nginx.conf"), "utf-8");

describe("política de indexação do frontend", () => {
  it("bloqueia explicitamente a indexação do SPA autenticado", () => {
    expect(robots.trim().split(/\r?\n/)).toEqual([
      "User-agent: *",
      "Disallow: /",
    ]);
  });

  it("serve robots.txt como texto sem cair no fallback da SPA", () => {
    const location = nginx.match(
      /location = \/robots\.txt\s*\{(?<body>[\s\S]*?)\n    \}/,
    );

    expect(location?.groups?.body).toContain("try_files /robots.txt =404;");
    expect(location?.groups?.body).toContain("default_type text/plain;");
    expect(location?.groups?.body).not.toContain("/index.html");
  });
});
