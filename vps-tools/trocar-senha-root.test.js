/**
 * Testes de vps-tools/trocar-senha-root.js
 *
 * Rodar:  node --test vps-tools/
 *
 * Cobre a lógica que dá para exercitar sem uma VPS: validação da senha,
 * reescrita do arquivo local de ambiente e — o ponto mais sensível — a
 * garantia de que a senha viaja pelo STDIN do `chpasswd` e nunca pela
 * linha de comando (onde apareceria em `ps` e nos logs de auditoria).
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');

const { atualizarEnv, validarSenha, trocarSenhaRemota } = require('./trocar-senha-root');

const SENHA_VALIDA = 'senha-de-teste-longa';

function envTemporario(conteudo) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ejc-vps-'));
  const arquivo = path.join(dir, '.env');
  fs.writeFileSync(arquivo, conteudo);
  return arquivo;
}

/** Dublê de conexão ssh2: registra o comando e o que foi escrito no stdin. */
function connFalso(capturas, codigoSaida = 0, stderr = '') {
  return {
    exec(comando, cb) {
      capturas.comando = comando;
      const stream = new EventEmitter();
      stream.stderr = new EventEmitter();
      stream.end = (dados) => {
        capturas.stdin = dados;
        process.nextTick(() => {
          if (stderr) stream.stderr.emit('data', Buffer.from(stderr));
          stream.emit('close', codigoSaida);
        });
      };
      cb(null, stream);
    },
  };
}

test('validarSenha recusa entrada vazia', () => {
  assert.match(validarSenha('', ''), /Nada foi digitado/);
});

test('validarSenha recusa senhas divergentes', () => {
  assert.match(validarSenha(SENHA_VALIDA, `${SENHA_VALIDA}x`), /não conferem/);
});

test('validarSenha recusa senha curta', () => {
  assert.match(validarSenha('curta1', 'curta1'), /muito curta/);
});

test('validarSenha recusa quebra de linha (evita injeção no chpasswd)', () => {
  const comQuebra = `${SENHA_VALIDA}\nroot:outra`;
  assert.match(validarSenha(comQuebra, comQuebra), /quebra de linha/);
});

test('validarSenha aceita senha longa e coincidente', () => {
  assert.strictEqual(validarSenha(SENHA_VALIDA, SENHA_VALIDA), null);
});

test('atualizarEnv substitui VPS_PASSWORD e preserva as demais linhas', () => {
  const arquivo = envTemporario(
    '# comentario\nVPS_HOST=exemplo.invalido\nVPS_PASSWORD=antiga\nVPS_PORT=22\n'
  );
  assert.strictEqual(atualizarEnv('nova-senha', arquivo), true);

  const linhas = fs.readFileSync(arquivo, 'utf8').split('\n');
  assert.ok(linhas.includes('VPS_PASSWORD=nova-senha'));
  assert.ok(linhas.includes('VPS_HOST=exemplo.invalido'));
  assert.ok(linhas.includes('VPS_PORT=22'));
  assert.ok(linhas.includes('# comentario'));
  assert.ok(!linhas.includes('VPS_PASSWORD=antiga'));
});

test('atualizarEnv acrescenta VPS_PASSWORD quando a chave não existe', () => {
  const arquivo = envTemporario('VPS_HOST=exemplo.invalido\n');
  assert.strictEqual(atualizarEnv('nova-senha', arquivo), true);
  assert.ok(fs.readFileSync(arquivo, 'utf8').includes('VPS_PASSWORD=nova-senha'));
});

test('atualizarEnv devolve false quando o arquivo não existe', () => {
  const inexistente = path.join(os.tmpdir(), 'ejc-vps-inexistente', '.env');
  assert.strictEqual(atualizarEnv('nova-senha', inexistente), false);
});

test('atualizarEnv grava o arquivo com permissão restrita a dono', { skip: process.platform === 'win32' }, () => {
  const arquivo = envTemporario('VPS_PASSWORD=antiga\n');
  atualizarEnv('nova-senha', arquivo);
  const modo = fs.statSync(arquivo).mode & 0o777;
  assert.strictEqual(modo, 0o600);
});

test('trocarSenhaRemota entrega a senha pelo stdin, nunca no comando', async () => {
  const capturas = {};
  const resultado = await trocarSenhaRemota(connFalso(capturas), 'root', SENHA_VALIDA);

  assert.strictEqual(resultado.code, 0);
  assert.strictEqual(capturas.comando, 'chpasswd');
  assert.strictEqual(capturas.stdin, `root:${SENHA_VALIDA}\n`);
  // A garantia central: a senha não pode estar na linha de comando.
  assert.ok(!capturas.comando.includes(SENHA_VALIDA));
});

test('trocarSenhaRemota escala com sudo -n quando o usuário não é root', async () => {
  const capturas = {};
  await trocarSenhaRemota(connFalso(capturas), 'deploy', SENHA_VALIDA);

  assert.strictEqual(capturas.comando, 'sudo -n chpasswd');
  assert.strictEqual(capturas.stdin, `deploy:${SENHA_VALIDA}\n`);
  assert.ok(!capturas.comando.includes(SENHA_VALIDA));
});

test('trocarSenhaRemota propaga código de saída e stderr do chpasswd', async () => {
  const capturas = {};
  const conn = connFalso(capturas, 1, 'chpasswd: falha\n');
  const resultado = await trocarSenhaRemota(conn, 'root', SENHA_VALIDA);

  assert.strictEqual(resultado.code, 1);
  assert.strictEqual(resultado.stderr, 'chpasswd: falha');
});
