# ── app/services/backup_service.py ───────────────────────────────────────────
# Backup diário automatizado → Google Drive.
#
# Desenho de segurança (LGPD):
# - O dump do Postgres carrega PII (clientes, processos): TODO artefato é
#   cifrado com Fernet (BACKUP_ENCRYPTION_KEY) ANTES de sair do VPS. Perder a
#   chave = perder os backups — ela deve ser guardada fora do servidor.
# - Usa identidade Google exclusiva do backup quando configurada
#   (BACKUP_GOOGLE_DRIVE_*), preservando o escopo somente leitura do RAG.
#   O modo legado herdado permanece explícito para compatibilidade.
# - Rotação apaga SÓ arquivos com o prefixo do EJC (ejc_backup_) na pasta.
# - Segredos (chave, senha do banco) nunca vão para log/erro/estado.
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from cryptography.fernet import Fernet
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger("ejc.backup")
settings = get_settings()

# Prefixo do EJC nos artefatos enviados ao Drive — a rotação NUNCA toca
# arquivos fora deste prefixo (a pasta pode conter outros documentos).
PREFIXO_BACKUP = "ejc_backup_"
# Guard de processo: um backup por vez (pg_dump + upload podem levar minutos).
# Flag booleana testada-e-setada SINCRONAMENTE (sem await entre teste e set) no
# início de executar_backup — imune ao TOCTOU de check + `async with Lock`.
_em_execucao = False


# ── Configuração ──────────────────────────────────────────────────────────────

def hora_backup_utc() -> tuple[int, int]:
    """Converte BACKUP_HORA_UTC ("HH:MM") em (hora, minuto). Valor malformado
    cai no default 05:00 com warning — nunca derruba o boot do scheduler."""
    raw = (settings.BACKUP_HORA_UTC or "").strip()
    try:
        hora_s, minuto_s = raw.split(":", 1)
        hora, minuto = int(hora_s), int(minuto_s)
        if 0 <= hora <= 23 and 0 <= minuto <= 59:
            return hora, minuto
    except (ValueError, AttributeError):
        pass
    logger.warning("[Backup] BACKUP_HORA_UTC inválida (%r) — usando 05:00 UTC", raw)
    return 5, 0


def configuracao_status() -> dict[str, bool | str]:
    """Configuração operacional sem expor qualquer segredo."""
    from app.services import backup_drive_auth

    auth = backup_drive_auth.auth_status()
    dedicada = bool(auth["credencial_dedicada_configurada"])
    # Em auto/inherit, GOOGLE_DRIVE_* continua aceito por compatibilidade.
    herdada_permitida = auth["auth_mode"] in {"auto", "inherit"}
    if herdada_permitida and not dedicada:
        from app.services import google_drive_service as gdrive

        inherited = gdrive.auth_status()
        credencial_drive = any(
            bool(value)
            for key, value in inherited.items()
            if key != "auth_mode"
        )
    else:
        credencial_drive = dedicada
    return {
        "enabled": bool(settings.BACKUP_ENABLED),
        "chave_configurada": bool((settings.BACKUP_ENCRYPTION_KEY or "").strip()),
        "pasta_configurada": bool((settings.BACKUP_DRIVE_FOLDER_ID or "").strip()),
        "credencial_drive_configurada": credencial_drive,
        "credencial_dedicada_configurada": dedicada,
        "auth_mode": str(auth["auth_mode"]),
        "pg_dump_disponivel": shutil.which("pg_dump") is not None,
    }


def em_execucao() -> bool:
    return _em_execucao


# ── Criptografia (Fernet) ─────────────────────────────────────────────────────

def _fernet() -> Fernet:
    chave = (settings.BACKUP_ENCRYPTION_KEY or "").strip()
    if not chave:
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY ausente. O backup NÃO sai do VPS sem "
            "criptografia (LGPD). Gere a chave com: python3 -c 'from "
            "cryptography.fernet import Fernet; print(Fernet.generate_key()"
            ".decode())' e defina no .env."
        )
    try:
        return Fernet(chave.encode())
    except Exception as exc:
        # Não incluir a chave na mensagem — segredo nunca vai para log.
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY inválida: precisa ser uma chave Fernet "
            "(32 bytes url-safe base64)."
        ) from exc


