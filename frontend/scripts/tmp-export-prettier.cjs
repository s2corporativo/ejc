const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const targets = [
  "src/components/visual/LinhaDoTempoProcessual.tsx",
  "src/types/visualLaw.ts",
];
const prettierBin = path.join(
  process.cwd(),
  "node_modules",
  "prettier",
  "bin",
  "prettier.cjs",
);

execFileSync(process.execPath, [prettierBin, "--write", ...targets], {
  stdio: "inherit",
});

for (const target of targets) {
  const marker = target.includes("LinhaDoTempoProcessual")
    ? "TIMELINE"
    : "VISUAL_LAW";
  console.log(`__FORMATTED_${marker}_BEGIN__`);
  console.log(fs.readFileSync(target).toString("base64"));
  console.log(`__FORMATTED_${marker}_END__`);
}

execFileSync(
  process.execPath,
  [prettierBin, "--check", "src/**/*.{ts,tsx,css}"],
  { stdio: "inherit" },
);
