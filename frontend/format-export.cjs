const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const target = "src/components/__tests__/CaseContextBar.test.tsx";
const prettierBin = path.join(
  process.cwd(),
  "node_modules",
  "prettier",
  "bin",
  "prettier.cjs",
);

execFileSync(process.execPath, [prettierBin, "--write", target], {
  stdio: "inherit",
});

console.log("__FORMATTED_BEGIN__");
console.log(fs.readFileSync(target).toString("base64"));
console.log("__FORMATTED_END__");

execFileSync(
  process.execPath,
  [prettierBin, "--check", "src/**/*.{ts,tsx,css}"],
  { stdio: "inherit" },
);