def cifrar_arquivo(origem: str, destino: str, chave: str | None = None) -> int:
    """Cifra `origem` → `destino` com Fernet. Retorna o tamanho cifrado (bytes).

    Fernet opera em memória (não há streaming); aceitável para o porte do
    escritório — o limite de uploads (BACKUP_UPLOADS_MAX_MB) protege a RAM.
    """
    f = Fernet(chave.encode()) if chave else _fernet()
    with open(origem, "rb") as src:
        token = f.encrypt(src.read())
    with open(destino, "wb") as dst:
        dst.write(token)
    return len(token)


def decifrar_arquivo(origem: str, destino: str, chave: str | None = None) -> int:
    """Decifra um artefato de backup (usado na restauração e nos testes)."""
    f = Fernet(chave.encode()) if chave else _fernet()
    with open(origem, "rb") as src:
        dados = f.decrypt(src.read())
    with open(destino, "wb") as dst:
        dst.write(dados)
    return len(dados)


# ── Artefatos ────────────────────────────────────────────────────────────────

def _nome_artefato(sufixo: str, ts: datetime) -> str:
    """ejc_backup_<UTC compacto>_<sufixo>.enc — prefixo fixo para a rotação."""
    return f"{PREFIXO_BACKUP}{ts.strftime('%Y%m%dT%H%M%SZ')}_{sufixo}.enc"


