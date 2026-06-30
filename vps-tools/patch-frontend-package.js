const fs = require("fs");
const pkgPath = "/app/package.json";
const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
pkg.scripts = {
  ...pkg.scripts,
  lint: "tsc --noEmit",
  format: 'prettier --write "src/**/*.{ts,tsx,css}"',
  "format:check": 'prettier --check "src/**/*.{ts,tsx,css}"',
};
fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n");
