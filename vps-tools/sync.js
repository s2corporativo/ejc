/**
 * EJC Sync Tool — sobe arquivo local para VPS e reinicia o serviço
 *
 * Uso:
 *   node sync.js backend routers/cases.py        -> sobe backend e reinicia ejc_backend
 *   node sync.js frontend pages/Dashboard.tsx    -> sobe frontend (requer rebuild)
 *   node sync.js frontend pages/Dashboard.tsx --no-restart
 */
const { Client } = require('ssh2');
const fs = require('fs');
const path = require('path');

const sshConfig = require('./ssh-config');
const BACKEND_REMOTE = '/opt/ejc/backend/app';
const FRONTEND_REMOTE = '/opt/ejc/frontend/src';
const LOCAL_BASE = path.join(__dirname, '..');

const [,, type, filePath, flag] = process.argv;

if (!type || !filePath) {
  console.log('Uso: node sync.js <backend|frontend> <caminho_relativo> [--no-restart]');
  console.log('Ex:  node sync.js backend routers/cases.py');
  console.log('Ex:  node sync.js frontend pages/Dashboard.tsx');
  process.exit(1);
}

const localFile = path.join(LOCAL_BASE, type === 'backend' ? 'backend/app' : 'frontend/src', filePath);
const remoteFile = (type === 'backend' ? BACKEND_REMOTE : FRONTEND_REMOTE) + '/' + filePath;
const noRestart = flag === '--no-restart';

if (!fs.existsSync(localFile)) {
  console.error('Arquivo local não encontrado:', localFile);
  process.exit(1);
}

const conn = new Client();
conn.on('ready', () => {
  conn.sftp((err, sftp) => {
    if (err) { console.error('SFTP error:', err.message); conn.end(); return; }
    const remoteDir = path.posix.dirname(remoteFile);
    conn.exec(`mkdir -p "${remoteDir}"`, (_, stream) => {
      if (stream) stream.on('close', upload); else upload();
    });

    function upload() {
      sftp.fastPut(localFile, remoteFile, e => {
        if (e) { console.error('Upload error:', e.message); conn.end(); return; }
        console.log('OK upload:', remoteFile);
        if (noRestart) { conn.end(); return; }
        const restartCmd = type === 'backend'
          ? 'docker restart ejc_backend && echo "Backend reiniciado"'
          : 'cd /opt/ejc && docker compose build frontend 2>&1 | tail -5 && docker compose up -d --no-deps frontend && echo "Frontend deploy OK"';
        conn.exec(restartCmd, (e2, stream2) => {
          if (e2) { console.error(e2.message); conn.end(); return; }
          stream2.on('close', () => conn.end());
          stream2.on('data', d => process.stdout.write(d));
          stream2.stderr.on('data', d => process.stderr.write(d));
        });
      });
    }
  });
}).on('error', e => console.error('SSH Error:', e.message));

conn.connect({ ...sshConfig, readyTimeout: 30000 });
