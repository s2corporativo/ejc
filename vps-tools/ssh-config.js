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
const os = require('os');
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

// Chave SSH (opcional, preferida quando presente). Aceita o caminho de um
// arquivo de chave — VPS_SSH_KEY_PATH — ou a chave literal em VPS_SSH_KEY.
// Depender só de senha deixa o acesso com ponto único de falha: se ela for
// trocada ou perdida, não sobra caminho de entrada.
function carregarChave() {
  const caminho = process.env.VPS_SSH_KEY_PATH;
  if (caminho) {
    const resolvido = caminho.startsWith('~')
      ? path.join(os.homedir(), caminho.slice(1))
      : caminho;
    if (!fs.existsSync(resolvido)) {
      console.error(`[vps-tools] VPS_SSH_KEY_PATH aponta para arquivo inexistente: ${resolvido}`);
      process.exit(1);
    }
    return fs.readFileSync(resolvido, 'utf8');
  }
  return process.env.VPS_SSH_KEY || undefined;
}

const privateKey = carregarChave();
const passphrase = process.env.VPS_SSH_PASSPHRASE || undefined;

const missing = [];
if (!host) missing.push('VPS_HOST');
if (!password && !privateKey) missing.push('VPS_PASSWORD (ou VPS_SSH_KEY_PATH/VPS_SSH_KEY)');
if (missing.length) {
  console.error(
    `[vps-tools] Credenciais ausentes: ${missing.join(', ')}.\n` +
    `Configure vps-tools/.env (veja vps-tools/.env.example) ou exporte as variáveis de ambiente.`
  );
  process.exit(1);
}

// `password` segue presente quando definida: o ssh2 tenta a chave primeiro e
// cai para senha se o servidor recusar, preservando o comportamento anterior.
const config = { host, port, username, readyTimeout: 30000 };
if (privateKey) config.privateKey = privateKey;
if (passphrase) config.passphrase = passphrase;
if (password) config.password = password;

module.exports = config;
