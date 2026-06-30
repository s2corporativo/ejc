/**
 * vps-tools/ssh-config.js
 * Carrega as credenciais de acesso à VPS a partir de variáveis de ambiente.
 *
 * NUNCA versione credenciais reais. Defina-as de uma destas formas:
 *   1) Arquivo local vps-tools/.env (ignorado pelo .gitignore) — ver .env.example
 *   2) Variáveis de ambiente: VPS_HOST, VPS_USER, VPS_PASSWORD, VPS_PORT
 *
 * Este módulo apenas LÊ configuração; não adiciona funcionalidade nova.
 */
const fs = require('fs');
const path = require('path');

// Carregador mínimo de .env local (sem dependência externa).
(function loadLocalEnv() {
  const envPath = path.join(__dirname, '.env');
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!m || line.trim().startsWith('#')) continue;
    const key = m[1];
    let val = m[2].trim();
    if ((val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = val;
  }
})();

const host = process.env.VPS_HOST;
const username = process.env.VPS_USER || 'root';
const password = process.env.VPS_PASSWORD;
const port = Number(process.env.VPS_PORT || 22);

const missing = [];
if (!host) missing.push('VPS_HOST');
if (!password) missing.push('VPS_PASSWORD');
if (missing.length) {
  console.error(
    `[vps-tools] Credenciais ausentes: ${missing.join(', ')}.\n` +
    `Configure vps-tools/.env (veja vps-tools/.env.example) ou exporte as variáveis de ambiente.`
  );
  process.exit(1);
}

module.exports = { host, port, username, password, readyTimeout: 30000 };
