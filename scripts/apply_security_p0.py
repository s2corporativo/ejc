"""Patch determinístico temporário para o PR de segurança P0.

O arquivo é removido pelo próprio workflow após aplicar as alterações.
"""
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


# Busca global: rejeição de CPF/CNPJ parcial usa HTTPException.
path = "backend/app/routers/search.py"
text = read(path)
old_import = "from fastapi import APIRouter, Depends, Query, Request\n"
new_import = "from fastapi import APIRouter, Depends, HTTPException, Query, Request\n"
if old_import in text:
    text = text.replace(old_import, new_import, 1)
elif new_import not in text:
    raise RuntimeError("Import do FastAPI não localizado em search.py")
write(path, text)


# CRM integral: somente perfis expressamente previstos na matriz _CLIENTES.
path = "backend/app/routers/clients.py"
text = read(path)
old_gate = '''def _req_clientes_leitura(cu: User = Depends(get_current_user)) -> User:
    """Leitura do CRM restrita à equipe interna — bloqueia cliente_externo
    (portal do cliente NÃO pode listar/consultar a carteira de clientes)."""
    if cu.role.value == "cliente_externo":
        raise HTTPException(status_code=403, detail="Sem permissão para consultar clientes")
    return cu
'''
new_gate = '''def _req_clientes_leitura(cu: User = Depends(get_current_user)) -> User:
    """Leitura integral do CRM limitada aos perfis definidos na matriz _CLIENTES."""
    if cu.role.value not in _CLIENTES:
        raise HTTPException(status_code=403, detail="Sem permissão para consultar clientes")
    return cu
'''
if old_gate in text:
    text = text.replace(old_gate, new_gate, 1)
elif new_gate not in text:
    raise RuntimeError("Gate de leitura do CRM não localizado")
write(path, text)


# Documentos: ownership também para registros avulsos e arquivos do Drive.
path = "backend/app/routers/documents.py"
text = read(path)
text = text.replace(
    "from sqlalchemy import select, func as sqlfunc\n",
    "from sqlalchemy import select, func as sqlfunc, or_\n",
    1,
)
if "from sqlalchemy import select, func as sqlfunc, or_\n" not in text:
    raise RuntimeError("Import sqlalchemy de documents.py não localizado")

# Troca os gates case-only antes de inserir o helper, evitando substituí-lo.
text = text.replace(
    "        if d.case_id:\n            await verificar_acesso_caso(db, cu, d.case_id)\n",
    "        await _verificar_acesso_documento(db, cu, d)\n",
)
text = text.replace(
    "    if d.case_id:\n        await verificar_acesso_caso(db, cu, d.case_id)\n",
    "    await _verificar_acesso_documento(db, cu, d)\n",
)

conf_marker = '''def _pode_acessar_confidencial(user: User, conf: str) -> bool:
    """Cofre: restrito+ exige perfil socio ou superior."""
    if conf in ("restrito", "confidencial", "segredo_justica"):
        return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]
    return True
'''
helpers = conf_marker + '''

async def _verificar_acesso_cliente_sem_caso(
    db: AsyncSession,
    user: User,
    client_id: str,
) -> None:
    """Autoriza cliente avulso por gestão, titular externo ou caso atribuído."""
    if is_gestao(user):
        return
    if user.role.value == "cliente_externo":
        if getattr(user, "client_id", None) == client_id:
            return
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")
    case_id = (
        await db.execute(
            select(Case.id)
            .where(
                Case.client_id == client_id,
                Case.deleted_at.is_(None),
                or_(
                    Case.advogado_responsavel_id == user.id,
                    Case.advogado_auxiliar_id == user.id,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if case_id is None:
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")


async def _verificar_acesso_documento(
    db: AsyncSession,
    user: User,
    document: Document,
) -> None:
    """Gate único para documento vinculado a caso, cliente ou apenas uploader."""
    if document.case_id:
        await verificar_acesso_caso(db, user, document.case_id)
        return
    if is_gestao(user) or document.uploaded_by == user.id:
        return
    if document.client_id:
        if (
            user.role.value == "cliente_externo"
            and document.confidencialidade.value != "normal"
        ):
            raise HTTPException(status_code=403, detail="Documento interno ou restrito")
        await _verificar_acesso_cliente_sem_caso(db, user, document.client_id)
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")
'''
if "async def _verificar_acesso_documento(" not in text:
    if conf_marker not in text:
        raise RuntimeError("Marcador de confidencialidade não localizado")
    text = text.replace(conf_marker, helpers, 1)

