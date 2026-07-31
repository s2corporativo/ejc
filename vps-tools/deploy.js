#!/usr/bin/env node
/**
 * EJC VPS deploy helper.
 *
 * Run from C:\Users\User\EJC\vps-tools:
 *   node deploy.js --changed --dry-run
 *   node deploy.js --changed --yes
 *   node deploy.js backend/app/routers/cases.py frontend/src/pages/Casos.tsx --yes
 *   node deploy.js --manifest deploy-files.txt --yes
 *
 * Production facts verified on the VPS:
 * - The app code is baked into Docker images. Restart is not enough.
 * - Backend deploy needs docker compose build + recreate + alembic upgrade head.
 * - Frontend deploy needs docker compose build + recreate.
 * - SFTP upload works; SFTP download may be unavailable.
 *
 * Safety:
 * - Refuses .env/secret-looking files.
 * - Refuses files containing git conflict markers.
 * - Backs up the database before real deploy unless --no-backup is passed.
 * - Normalizes CRLF to LF for text files before upload.
 */

const { Client } = require("ssh2");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const REPO = path.resolve(__dirname, "..");
const REMOTE_ROOT = "/opt/ejc";
const DOMAIN = "https://ejc.depaulateixeira.adv.br";
const sshConfig = require("./ssh-config");

const argv = process.argv.slice(2);

function has(flag) {
  return argv.includes(flag);
}

function valueOf(flag, fallback = undefined) {
  const i = argv.indexOf(flag);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--")
    ? argv[i + 1]
    : fallback;
}

const opts = {
  changed: has("--changed"),
  dryRun: has("--dry-run"),
  noBackup: has("--no-backup"),
  noMigrate: has("--no-migrate"),
  backendOnly: has("--backend-only"),
  frontendOnly: has("--frontend-only"),
  yes: has("--yes"),
  skipPublic: has("--skip-public"),
  withEmbeddings: has("--with-embeddings"),
  base: valueOf("--base", "origin/main"),
  manifest: valueOf("--manifest"),
};

function usage(exitCode = 0) {
  console.log(`
Usage:
  node deploy.js --changed --yes
  node deploy.js --changed --base HEAD~1 --dry-run
  node deploy.js backend/app/routers/cases.py frontend/src/pages/Casos.tsx --yes
  node deploy.js --manifest deploy-files.txt --yes

Flags:
  --dry-run          Show what would be deployed; do not connect/upload.
  --changed          Deploy changed files from git diff, unstaged diff and untracked files.
  --base <ref>       Base ref for --changed. Default: origin/main.
  --manifest <file>  Text file with one repo-relative path per line.
  --backend-only     Keep only backend/* files.
  --frontend-only    Keep only frontend/* files.
  --no-backup        Skip database backup.
  --no-migrate       Skip alembic upgrade head.
  --with-embeddings  Rebuild embeddings service too, if present.
  --skip-public      Skip public HTTPS healthcheck.
  --yes              Required for a real deploy.
`);
  process.exit(exitCode);
}

if (has("--help") || has("-h")) usage(0);

function git(args) {
  return execFileSync("git", ["-C", REPO, ...args], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function changedFromGit() {
  const sets = [
    git(["diff", "--name-only", `${opts.base}...HEAD`]),
    git(["diff", "--name-only"]),
    git(["diff", "--name-only", "--cached"]),
    git(["ls-files", "--others", "--exclude-standard"]),
  ];
  return unique(sets.join("\n").split(/\r?\n/).filter(Boolean));
}

function fromManifest(file) {
  const abs = path.resolve(REPO, file);
  return fs
    .readFileSync(abs, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));
}

function positionalFiles() {
  const valueFlags = new Set(["--base", "--manifest"]);
  const files = [];
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (valueFlags.has(token)) {
      i += 1;
      continue;
    }
    if (!token.startsWith("--")) files.push(token);
  }
  return files;
}

function unique(list) {
  return [...new Set(list)];
}

