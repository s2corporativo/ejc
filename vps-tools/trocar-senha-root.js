#!/usr/bin/env node
/**
 * vps-tools/trocar-senha-root.js
 *
 * Troca a senha do usuário de acesso da VPS (padrão: root) por SSH, sem reboot
 * e sem depender do painel do provedor.
 *
 * Uso:
 *   node vps-tools/trocar-senha-root.js
 *
 * Pré-requisito: o acesso ATUAL precisa estar funcionando (arquivo local de
 * ambiente com VPS_PASSWORD válida, ou as variáveis exportadas no shell).
 * Se você já perdeu o acesso, este script não recupera nada — use primeiro o
 * reset pelo painel do provedor, descrito em RUNBOOK_ACESSO_VPS.md.
 *
 * Decisões de segurança:
 *  - A senha nova é entregue ao `chpasswd` pelo STDIN da sessão SSH, nunca na
 *    linha de comando. Assim ela não aparece em `ps`, nem no histórico do
 *    shell remoto, nem nos logs de auditoria de comando.
 *  - A entrada no terminal é oculta e pedida duas vezes.
 *  - Após a troca, o script abre uma conexão NOVA com a senha nova para provar
 *    que ela funciona. Só então grava o arquivo local de ambiente (modo 0600).
 *  - Nenhuma senha é impressa na tela, em nenhuma hipótese.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { Client } = require('ssh2');

// `ssh-config` encerra o processo quando faltam credenciais. Por isso ele é
// carregado dentro de main(), e não no topo: assim as funções deste módulo
// continuam importáveis (e testáveis) sem exigir um .env configurado.
const CAMINHO_ENV = path.join(__dirname, '.env');
const TAMANHO_MINIMO = 12;

/** Lê uma linha do terminal sem ecoar os caracteres digitados. */
function perguntarOculto(pergunta) {
  return new Promise((resolve, reject) => {
    if (!process.stdin.isTTY) {
      reject(new Error(
        'Entrada não interativa. Rode este script direto no terminal, ' +
        'sem pipe ou redirecionamento.'
      ));
      return;
    }
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: true,
    });
    let silenciar = false;
    rl._writeToOutput = (texto) => {
      if (!silenciar) process.stdout.write(texto);
    };
    rl.question(pergunta, (resposta) => {
      rl.close();
      process.stdout.write('\n');
      resolve(resposta);
    });
    // A pergunta já foi impressa acima; a partir daqui o eco fica mudo.
    silenciar = true;
  });
}

/** Abre uma conexão SSH com as credenciais dadas e resolve com o Client. */
function conectar(credenciais) {
  return new Promise((resolve, reject) => {
    const conn = new Client();
    const aoErro = (e) => {
      conn.removeAllListeners();
      reject(e);
    };
    conn.on('ready', () => {
      conn.removeListener('error', aoErro);
      resolve(conn);
    });
    conn.on('error', aoErro);
    conn.connect({ ...credenciais, readyTimeout: 30000 });
  });
}

/**
 * Executa `chpasswd` no host remoto entregando `usuario:senha` pelo stdin.
 * Resolve com o código de saída e o stderr acumulado.
 */
function trocarSenhaRemota(conn, usuario, novaSenha) {
  // chpasswd precisa de root. Se o login não for root, escala com sudo -n
  // (sem prompt): um sudo que peça senha travaria a sessão sem sinal claro.
  const comando = usuario === 'root' ? 'chpasswd' : 'sudo -n chpasswd';
  return new Promise((resolve, reject) => {
    conn.exec(comando, (err, stream) => {
      if (err) { reject(err); return; }
      let stderr = '';
      stream.stderr.on('data', (d) => { stderr += d.toString(); });
      stream.on('close', (code) => resolve({ code, stderr: stderr.trim() }));
      stream.on('error', reject);
      // A senha trafega pelo canal já cifrado do SSH, como stdin do processo.
      stream.end(`${usuario}:${novaSenha}\n`);
    });
  });
}

