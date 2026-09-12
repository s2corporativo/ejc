const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const modulePath = path.join(__dirname, 'ssh-config.js');
const probe = `
const c = require(${JSON.stringify(modulePath)});
process.stdout.write(JSON.stringify({
  host: c.host,
  port: c.port,
  username: c.username,
  hasKey: Boolean(c.privateKey),
  hasPassword: Boolean(c.password),
  hasPassphrase: Boolean(c.passphrase)
}));
`;

function envBase(extra = {}) {
  const env = { ...process.env };
  for (const key of [
    'VPS_HOST', 'VPS_USER', 'VPS_PORT', 'VPS_PASSWORD',
    'VPS_SSH_KEY_PATH', 'VPS_SSH_KEY', 'VPS_SSH_PASSPHRASE', 'VPS_ENV_FILE'
  ]) delete env[key];
  // Isola os testes de qualquer vps-tools/.env real presente na máquina.
  env.VPS_ENV_FILE = '';
  return { ...env, ...extra };
}

function run(extra) {
  return spawnSync(process.execPath, ['-e', probe], {
    cwd: __dirname,
    env: envBase(extra),
    encoding: 'utf8'
  });
}

test('aceita chave literal sem exigir senha', () => {
  const result = run({
    VPS_HOST: 'example.invalid',
    VPS_SSH_KEY: 'TEST-PRIVATE-KEY',
    VPS_SSH_PASSPHRASE: 'TEST-PASSPHRASE'
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    host: 'example.invalid',
    port: 22,
    username: 'root',
    hasKey: true,
    hasPassword: false,
    hasPassphrase: true
  });
});

test('aceita chave por arquivo e mantém senha somente como fallback', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ejc-ssh-key-'));
  const keyPath = path.join(dir, 'id_test');
  fs.writeFileSync(keyPath, 'TEST-PRIVATE-KEY', { mode: 0o600 });
  try {
    const result = run({
      VPS_HOST: 'example.invalid',
      VPS_USER: 'deploy',
      VPS_PORT: '2222',
      VPS_SSH_KEY_PATH: keyPath,
      VPS_PASSWORD: 'TEST-PASSWORD'
    });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout), {
      host: 'example.invalid',
      port: 2222,
      username: 'deploy',
      hasKey: true,
      hasPassword: true,
      hasPassphrase: false
    });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('falha fechado quando não há método de autenticação', () => {
  const result = run({ VPS_HOST: 'example.invalid' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Configuração ausente/);
});

test('falha fechado quando o caminho da chave não existe', () => {
  const result = run({
    VPS_HOST: 'example.invalid',
    VPS_SSH_KEY_PATH: path.join(os.tmpdir(), 'ejc-chave-inexistente')
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /arquivo inexistente ou inacessível/);
});

test('rejeita porta SSH inválida', () => {
  const result = run({
    VPS_HOST: 'example.invalid',
    VPS_SSH_KEY: 'TEST-PRIVATE-KEY',
    VPS_PORT: '70000'
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /VPS_PORT deve ser um inteiro/);
});

test('rejeita arquivo de chave legível por grupo ou outros', { skip: process.platform === 'win32' }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ejc-ssh-key-mode-'));
  const keyPath = path.join(dir, 'id_insecure');
  fs.writeFileSync(keyPath, 'TEST-PRIVATE-KEY', { mode: 0o644 });
  try {
    fs.chmodSync(keyPath, 0o644);
    const result = run({
      VPS_HOST: 'example.invalid',
      VPS_SSH_KEY_PATH: keyPath
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /permissões 0600/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
