const { Client } = require('ssh2');
const CMD = process.argv.slice(2).join(' ') || 'echo ok';

const conn = new Client();
conn.on('ready', () => {
  conn.exec(CMD, (err, stream) => {
    if (err) { console.error(err); conn.end(); return; }
    stream.on('close', () => conn.end());
    stream.on('data', d => process.stdout.write(d));
    stream.stderr.on('data', d => process.stderr.write(d));
  });
}).on('error', e => console.error('Erro SSH:', e.message));

const sshConfig = require('./ssh-config');
conn.connect({ ...sshConfig, readyTimeout: 15000 });
