/**
 * EJC Pull — baixa um arquivo da VPS para o local via SFTP.
 * Uso: node pull-file.js <remote_abs_path> <local_abs_path>
 */
const { Client } = require('ssh2');
const [,, remote, local] = process.argv;
if (!remote || !local) { console.error('Uso: node pull-file.js <remote> <local>'); process.exit(1); }
const conn = new Client();
conn.on('ready', () => {
  conn.sftp((err, sftp) => {
    if (err) { console.error('SFTP:', err.message); conn.end(); return; }
    sftp.fastGet(remote, local, (e) => {
      if (e) console.error('GET error:', e.message);
      else console.log('OK baixado:', local);
      conn.end();
    });
  });
}).on('error', (e) => console.error('SSH:', e.message));
const sshConfig = require('./ssh-config');
conn.connect({ ...sshConfig, readyTimeout: 30000 });