/** Reescreve VPS_PASSWORD no arquivo local de ambiente, preservando o resto. */
function atualizarEnv(novaSenha, caminho = CAMINHO_ENV) {
  if (!fs.existsSync(caminho)) return false;
  const linhas = fs.readFileSync(caminho, 'utf8').split(/\r?\n/);
  let encontrou = false;
  const saida = linhas.map((linha) => {
    if (/^\s*VPS_PASSWORD\s*=/.test(linha)) {
      encontrou = true;
      return `VPS_PASSWORD=${novaSenha}`;
    }
    return linha;
  });
  if (!encontrou) saida.push(`VPS_PASSWORD=${novaSenha}`);
  fs.writeFileSync(caminho, saida.join('\n'), { encoding: 'utf8', mode: 0o600 });
  try { fs.chmodSync(caminho, 0o600); } catch { /* Windows não aplica */ }
  return true;
}

/** Valida a senha digitada. Devolve mensagem de erro, ou null quando está ok. */
function validarSenha(senha1, senha2) {
  if (!senha1) return 'Nada foi digitado. Nada alterado.';
  if (senha1 !== senha2) return 'As senhas não conferem. Nada alterado.';
  if (senha1.length < TAMANHO_MINIMO) {
    return `Senha muito curta (mínimo ${TAMANHO_MINIMO} caracteres). Nada alterado.`;
  }
  if (/[\r\n]/.test(senha1)) {
    return 'A senha não pode conter quebra de linha. Nada alterado.';
  }
  return null;
}

async function main() {
  const sshConfig = require('./ssh-config');
  const usuario = sshConfig.username;

  console.log('Troca de senha da VPS por SSH');
  console.log(`  host....: ${sshConfig.host}`);
  console.log(`  porta...: ${sshConfig.port}`);
  console.log(`  usuário.: ${usuario}`);
  console.log('');

  const senha1 = await perguntarOculto('Nova senha: ');
  const senha2 = senha1 ? await perguntarOculto('Repita a nova senha: ') : '';
  const erro = validarSenha(senha1, senha2);
  if (erro) throw new Error(erro);

  console.log('\n[1/3] Conectando com as credenciais atuais...');
  const conn = await conectar(sshConfig);

  console.log('[2/3] Aplicando a nova senha via chpasswd...');
  let resultado;
  try {
    resultado = await trocarSenhaRemota(conn, usuario, senha1);
  } finally {
    conn.end();
  }
  if (resultado.code !== 0) {
    throw new Error(
      `chpasswd falhou (código ${resultado.code}).` +
      (resultado.stderr ? ` Detalhe: ${resultado.stderr}` : '')
    );
  }

  console.log('[3/3] Verificando: abrindo conexão nova com a senha nova...');
  const verificacao = await conectar({
    host: sshConfig.host,
    port: sshConfig.port,
    username: usuario,
    password: senha1,
    readyTimeout: 30000,
  });
  verificacao.end();

  const gravou = atualizarEnv(senha1);
  console.log('\nOK — senha trocada e verificada por login novo.');
  console.log(gravou
    ? `VPS_PASSWORD atualizada em ${CAMINHO_ENV} (permissão 0600).`
    : `Atenção: ${CAMINHO_ENV} não existe; atualize VPS_PASSWORD onde você a mantém.`);
  console.log('\nLembre-se de atualizar também o segredo VPS_PASSWORD no GitHub');
  console.log('(Settings > Secrets and variables > Actions), senão a esteira de');
  console.log('deploy continuará sendo recusada pelo servidor.');
}

module.exports = { atualizarEnv, validarSenha, trocarSenhaRemota, conectar };

if (require.main === module) {
  main().catch((e) => {
    console.error(`\nERRO: ${e.message}`);
    process.exit(1);
  });
}
