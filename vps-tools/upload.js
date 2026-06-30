const { Client } = require('ssh2');
const fs = require('fs');
const path = require('path');

const [,, remotePath, localPath] = process.argv;
if (!remotePath || !localPath) {
  console.error('Usage: node sftp_write.js <remote_path> <local_path>');
  process.exit(1);
}

if (!fs.existsSync(localPath)) {
  console.error(`Local file not found: ${localPath}`);
  process.exit(1);
}

const conn = new Client();
conn.on('ready', () => {
  conn.sftp((err, sftp) => {
    if (err) { console.error('SFTP init error:', err.message); conn.end(); process.exit(1); return; }

    // Ensure remote directory exists
    const remoteDir = path.posix.dirname(remotePath);
    conn.exec(`mkdir -p "${remoteDir}"`, (err2, stream) => {
      if (err2) { console.error('mkdir error:', err2.message); }
      if (stream) {
        stream.on('close', () => uploadFile());
        stream.resume();
      } else {
        uploadFile();
      }
    });

    function uploadFile() {
      const readStream = fs.createReadStream(localPath);
      const writeStream = sftp.createWriteStream(remotePath);
      writeStream.on('close', () => {
        console.log(`OK: ${remotePath}`);
        conn.end();
      });
      writeStream.on('error', e => {
        console.error(`Write error: ${e.message}`);
        conn.end();
        process.exit(1);
      });
      readStream.on('error', e => {
        console.error(`Read error: ${e.message}`);
        conn.end();
        process.exit(1);
      });
      readStream.pipe(writeStream);
    }
  });
}).on('error', e => {
  console.error('SSH error:', e.message);
  process.exit(1);
});

const sshConfig = require('./ssh-config');
conn.connect({ ...sshConfig, readyTimeout: 20000 });
