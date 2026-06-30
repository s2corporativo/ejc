/**
 * EJC Deploy — Rebranding De Paula Teixeira (bronze)
 * Sobe o conjunto de arquivos alterados na refatoração visual e rebuilda o
 * container frontend na VPS. Faz BACKUP reversível do fonte remoto antes.
 *
 * Uso: node deploy-rebrand.js
 */
const { Client } = require('ssh2');
const fs = require('fs');
const path = require('path');

const sshConfig = require('./ssh-config');
const REMOTE_BASE = '/opt/ejc/frontend';
const LOCAL_BASE = path.join(__dirname, '..', 'frontend');

// Arquivos alterados/criados na refatoração visual (relativos a frontend/)
const FILES = [
  'tailwind.config.js',
  'index.html',
  'public/favicon.svg',
  'src/index.css',
  'src/components/Brand.tsx',
  'src/components/RichText.tsx',
  'src/components/AIResponse.tsx',
  'src/components/LegalDocument.tsx',
  'src/components/Layout.tsx',
  'src/components/Dashboards.tsx',
  'src/components/ExplicarMov.tsx',
  'src/components/NoticiasCard.tsx',
  'src/pages/LoginModern.tsx',
  'src/pages/RecuperarSenha.tsx',
  'src/pages/RedefinirSenha.tsx',
  'src/pages/TrocarSenha.tsx',
  'src/pages/AssistenteIA.tsx',
  'src/pages/AgenteIA.tsx',
  'src/pages/IA.tsx',
  'src/pages/Pecas.tsx',
  'src/pages/Prompts.tsx',
  'src/pages/ConteudoJuridico.tsx',
  'src/pages/Biblioteca.tsx',
  'src/pages/SalaDeGuerra.tsx',
  'src/pages/Wiki.tsx',
  'src/pages/CasoDetalhe.tsx',
  'src/pages/ramos/RamoBase.tsx',
];

const conn = new Client();

function exec(cmd) {
  return new Promise((resolve, reject) => {
    conn.exec(cmd, (err, stream) => {
      if (err) return reject(err);
      let out = '';
      stream.on('close', () => resolve(out));
      stream.on('data', (d) => { out += d; process.stdout.write(d); });
      stream.stderr.on('data', (d) => { out += d; process.stderr.write(d); });
    });
  });
}

function uploadAll(sftp) {
  return new Promise((resolve, reject) => {
    let i = 0;
    const next = () => {
      if (i >= FILES.length) return resolve();
      const rel = FILES[i++];
      const local = path.join(LOCAL_BASE, rel);
      const remote = REMOTE_BASE + '/' + rel;
      if (!fs.existsSync(local)) { console.error('FALTANDO local:', local); return reject(new Error('missing ' + rel)); }
      const dir = path.posix.dirname(remote);
      conn.exec(`mkdir -p "${dir}"`, (e, s) => {
        const doPut = () => sftp.fastPut(local, remote, (er) => {
          if (er) return reject(er);
          console.log('  ↑', rel);
          next();
        });
        if (s) s.on('close', doPut); else doPut();
      });
    };
    next();
  });
}

conn.on('ready', async () => {
  try {
    console.log('== 1/4 Backup do fonte remoto ==');
    await exec(`cd ${REMOTE_BASE} && ts=$(date +%Y%m%d_%H%M) && tar czf /opt/ejc/frontend_pre_rebrand_$ts.tgz src index.html tailwind.config.js public 2>/dev/null; ls -lh /opt/ejc/frontend_pre_rebrand_$ts.tgz; echo BACKUP_DONE`);

    console.log('\n== 2/4 Upload dos arquivos (' + FILES.length + ') ==');
    await new Promise((resolve, reject) => {
      conn.sftp((err, sftp) => err ? reject(err) : uploadAll(sftp).then(resolve, reject));
    });

    console.log('\n== 3/4 Rebuild do container frontend ==');
    await exec('cd /opt/ejc && docker compose build frontend 2>&1 | tail -20');

    console.log('\n== 4/4 Subindo container ==');
    await exec('cd /opt/ejc && docker compose up -d --no-deps frontend && echo DEPLOY_OK');

    console.log('\n== Verificação ==');
    await exec('sleep 3; docker ps --filter name=ejc_frontend --format "{{.Names}} {{.Status}}"; curl -s -o /dev/null -w "HTTP %{http_code}\\n" http://localhost:80/');
  } catch (e) {
    console.error('\nERRO no deploy:', e.message);
  } finally {
    conn.end();
  }
}).on('error', (e) => console.error('SSH Error:', e.message));

conn.connect({ ...sshConfig, readyTimeout: 30000 });
