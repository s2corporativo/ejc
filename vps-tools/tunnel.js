// Túnel SSH: localhost:<porta_local> -> 127.0.0.1:<porta_remota> na VPS
// Uso: node tunnel.js [porta_local] [porta_remota]   (padrão: 8100 8100 — Graphiti MCP)
const net = require('net');
const { Client } = require('ssh2');
const sshConfig = require('./ssh-config');

const LOCAL_PORT = parseInt(process.argv[2] || '8100', 10);
const REMOTE_PORT = parseInt(process.argv[3] || '8100', 10);

const conn = new Client();
conn.on('ready', () => {
  const server = net.createServer(sock => {
    conn.forwardOut(sock.remoteAddress || '127.0.0.1', sock.remotePort || 0, '127.0.0.1', REMOTE_PORT, (err, stream) => {
      if (err) { sock.destroy(); return; }
      sock.pipe(stream).pipe(sock);
      stream.on('error', () => sock.destroy());
      sock.on('error', () => stream.destroy());
    });
  });
  server.listen(LOCAL_PORT, '127.0.0.1', () =>
    console.log(`Túnel ativo: http://127.0.0.1:${LOCAL_PORT} -> VPS 127.0.0.1:${REMOTE_PORT} (Ctrl+C encerra)`));
}).on('error', e => { console.error('Erro SSH:', e.message); process.exit(1); });

conn.connect({ ...sshConfig, readyTimeout: 15000, keepaliveInterval: 15000 });