list_start_marker = "    # Esconder confidenciais de quem não pode ver\n"
list_end_marker = "    if case_id:\n"
new_list_scope = '''    # Cofre + ownership: documento sem case_id não é público para a equipe.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(Document.confidencialidade.in_(["normal", "interno"]))
    if cu.role.value == "cliente_externo":
        if not getattr(cu, "client_id", None):
            q = q.where(Document.id.is_(None))
        else:
            q = q.where(
                Document.client_id == cu.client_id,
                Document.confidencialidade == "normal",
            )
    elif not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        clientes_visiveis = select(Case.client_id).where(
            Case.deleted_at.is_(None),
            Case.client_id.is_not(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        q = q.where(
            or_(
                Document.case_id.in_(casos_visiveis),
                (
                    Document.case_id.is_(None)
                    & Document.client_id.in_(clientes_visiveis)
                ),
                (
                    Document.case_id.is_(None)
                    & Document.client_id.is_(None)
                    & (Document.uploaded_by == cu.id)
                ),
            )
        )
'''
if "# Cofre + ownership: documento sem case_id" not in text:
    try:
        scope_start = text.index(list_start_marker, text.index("async def listar("))
        scope_end = text.index(list_end_marker, scope_start)
    except ValueError as exc:
        raise RuntimeError("Limites do escopo da listagem documental não localizados") from exc
    text = text[:scope_start] + new_list_scope + text[scope_end:]

upload_marker = '''        if cli is None:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
'''
upload_check = "        await _verificar_acesso_cliente_sem_caso(db, cu, client_id)\n"
if upload_check not in text:
    if upload_marker not in text:
        raise RuntimeError("Validação de client_id no upload não localizada")
    text = text.replace(upload_marker, upload_marker + upload_check, 1)

drive_start_marker = "async def _gate_drive_doc(db: AsyncSession, cu: User, file_id: str):\n"
drive_end_marker = '\n\n@router.get("/drive/{file_id}/link")\n'
new_drive_gate = '''async def _gate_drive_doc(db: AsyncSession, cu: User, file_id: str):
    """Gate IDOR/LGPD para documentos do Drive, inclusive sem case_id."""
    from sqlalchemy import text as sql_text

    row = (
        await db.execute(
            sql_text(
                "SELECT id, case_id, client_id, uploaded_by, confidencialidade "
                "FROM documents WHERE drive_file_id = :fid "
                "AND deleted_at IS NULL LIMIT 1"
            ),
            {"fid": file_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Documento não encontrado")
    if row.get("case_id"):
        await verificar_acesso_caso(db, cu, row["case_id"])
    elif is_gestao(cu) or row.get("uploaded_by") == cu.id:
        pass
    elif row.get("client_id"):
        if (
            cu.role.value == "cliente_externo"
            and row.get("confidencialidade") != "normal"
        ):
            raise HTTPException(403, "Documento interno ou restrito")
        await _verificar_acesso_cliente_sem_caso(db, cu, row["client_id"])
    else:
        raise HTTPException(403, "Sem permissão para este documento")
    if not _pode_acessar_confidencial(
        cu, row.get("confidencialidade") or "normal"
    ):
        raise HTTPException(403, "Documento restrito — acesso negado")
    return row
'''
if "Gate IDOR/LGPD para documentos do Drive" not in text:
    try:
        drive_start = text.index(drive_start_marker)
        drive_end = text.index(drive_end_marker, drive_start)
    except ValueError as exc:
        raise RuntimeError("Limites do gate do Google Drive não localizados") from exc
    text = text[:drive_start] + new_drive_gate + text[drive_end:]

write(path, text)
