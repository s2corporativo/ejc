const { Client } = require('ssh2');
const fs = require('fs');
const sshConfig = require('./ssh-config');
fs.writeFileSync('_tiny.txt', 'hello-sftp-'+Date.now());
const conn = new Client();
conn.on('ready', () => {
  conn.sftp((err, sftp) => {
    if (err) { console.log('SFTP-SUBSYS-ERR:', err.message); conn.end(); return; }
    sftp.fastPut('_tiny.txt', '/tmp/_ejc_sftp_test.txt', (e) => {
      console.log(e ? ('PUT-ERR: '+e.message) : 'PUT-OK');
      conn.end();
    });
  });
}).on('error', e => console.log('CONN-ERR:', e.message));
conn.connect({ ...sshConfig, readyTimeout: 20000 });