def _pg_dump_para(destino: str) -> int:
    """Roda pg_dump -Fc (formato custom, já comprimido) para `destino`.

    Bloqueante — chamar via asyncio.to_thread. Retorna tamanho em bytes.
    """
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError(
            "Binário pg_dump não encontrado no container. Instale o pacote "
            "postgresql-client na imagem do backend (já presente no "
            "Dockerfile oficial) — sem ele o backup do banco é impossível."
        )
    url = urlparse(settings.DATABASE_URL_SYNC)
    # urlparse devolve credenciais PERCENT-ENCODED (senha com @ / : falharia
    # no pg_dump) — unquote() restaura os valores reais.
    # Senha via env PGPASSWORD (nunca em argv — visível em `ps`).
    env = {**os.environ, "PGPASSWORD": unquote(url.password or "")}
    cmd = [
        pg_dump,
        "-h", url.hostname or "localhost",
        "-p", str(url.port or 5432),
        "-U", unquote(url.username or ""),
        "-d", unquote((url.path or "/").lstrip("/")),
        "-Fc",
        "-f", destino,
    ]
    r = subprocess.run(
        cmd, env=env, timeout=settings.BACKUP_PG_DUMP_TIMEOUT,
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # stderr do pg_dump não contém a senha (passada via env).
        raise RuntimeError(f"pg_dump retornou código {r.returncode}: {(r.stderr or '')[:300]}")
    return os.path.getsize(destino)


def _tamanho_diretorio(caminho: str) -> int:
    total = 0
    for raiz, _dirs, arquivos in os.walk(caminho):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                continue
    return total


def _tar_uploads_para(destino: str) -> int:
    """Empacota UPLOAD_DIR em tar.gz. Bloqueante — usar asyncio.to_thread.

    O diretório está VIVO durante o backup (uploads/remoções concorrentes):
    arquivo que sumir entre o walk e o tar.add é logado e pulado — nunca
    derruba o backup inteiro."""
    base = settings.UPLOAD_DIR
    with tarfile.open(destino, "w:gz") as tar:
        for raiz, _dirs, arquivos in os.walk(base):
            for nome in arquivos:
                caminho = os.path.join(raiz, nome)
                arcname = os.path.join("uploads", os.path.relpath(caminho, base))
                try:
                    tar.add(caminho, arcname=arcname, recursive=False)
                except FileNotFoundError:
                    logger.warning(
                        "[Backup] arquivo removido durante o tar (pulado): %s",
                        caminho,
                    )
    return os.path.getsize(destino)


# ── Google Drive (identidade de escrita isolada do RAG) ──────────────────────

def _drive_client_escrita():
    from app.services import backup_drive_auth

    return backup_drive_auth.build_client()


def _upload_drive_sync(service, caminho: str, nome: str, folder_id: str) -> dict[str, Any]:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(
        caminho, mimetype="application/octet-stream",
        resumable=True, chunksize=8 * 1024 * 1024,
    )
    body = {"name": nome, "parents": [folder_id]}
    return service.files().create(
        body=body, media_body=media,
        fields="id,name,size", supportsAllDrives=True,
    ).execute()


def _listar_backups_sync(service, folder_id: str) -> list[dict[str, Any]]:
    """Lista arquivos da pasta com o prefixo do EJC (paginado)."""
    itens: list[dict[str, Any]] = []
    page_token: str | None = None
    q = f"'{folder_id}' in parents and trashed = false and name contains '{PREFIXO_BACKUP}'"
    while True:
        resp = service.files().list(
            q=q,
            fields="nextPageToken, files(id,name,createdTime,size)",
            pageToken=page_token,
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        itens.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return itens


def selecionar_para_rotacao(
    arquivos: list[dict[str, Any]], *, retencao_dias: int, agora: datetime | None = None,
) -> list[dict[str, Any]]:
    """Escolhe quais arquivos apagar: SÓ com prefixo do EJC e mais antigos que
    a retenção. Função pura — testável sem Drive real."""
    agora = agora or datetime.now(timezone.utc)
    corte = agora - timedelta(days=retencao_dias)
    apagar: list[dict[str, Any]] = []
    for arq in arquivos:
        nome = arq.get("name") or ""
        if not nome.startswith(PREFIXO_BACKUP):
            continue  # nunca tocar arquivos alheios na pasta
        criado_raw = (arq.get("createdTime") or "").replace("Z", "+00:00")
        try:
            criado = datetime.fromisoformat(criado_raw)
        except ValueError:
            continue  # sem data confiável → não apagar (fail-safe)
        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=timezone.utc)
        if criado < corte:
            apagar.append(arq)
    return apagar


def _rotacionar_sync(service, folder_id: str, retencao_dias: int) -> int:
    """Apaga do Drive os backups do EJC além da retenção. Retorna quantos."""
    arquivos = _listar_backups_sync(service, folder_id)
    removidos = 0
    for arq in selecionar_para_rotacao(arquivos, retencao_dias=retencao_dias):
        try:
            service.files().delete(fileId=arq["id"], supportsAllDrives=True).execute()
            removidos += 1
        except Exception as exc:  # rotação parcial não derruba o backup
            logger.warning("[Backup] rotação: falha ao apagar %s: %s", arq.get("name"), exc)
    return removidos


# ── Estado persistido (sem migration — precedente google_drive_sync_state) ───

async def _ensure_state_table(db: AsyncSession) -> None:
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS backup_drive_state (
            id SMALLINT PRIMARY KEY DEFAULT 1,
            last_run_at TIMESTAMPTZ NULL,
            last_status TEXT NULL,
            last_error TEXT NULL,
            last_origem TEXT NULL,
            duracao_segundos DOUBLE PRECISION NULL,
            detalhes JSONB NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


async def _persistir_estado(db: AsyncSession, resultado: dict[str, Any]) -> None:
    try:
        await _ensure_state_table(db)
        await db.execute(sqltext("""
            INSERT INTO backup_drive_state (
                id, last_run_at, last_status, last_error, last_origem,
                duracao_segundos, detalhes, updated_at
            ) VALUES (
                1, NOW(), :status, :erro, :origem,
                :duracao, CAST(:detalhes AS JSONB), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                last_run_at = EXCLUDED.last_run_at,
                last_status = EXCLUDED.last_status,
                last_error = EXCLUDED.last_error,
                last_origem = EXCLUDED.last_origem,
                duracao_segundos = EXCLUDED.duracao_segundos,
                detalhes = EXCLUDED.detalhes,
                updated_at = NOW()
        """), {
            "status": resultado.get("status"),
            "erro": resultado.get("erro"),
            "origem": resultado.get("origem"),
            "duracao": resultado.get("duracao_segundos"),
            "detalhes": json.dumps(resultado.get("artefatos") or []),
        })
        await db.commit()
    except Exception as exc:  # estado é telemetria — nunca derruba o backup
        logger.warning("[Backup] falha ao persistir estado: %s", exc)


async def obter_estado(db: AsyncSession) -> dict[str, Any] | None:
    await _ensure_state_table(db)
    row = (await db.execute(sqltext(
        "SELECT last_run_at, last_status, last_error, last_origem, "
        "duracao_segundos, detalhes, updated_at "
        "FROM backup_drive_state WHERE id = 1"
    ))).mappings().first()
    return dict(row) if row else None


def proximo_agendamento() -> str | None:
    try:
        from app.services.scheduler import get_scheduler
        job = get_scheduler().get_job("backup_drive")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
    except Exception:
        logger.warning(
            "[backup] não foi possível obter o próximo agendamento (segue com None)",
            exc_info=True,
        )
    return None


# ── Alerta de falha (canal de notificação existente — fail-safe) ─────────────

async def _alertar_falha(db: AsyncSession, erro: str) -> None:
    """Notifica o admin (sino + e-mail se habilitado) quando o backup falha.
    Fail-safe: indisponibilidade do canal nunca mascara o log estruturado."""
    try:
        from app.services.notification_service import notificar

        row = (await db.execute(sqltext(
            "SELECT id, email FROM users "
            "WHERE role IN ('superadmin','admin') AND is_active = true "
            "AND email IS NOT NULL LIMIT 1"
        ))).first()
        if not row:
            return
        titulo = "Backup automático FALHOU"
        msg = (
            f"O backup diário para o Google Drive falhou: {erro[:400]}. "
            "Verifique BACKUP_* no .env e os logs do backend."
        )
        await notificar(
            db, row.id, titulo, msg,
            tipo="sistema", link="/", forcar_sino=True,
            email=row.email or None,
            email_assunto="[EJC] Backup automático FALHOU",
            email_corpo=f"<h3>EJC — Backup falhou</h3><p>{msg}</p>",
        )
    except Exception as exc:
        logger.warning("[Backup] alerta de falha indisponível: %s", exc)


# ── Execução ─────────────────────────────────────────────────────────────────

async def executar_backup(
    db: AsyncSession,
    *,
    origem: str = "agendado",
    usuario_id: str | None = None,
    usuario_role: str | None = None,
) -> dict[str, Any]:
    """Executa o ciclo completo: pg_dump + tar de uploads → cifra → Drive →
    rotação → estado/auditoria/alerta. Nunca levanta exceção ao chamador —
    retorna dict com ok/status/erro (padrão sincronizar_pasta_conhecimento)."""
    global _em_execucao
    if _em_execucao:
        return {
            "ok": False, "status": "em_execucao", "origem": origem,
            "detail": "Já existe um backup em andamento.",
        }
    _em_execucao = True   # set SÍNCRONO após o teste — sem janela de TOCTOU

    try:
        inicio = time.monotonic()
        ts = datetime.now(timezone.utc)
        artefatos: list[dict[str, Any]] = []
        avisos: list[str] = []
        status, erro = "sucesso", None

        try:
            # Gates de configuração — falham cedo com mensagem acionável.
            fernet_chave = (settings.BACKUP_ENCRYPTION_KEY or "").strip()
            _fernet()  # valida presença/formato da chave
            folder_id = (settings.BACKUP_DRIVE_FOLDER_ID or "").strip()
            if not folder_id:
                raise RuntimeError(
                    "BACKUP_DRIVE_FOLDER_ID não configurado — defina o ID da "
                    "pasta do Google Drive que receberá os backups."
                )

            with tempfile.TemporaryDirectory(prefix="ejc_backup_") as tmp:
                # 1) Dump do Postgres (formato custom -Fc, já comprimido).
                dump_path = os.path.join(tmp, "db.dump")
                dump_bytes = await asyncio.to_thread(_pg_dump_para, dump_path)

                # Teto de RAM: a cifragem Fernet lê o dump INTEIRO em memória.
                # Checado ANTES de ler — acima do teto o backup falha com erro
                # claro (alerta existente dispara) sem estourar a RAM do VPS.
                limite_db = settings.BACKUP_DB_MAX_MB * 1024 * 1024
                if dump_bytes > limite_db:
                    raise RuntimeError(
                        f"Dump do banco ({dump_bytes} bytes) excede "
                        f"BACKUP_DB_MAX_MB={settings.BACKUP_DB_MAX_MB} MB — "
                        "aumente o teto no .env (garantindo RAM equivalente) "
                        "para voltar a fazer backup do banco."
                    )

                # 2) Cifra o dump (LGPD: nada sai do VPS em claro).
                dump_enc = os.path.join(tmp, "db.dump.enc")
                dump_enc_bytes = await asyncio.to_thread(
                    cifrar_arquivo, dump_path, dump_enc, fernet_chave
                )
                os.unlink(dump_path)  # não manter o dump em claro no disco
                artefatos.append({
                    "nome": _nome_artefato("db.dump", ts),
                    "caminho": dump_enc,
                    "bytes_original": dump_bytes,
                    "bytes_cifrado": dump_enc_bytes,
                })

                # 3) Uploads (tar.gz) — com teto de tamanho configurável.
                if os.path.isdir(settings.UPLOAD_DIR):
                    limite = settings.BACKUP_UPLOADS_MAX_MB * 1024 * 1024
                    tamanho = await asyncio.to_thread(
                        _tamanho_diretorio, settings.UPLOAD_DIR
                    )
                    if tamanho > limite:
                        avisos.append(
                            f"uploads ignorados: {tamanho} bytes excede "
                            f"BACKUP_UPLOADS_MAX_MB={settings.BACKUP_UPLOADS_MAX_MB}"
                        )
                    else:
                        tar_path = os.path.join(tmp, "uploads.tar.gz")
                        tar_bytes = await asyncio.to_thread(_tar_uploads_para, tar_path)
                        tar_enc = os.path.join(tmp, "uploads.tar.gz.enc")
                        tar_enc_bytes = await asyncio.to_thread(
                            cifrar_arquivo, tar_path, tar_enc, fernet_chave
                        )
                        os.unlink(tar_path)
                        artefatos.append({
                            "nome": _nome_artefato("uploads.tar.gz", ts),
                            "caminho": tar_enc,
                            "bytes_original": tar_bytes,
                            "bytes_cifrado": tar_enc_bytes,
                        })
                else:
                    avisos.append(f"UPLOAD_DIR inexistente: {settings.UPLOAD_DIR}")

                # 4) Upload ao Drive (identidade de escrita exclusiva quando configurada).
                service = await asyncio.to_thread(_drive_client_escrita)
                for art in artefatos:
                    enviado = await asyncio.to_thread(
                        _upload_drive_sync, service, art["caminho"], art["nome"], folder_id
                    )
                    art["drive_file_id"] = enviado.get("id")
                    art.pop("caminho", None)

                # 5) Rotação: mantém BACKUP_RETENCAO_DIAS dias (só prefixo EJC).
                removidos = await asyncio.to_thread(
                    _rotacionar_sync, service, folder_id, settings.BACKUP_RETENCAO_DIAS
                )

            if avisos:
                status = "parcial"
            resultado_extra: dict[str, Any] = {"rotacao_removidos": removidos}
        except Exception as exc:
            status = "erro"
            # str(exc) de subprocess/googleapiclient não carrega segredos
            # (senha vai via PGPASSWORD; a chave nunca entra em mensagens).
            erro = f"{type(exc).__name__}: {str(exc)[:500]}"
            resultado_extra = {}
            logger.error("[Backup] falha (%s): %s", origem, erro)

        duracao = round(time.monotonic() - inicio, 2)
        resultado = {
            "ok": status in {"sucesso", "parcial"},
            "status": status,
            "origem": origem,
            "erro": erro,
            "avisos": avisos,
            "artefatos": [
                {k: v for k, v in a.items() if k != "caminho"} for a in artefatos
            ],
            "duracao_segundos": duracao,
            "executado_em": ts.isoformat(),
            **resultado_extra,
        }

        # Log estruturado do resultado (sucesso e falha).
        logger.info(
            "[Backup] status=%s origem=%s duracao=%.1fs artefatos=%d erro=%s",
            status, origem, duracao, len(resultado["artefatos"]), erro or "-",
        )

        # Estado + auditoria + alerta — todos fail-safe.
        await _persistir_estado(db, resultado)
        try:
            from app.models.audit_log import criar_audit_log
            await criar_audit_log(
                db, user_id=usuario_id, user_role=usuario_role,
                acao="BACKUP", entidade="backup",
                detalhes=(
                    f"Backup {origem}: status={status}; duracao={duracao}s; "
                    f"artefatos={len(resultado['artefatos'])}; erro={erro or '-'}"
                ),
            )
            await db.commit()
        except Exception as exc:
            logger.warning("[Backup] audit log indisponível: %s", exc)

        if status == "erro":
            await _alertar_falha(db, erro or "erro desconhecido")

        return resultado
    finally:
        _em_execucao = False


async def executar_backup_background(
    *, origem: str = "manual", usuario_id: str | None = None,
    usuario_role: str | None = None,
) -> None:
    """Wrapper para asyncio.create_task: abre sessão própria (a sessão da
    request já terá sido fechada quando o backup terminar)."""
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await executar_backup(
                db, origem=origem, usuario_id=usuario_id, usuario_role=usuario_role,
            )
    except Exception as exc:  # nunca deixar exceção morrer sem log na task
        logger.error("[Backup] execução em background falhou: %s", exc)


async def job_backup_drive() -> None:
    """Job diário do APScheduler (BACKUP_HORA_UTC). Gate interno BACKUP_ENABLED
    (default False — opt-in em produção), mesmo padrão dos demais jobs."""
    if not settings.BACKUP_ENABLED:
        logger.debug("[Backup] BACKUP_ENABLED=false — job diário pulado")
        return
    await executar_backup_background(origem="agendado")