function normalizePath(file) {
  return file.replace(/\\/g, "/").replace(/^\.\//, "");
}

function isDeployable(file) {
  return file.startsWith("backend/") || file.startsWith("frontend/");
}

function isLocalArtifact(file) {
  const lower = file.toLowerCase();
  return (
    /(^|\/)(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache)(\/|$)/.test(lower) ||
    /\.(db|sqlite|sqlite3|pyc|pyo|log|bak|tmp)$/i.test(lower)
  );
}

function isTextFile(file) {
  return /\.(py|pyi|ts|tsx|js|jsx|css|html|json|md|txt|yml|yaml|toml|ini|sh|sql|conf|nginx)$/i.test(file);
}

function looksSecret(file) {
  const lower = file.toLowerCase();
  return (
    /(^|\/)\.env($|[.\w-])/.test(lower) ||
    /\.(pem|key|p12|pfx|crt)$/i.test(lower) ||
    /(^|\/)(credentials|rclone\.conf|gdrive_sa\.json|.*service-account.*\.json)$/.test(lower)
  );
}

function containsConflictMarker(abs) {
  if (!isTextFile(abs)) return false;
  const text = fs.readFileSync(abs, "utf8");
  return /^(<<<<<<<|=======|>>>>>>>)(?: |\t|$)/m.test(text);
}

function remotePath(file) {
  return `${REMOTE_ROOT}/${file}`;
}

let files;
if (opts.changed) files = changedFromGit();
else if (opts.manifest) files = fromManifest(opts.manifest);
else files = positionalFiles();

files = unique(files.map(normalizePath))
  .filter(isDeployable)
  .filter((file) => !isLocalArtifact(file))
  .filter((file) => fs.existsSync(path.join(REPO, file)));

if (opts.backendOnly && opts.frontendOnly) {
  console.error("Use only one of --backend-only or --frontend-only.");
  process.exit(1);
}
if (opts.backendOnly) files = files.filter((file) => file.startsWith("backend/"));
if (opts.frontendOnly) files = files.filter((file) => file.startsWith("frontend/"));

if (!files.length) {
  console.error("No deployable files found under backend/ or frontend/.");
  usage(1);
}

const blockedSecrets = files.filter(looksSecret);
if (blockedSecrets.length) {
  console.error("Refusing to deploy secret-looking files:");
  blockedSecrets.forEach((file) => console.error(`  ${file}`));
  process.exit(1);
}

const conflictFiles = files.filter((file) => containsConflictMarker(path.join(REPO, file)));
if (conflictFiles.length) {
  console.error("Refusing to deploy files with git conflict markers:");
  conflictFiles.forEach((file) => console.error(`  ${file}`));
  process.exit(1);
}

const touchesBackend = files.some((file) => file.startsWith("backend/"));
const touchesFrontend = files.some((file) => file.startsWith("frontend/"));

console.log(`\n== EJC VPS DEPLOY -> ${sshConfig.host}:${REMOTE_ROOT} ==`);
console.log(`Files: ${files.length}`);
files.forEach((file) => console.log(`  ${file}`));
console.log("");
console.log(`Backend: ${touchesBackend ? "yes (build + recreate + migrate)" : "no"}`);
console.log(`Frontend: ${touchesFrontend ? "yes (build + recreate)" : "no"}`);
console.log(`DB backup: ${opts.noBackup ? "skip" : "yes"}`);
console.log(`Migration: ${touchesBackend && !opts.noMigrate ? "yes" : "skip"}`);
console.log(`Mode: ${opts.dryRun ? "dry-run" : "real"}`);

if (opts.dryRun) {
  console.log("\nDry-run only. Nothing was uploaded.");
  process.exit(0);
}

if (!opts.yes) {
  console.error("\nReal deploy requires --yes. Run again with --dry-run first if unsure.");
  process.exit(1);
}

function timestamp() {
  return new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
}

function sshExec(conn, command) {
  return new Promise((resolve, reject) => {
    conn.exec(command, (err, stream) => {
      if (err) {
        reject(err);
        return;
      }
      let output = "";
      stream.on("data", (chunk) => {
        output += chunk.toString();
        process.stdout.write(chunk);
      });
      stream.stderr.on("data", (chunk) => {
        output += chunk.toString();
        process.stderr.write(chunk);
      });
      stream.on("close", (code) => {
        if (code === 0) resolve(output);
        else reject(new Error(`Command failed (${code}): ${command}\n${output.slice(-1200)}`));
      });
    });
  });
}

function sftpPut(sftp, localFile, remoteFile) {
  return new Promise((resolve, reject) => {
    const tmpFile = path.join(os.tmpdir(), `ejc-deploy-${process.pid}-${path.basename(localFile)}`);
    const relative = normalizePath(path.relative(REPO, localFile));
    const content = fs.readFileSync(localFile);
    const payload = isTextFile(relative)
      ? Buffer.from(content.toString("utf8").replace(/\r\n/g, "\n"), "utf8")
      : content;

    fs.writeFileSync(tmpFile, payload);
    sftp.fastPut(tmpFile, remoteFile, (err) => {
      try {
        fs.unlinkSync(tmpFile);
      } catch (_) {
        // Best effort cleanup only.
      }
      if (err) reject(err);
      else resolve();
    });
  });
}

const conn = new Client();

conn
  .on("ready", () => {
    conn.sftp(async (err, sftp) => {
      try {
        if (err) throw err;

        const ts = timestamp();
        console.log("\n[preflight] docker compose config");
        await sshExec(conn, `cd ${REMOTE_ROOT} && docker compose config >/tmp/ejc_compose_config_${ts}.txt`);

        if (!opts.noBackup) {
          console.log("\n[1/6] database backup");
          await sshExec(
            conn,
            [
              `mkdir -p ${REMOTE_ROOT}/backups/deploy_${ts}`,
              `docker exec ejc_db sh -lc 'pg_dump -U "\${POSTGRES_USER:-ejc_user}" -d "\${POSTGRES_DB:-ejc_db}" -Fc' > ${REMOTE_ROOT}/backups/deploy_${ts}/ejc_db.dump`,
              `ls -lh ${REMOTE_ROOT}/backups/deploy_${ts}/ejc_db.dump`,
            ].join(" && ")
          );
        }

        console.log("\n[2/6] upload files");
        for (const file of files) {
          const localFile = path.join(REPO, file);
          const remoteFile = remotePath(file);
          await sshExec(conn, `mkdir -p "${path.posix.dirname(remoteFile)}"`);
          await sftpPut(sftp, localFile, remoteFile);
          console.log(`  OK ${remoteFile}`);
        }

        if (touchesBackend) {
          console.log("\n[3/6] build backend services");
          const buildBackend = [
            "cd /opt/ejc",
            "services=$(docker compose config --services)",
            "targets='backend'",
            "echo \"$services\" | grep -qx worker && targets=\"$targets worker\" || true",
            opts.withEmbeddings
              ? "echo \"$services\" | grep -qx embeddings && targets=\"$targets embeddings\" || true"
              : "true",
            "echo \"building: $targets\"",
            "docker compose build $targets",
          ].join(" && ");
          await sshExec(conn, buildBackend);

          console.log("\n[4/6] recreate backend services");
          await sshExec(
            conn,
            [
              "cd /opt/ejc",
              "services=$(docker compose config --services)",
              "targets='backend'",
              "echo \"$services\" | grep -qx worker && targets=\"$targets worker\" || true",
              opts.withEmbeddings
                ? "echo \"$services\" | grep -qx embeddings && targets=\"$targets embeddings\" || true"
                : "true",
              "docker compose up -d --no-deps $targets",
            ].join(" && ")
          );

          if (!opts.noMigrate) {
            console.log("\n[5/6] alembic upgrade head");
            await sshExec(
              conn,
              [
                "sleep 6",
                "docker exec ejc_backend alembic current",
                "docker exec ejc_backend alembic upgrade head",
                "docker exec ejc_backend alembic current",
              ].join(" && ")
            );
          }
        }

        if (touchesFrontend) {
          console.log("\n[frontend] build + recreate");
          await sshExec(
            conn,
            "cd /opt/ejc && docker compose build frontend && docker compose up -d --no-deps frontend"
          );
        }

        console.log("\n[6/6] healthcheck");
        await sshExec(
          conn,
          [
            "sleep 5",
            "docker exec ejc_backend python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health').read().decode())\"",
            opts.skipPublic
              ? "true"
              : `curl -fsS -o /dev/null -w 'public health: %{http_code}\\n' ${DOMAIN}/api/health`,
          ].join(" && ")
        );

        console.log("\nDeploy finished.");
        conn.end();
      } catch (error) {
        console.error(`\nDeploy failed: ${error.message}`);
        console.error(`Rollback note: DB backups are under ${REMOTE_ROOT}/backups/deploy_<timestamp>/ when backup was enabled.`);
        conn.end();
        process.exit(1);
      }
    });
  })
  .on("error", (error) => {
    console.error(`SSH error: ${error.message}`);
    process.exit(1);
  });

conn.connect({ ...sshConfig, readyTimeout: 30000 });
