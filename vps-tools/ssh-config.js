/**
 * vps-tools/ssh-config.js
 * Carrega a configuração de acesso SSH/SFTP à VPS a partir de variáveis de
 * ambiente. Nunca versiona nem imprime credenciais.
 *
 * Formas suportadas:
 *   1) Arquivo local vps-tools/.env (ignorado pelo .gitignore) — ver .env.example
 *   2) Variáveis de ambiente.
 *
 * Autenticação por chave é preferida. Senha permanece como fallback somente
 * para hosts que ainda a aceitem; o host de produção atual está endurecido
 * para autenticação por chave.
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
const password = process.env.VPS_PASSWORD || undefined;
const port = Number(process.env.VPS_PORT || 22);

function carregarChavePrivada() {
  const caminhoInformado = process.env.VPS_SSH_KEY_PATH;
  if (caminhoInformado) {
    const caminho = caminhoInformado === '~'
      ? os.homedir()
      : caminhoInformado.startsWith('~/')
        ? path.join(os.homedir(), caminhoInformado.slice(2))
        : caminhoInformado;

    let stat;
    try {
      stat = fs.statSync(caminho);
    } catch {
      console.error('[vps-tools] VPS_SSH_KEY_PATH aponta para arquivo inexistente ou inacessível.');
      process.exit(1);
    }
    if (!stat.isFile()) {
      console.error('[vps-tools] VPS_SSH_KEY_PATH precisa apontar para um arquivo regular.');
      process.exit(1);
    }
    return fs.readFileSync(caminho, 'utf8');
  }

  // Útil em CI/cofre que injeta o segredo diretamente no ambiente. Para uso
  // local, prefira VPS_SSH_KEY_PATH para não duplicar a chave em variáveis.
  return process.env.VPS_SSH_KEY || undefined;
}

const privateKey = carregarChavePrivada();
const passphrase = privateKey ? (process.env.VPS_SSH_PASSPHRASE || undefined) : undefined;

const missing = [];
if (!host) missing.push('VPS_HOST');
if (!privateKey && !password) missing.push('VPS_SSH_KEY_PATH/VPS_SSH_KEY (ou VPS_PASSWORD em host que aceite senha)');
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error('[vps-tools] VPS_PORT deve ser um inteiro entre 1 e 65535.');
  process.exit(1);
}
if (missing.length) {
  console.error(
    `[vps-tools] Configuração ausente: ${missing.join(', ')}.\n` +
    'Configure vps-tools/.env (veja vps-tools/.env.example) ou exporte as variáveis de ambiente.'
  );
  process.exit(1);
}

const config = { host, port, username, readyTimeout: 30000 };
if (privateKey) config.privateKey = privateKey;
if (passphrase) config.passphrase = passphrase;
if (password) config.password = password;

module.exports = config;
