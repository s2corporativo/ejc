"""Unifica consumidores de preliminares, preservando contratos e rollback.

Backfill sob locks, abortando colisões/estado canônico divergente. As seis
interfaces legadas viram views atualizáveis; suas tabelas físicas passam a
espelhos de rollback, atualizados na mesma transação por triggers restritos ao espelhamento.
Downgrade retira as views/espelhos e restaura as tabelas com os dados atuais.
Nenhuma tabela de dados é apagada. Nova execução após downgrade aceita apenas
um estado equivalente: divergência exige reconciliação explícita, nunca perda
silenciosa ou sobrescrita. Migrations anteriores permanecem imutáveis.
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "171_preliminares_cutover"
down_revision = "170_djen_remove_unicidade_global"
branch_labels = None
depends_on = None

# Mapeamento congelado nesta revisão; não depende dos modelos da aplicação.
COLUNAS = {
    "raio_x_analises": (
        "id",
        "titulo",
        "potencial_cliente",
        "numero_processo",
        "area",
        "subarea",
        "rito",
        "fase",
        "tribunal",
        "orgao",
        "unidade",
        "posicao_cliente",
        "status",
        "risco_nivel",
        "prazo_urgente",
        "origem_contextual_case_id",
        "convertido_case_id",
        "dados_extraidos",
        "relatorio",
        "revisao_humana",
        "alertas_conflito",
        "custo_ia",
        "created_by",
        "retention_until",
        "converted_at",
        "archived_at",
        "discarded_at",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "raio_x_documentos": (
        "id",
        "analise_id",
        "nome_original",
        "filepath",
        "mimetype",
        "size_bytes",
        "sha256",
        "tipo_documento",
        "paginas",
        "ocr_utilizado",
        "resultado_analise",
        "uploaded_by",
        "created_at",
    ),
    "legal_chat_sessions": (
        "id",
        "titulo",
        "status",
        "favorita",
        "cliente_potencial",
        "area_sugerida",
        "advogado_responsavel_id",
        "workspace_texto",
        "workspace_versao",
        "client_id",
        "convertido_case_id",
        "converted_at",
        "frozen_at",
        "custo_ia_total",
        "created_by",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "legal_chat_messages": (
        "id",
        "session_id",
        "autor",
        "user_id",
        "modo",
        "conteudo",
        "modelo",
        "agente",
        "skills",
        "fontes",
        "citacoes",
        "alertas",
        "tokens_input",
        "tokens_output",
        "custo_estimado",
        "ai_log_id",
        "estado_versao",
        "created_at",
    ),
    "legal_chat_attachments": (
        "id",
        "session_id",
        "nome_original",
        "filepath",
        "mimetype",
        "size_bytes",
        "sha256",
        "tipo_documento",
        "ocr_utilizado",
        "resultado_analise",
        "uploaded_by",
        "created_at",
    ),
    "legal_chat_state_versions": (
        "id",
        "session_id",
        "versao",
        "resumo",
        "estado",
        "origem",
        "created_by",
        "created_at",
    ),
}
FONTES = (
    ("raio_x_analises", "preliminares", "raio_x", {}),
    (
        "legal_chat_sessions",
        "preliminares",
        "sala_juridica",
        {
            "cliente_potencial": "potencial_cliente",
            "area_sugerida": "area",
        },
    ),
    ("raio_x_documentos", "preliminar_documentos", "raio_x", {"analise_id": "preliminar_id"}),
    ("legal_chat_attachments", "preliminar_documentos", "sala_juridica", {"session_id": "preliminar_id"}),
    ("legal_chat_messages", "preliminar_mensagens", "sala_juridica", {"session_id": "preliminar_id"}),
    (
        "legal_chat_state_versions",
        "preliminar_estados",
        "sala_juridica",
        {
            "session_id": "preliminar_id",
            "origem": "autoria",
        },
    ),
)
CANONICAS = tuple(dict.fromkeys(f[1] for f in FONTES))


def _sql(statement):
    return op.get_bind().execute(sa.text(statement))


def _contexto():
    conn = op.get_bind()
    schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()
    quote = conn.dialect.identifier_preparer.quote_identifier
    return lambda name: f"{quote(schema)}.{quote(name)}"


def _pares(fonte):
    antiga, _, _, renomes = fonte
    return [(c, renomes.get(c, c)) for c in COLUNAS[antiga]]


def _abortar_se(query):
    # Mensagem deliberadamente sem IDs, títulos ou conteúdo de documentos.
    _sql(f"""DO $$ BEGIN
        IF EXISTS ({query}) THEN
            RAISE EXCEPTION 'Preliminares: colisão ou divergência; reconciliação necessária';
        END IF;
    END $$""")


def _validar(q):
    inspector = sa.inspect(op.get_bind())
    for name in [f[0] for f in FONTES] + list(CANONICAS):
        if (
            op.get_bind()
            .execute(
                sa.text("SELECT relrowsecurity OR relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:name)"),
                {"name": q(name)},
            )
            .scalar_one()
        ):
            raise RuntimeError("Preliminares: RLS existente exige preservação explícita antes do cutover")
    for antiga, nova, _, renomes in FONTES:
        if op.get_bind().execute(sa.text("""
            SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass(:name) AND NOT tgisinternal)
                OR EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class=to_regclass(:name))
        """), {"name": q(antiga)}).scalar_one():
            raise RuntimeError("Preliminares: trigger/regra legada exige revisão antes do cutover")
        atual = {c["name"] for c in inspector.get_columns(antiga)}
        if atual != set(COLUNAS[antiga]):
            raise RuntimeError("Preliminares: schema legado divergente; reconciliação necessária")
        canon = {c["name"] for c in inspector.get_columns(nova)}
        if not {renomes.get(c, c) for c in atual} <= canon:
            raise RuntimeError("Preliminares: schema canônico incompatível")
    for nova in CANONICAS:
        fontes = [f for f in FONTES if f[1] == nova]
        ids = " UNION ALL ".join(f"SELECT id FROM {q(f[0])}" for f in fontes)
        _abortar_se(f"SELECT id FROM ({ids}) ids GROUP BY id HAVING count(*) > 1")
        _abortar_se(f"SELECT c.id FROM {q(nova)} c WHERE NOT EXISTS (SELECT 1 FROM ({ids}) ids WHERE ids.id=c.id)")
    for fonte in FONTES:
        antiga, nova, origem, _ = fonte
        differences = " OR ".join(f"c.{canonical} IS DISTINCT FROM l.{old}" for old, canonical in _pares(fonte))
        if nova == "preliminares":
            differences += f" OR c.origem IS DISTINCT FROM '{origem}'"
        _abortar_se(f"SELECT 1 FROM {q(antiga)} l JOIN {q(nova)} c ON c.id=l.id WHERE {differences}")


def _backfill(q):
    for fonte in FONTES:
        antiga, nova, origem, _ = fonte
        columns = [canonical for _, canonical in _pares(fonte)]
        values = [old for old, _ in _pares(fonte)]
        if nova == "preliminares":
            columns.append("origem")
            values.append(f"'{origem}'")
        # Os conflitos já foram verificados integralmente, sob os mesmos locks.
        _sql(
            f"INSERT INTO {q(nova)} ({', '.join(columns)}) SELECT {', '.join(values)} FROM {q(antiga)} ON CONFLICT (id) DO NOTHING"
        )


def _upsert(q, fonte):
    antiga = fonte[0]
    pairs = _pares(fonte)
    columns = ", ".join(old for old, _ in pairs)
    values = ", ".join(f"NEW.{canonical}" for _, canonical in pairs)
    updates = ", ".join(f"{old}=EXCLUDED.{old}" for old, _ in pairs if old != "id")
    return f'INSERT INTO {q(antiga + "_legado_171")} ({columns}) VALUES ({values}) ON CONFLICT (id) DO UPDATE SET {updates};'


def _espelhos(q):
    # A operação autorizada na base/view espelha a mesma linha no rollback,
    # sem exigir grants auxiliares nem permitir execução avulsa da função.
    for nova in CANONICAS:
        relation = q(nova).replace("'", "''")
        fontes = [f for f in FONTES if f[1] == nova]
        deletes = " ".join(f'DELETE FROM {q(f[0] + "_legado_171")} WHERE id=OLD.id;' for f in fontes)
        if nova == "preliminares":
            origem = "origem_atual := NEW.origem; IF TG_OP='UPDATE' AND OLD.origem IS DISTINCT FROM NEW.origem THEN RAISE EXCEPTION 'Origem de preliminar imutável'; END IF;"
        else:
            origem = f'SELECT origem INTO origem_atual FROM {q("preliminares")} WHERE id=NEW.preliminar_id;'
        writes = []
        for fonte in fontes:
            old, _, source, _ = fonte
            if len(fontes) == 1:
                fallback = "RAISE EXCEPTION 'Origem incompatível para filho de preliminar';"
            else:
                fallback = f'DELETE FROM {q(old + "_legado_171")} WHERE id=NEW.id;' if nova != "preliminares" else ""
            writes.append(f"IF origem_atual='{source}' THEN {_upsert(q, fonte)} ELSE {fallback} END IF;")
        name = f"espelhar_171_{nova}"
        _sql(f"""CREATE FUNCTION {q(name)}() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE origem_atual pg_catalog.text;
            BEGIN
                IF TG_RELID <> '{relation}'::pg_catalog.regclass THEN
                    RAISE EXCEPTION 'Espelho restrito à tabela canônica';
                END IF;
                IF TG_OP='TRUNCATE' THEN
                    RAISE EXCEPTION 'TRUNCATE proibido durante o espelhamento de rollback';
                END IF;
                IF TG_OP='UPDATE' AND OLD.id IS DISTINCT FROM NEW.id THEN
                    RAISE EXCEPTION 'ID de preliminar imutável';
                END IF;
                IF TG_OP='DELETE' THEN {deletes} RETURN NULL; END IF;
                {origem}
                {' '.join(writes)}
                RETURN NULL;
            END $$""")
        # Trigger não é API de escrita: somente seu owner pode registrá-lo,
        # e TG_RELID barra uso em outra tabela. Corpo todo schema-qualified.
        grants = (
            op.get_bind()
            .execute(
                sa.text("""
            SELECT coalesce(r.rolname, 'PUBLIC') AS role
            FROM pg_proc p CROSS JOIN LATERAL
                 aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
            LEFT JOIN pg_roles r ON r.oid=a.grantee
            WHERE p.oid=to_regprocedure(:function) AND a.grantee<>p.proowner
        """),
                {"function": q(name) + "()"},
            )
            .scalars()
            .all()
        )
        quote = op.get_bind().dialect.identifier_preparer.quote_identifier
        for role in set(grants):
            target = "PUBLIC" if role == "PUBLIC" else quote(role)
            _sql(f"REVOKE ALL PRIVILEGES ON FUNCTION {q(name)}() FROM {target}")
        _sql(
            f"CREATE TRIGGER {name} AFTER INSERT OR UPDATE OR DELETE ON {q(nova)} FOR EACH ROW EXECUTE FUNCTION {q(name)}()"
        )
        _sql(f"CREATE TRIGGER impedir_truncate_171_{nova} BEFORE TRUNCATE ON {q(nova)} FOR EACH STATEMENT EXECUTE FUNCTION {q(name)}()")


def _acl(q, name):
    conn = op.get_bind()
    owner = conn.execute(
        sa.text("SELECT r.rolname FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE c.oid=to_regclass(:name)"),
        {"name": q(name)},
    ).scalar_one()
    grants = conn.execute(
        sa.text("""
        SELECT coalesce(r.rolname, 'PUBLIC') AS role, a.privilege_type,
               a.is_grantable, NULL::text AS column_name, grantor.rolname AS grantor_role
        FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
        LEFT JOIN pg_roles r ON r.oid=a.grantee
        JOIN pg_roles grantor ON grantor.oid=a.grantor WHERE c.oid=to_regclass(:name)
        UNION ALL
        SELECT coalesce(r.rolname, 'PUBLIC'), a.privilege_type,
               a.is_grantable, att.attname, grantor.rolname
        FROM pg_attribute att CROSS JOIN LATERAL aclexplode(att.attacl) a
        LEFT JOIN pg_roles r ON r.oid=a.grantee
        JOIN pg_roles grantor ON grantor.oid=a.grantor
        WHERE att.attrelid=to_regclass(:name) AND att.attnum>0
    """),
        {"name": q(name)},
    ).all()
    return owner, grants


def _revogar_acl(q, name):
    quote = op.get_bind().dialect.identifier_preparer.quote_identifier
    _, defaults = _acl(q, name)
    for role in {g.role for g in defaults}:
        target = "PUBLIC" if role == "PUBLIC" else quote(role)
        _sql(f"REVOKE ALL PRIVILEGES ON {q(name)} FROM {target} CASCADE")
    for role, _, _, column, _ in defaults:
        if column:
            target = "PUBLIC" if role == "PUBLIC" else quote(role)
            _sql(f"REVOKE ALL PRIVILEGES ({quote(column)}) ON {q(name)} FROM {target} CASCADE")


def _restaurar_acl(q, name, acl, *, view=True):
    owner, grants = acl
    quote = op.get_bind().dialect.identifier_preparer.quote_identifier
    kind = "VIEW" if view else "TABLE"
    _sql(f"ALTER {kind} {q(name)} OWNER TO {quote(owner)}")
    _revogar_acl(q, name)
    executor = op.get_bind().execute(sa.text("SELECT current_user")).scalar_one()
    pending = [g for g in grants if not view or g[1] in {"SELECT", "INSERT", "UPDATE", "DELETE"}]
    while pending:
        progress = False
        for grant in list(pending):
            role, privilege, grantable, column, grantor = grant
            params = {"role": grantor, "table": q(name), "privilege": privilege + " WITH GRANT OPTION"}
            if column:
                params["column"] = column
                check = "SELECT has_column_privilege(:role,:table,:column,:privilege)"
            else:
                check = "SELECT has_table_privilege(:role,:table,:privilege)"
            if not op.get_bind().execute(sa.text(check), params).scalar_one():
                continue
            target = "PUBLIC" if role == "PUBLIC" else quote(role)
            cols = f" ({quote(column)})" if column else ""
            option = " WITH GRANT OPTION" if grantable else ""
            # O executor autorizado a trocar o owner concede em seu nome,
            # sem exigir USAGE de schema que o owner antigo pode não possuir.
            # Grants delegados precisam do papel original para manter a cadeia.
            if grantor != owner:
                _sql(f"SET LOCAL ROLE {quote(grantor)}")
            _sql(f"GRANT {privilege}{cols} ON {q(name)} TO {target}{option}")
            if grantor != owner:
                _sql(f"SET LOCAL ROLE {quote(executor)}")
            pending.remove(grant)
            progress = True
        if not progress:
            raise RuntimeError("Preliminares: cadeia de ACL exige reconciliação")


def _isolar_espelhos(q, acls):
    # O executor de migrations é principal confiável; nunca executar com
    # credencial compartilhada com consumidores SQL não confiáveis.
    owner = op.get_bind().execute(sa.text("SELECT current_user")).scalar_one()
    quote = op.get_bind().dialect.identifier_preparer.quote_identifier
    for antiga, _, _, _ in FONTES:
        name = antiga + "_legado_171"
        _sql(f"ALTER TABLE {q(name)} OWNER TO {quote(owner)}")
        _revogar_acl(q, name)
        _sql(f"GRANT ALL PRIVILEGES ON {q(name)} TO {quote(owner)}")
    # Metadados de ACL, sem conteúdo de casos; conservados até o downgrade.
    metadata = json.dumps({n: [o, [list(g) for g in grants]] for n, (o, grants) in acls.items()})
    literal = op.get_bind().execute(sa.text("SELECT quote_literal(:value)"), {"value": metadata}).scalar_one()
    _sql(f"COMMENT ON FUNCTION {q('espelhar_171_preliminares')}() IS {literal}")


def _projecao_legada(q, fonte, *, incluir_origem=False):
    antiga, nova, origem, _ = fonte
    columns = [f"{canonical} AS {old}" for old, canonical in _pares(fonte)]
    if nova == "preliminares":
        if incluir_origem:
            columns.append("origem")
        predicate = f"origem='{origem}'"
    else:
        predicate = f"EXISTS (SELECT 1 FROM {q('preliminares')} p WHERE p.id={q(nova)}.preliminar_id AND p.origem='{origem}')"
    return f'SELECT {", ".join(columns)} FROM {q(nova)} WHERE {predicate}'


def _validar_espelhos(q):
    # Nunca executar a definição de view alterável por um owner legado.
    for fonte in FONTES:
        antiga = fonte[0]
        columns = ", ".join(COLUNAS[antiga])
        left = _projecao_legada(q, fonte)
        right = f"SELECT {columns} FROM {q(antiga + '_legado_171')}"
        _abortar_se(f"({left} EXCEPT ALL {right}) UNION ALL ({right} EXCEPT ALL {left})")


def _views(q, defaults, acls):
    # Owner com acesso canônico + ACL/projeção legadas: leitor da view não
    # ganha acesso direto à base. security_barrier preserva o filtro de origem.
    # RLS preexistente aborta em _validar, antes de qualquer transformação.
    for fonte in FONTES:
        antiga, nova, origem, _ = fonte
        _sql(
            f'CREATE VIEW {q(antiga)} WITH (security_barrier=true) AS {_projecao_legada(q, fonte, incluir_origem=True)} WITH LOCAL CHECK OPTION'
        )
        for col, default in defaults[antiga].items():
            _sql(f"ALTER VIEW {q(antiga)} ALTER COLUMN {col} SET DEFAULT {default}")
        if nova == "preliminares":
            _sql(f"ALTER VIEW {q(antiga)} ALTER COLUMN origem SET DEFAULT '{origem}'")
        _restaurar_acl(q, antiga, acls[antiga])


def upgrade():
    q = _contexto()
    names = [f[0] for f in FONTES] + list(CANONICAS)
    _sql("SET LOCAL lock_timeout='5s'")
    _sql(f'LOCK TABLE {", ".join(q(n) for n in names)} IN ACCESS EXCLUSIVE MODE')
    _validar(q)
    inspector = sa.inspect(op.get_bind())
    defaults = {
        name: {c["name"]: c["default"] for c in inspector.get_columns(name) if c["default"] is not None}
        for name in names[: len(FONTES)]
    }
    acls = {name: _acl(q, name) for name in names[: len(FONTES)]}
    for antiga, nova, _, _ in FONTES:
        owner = acls[antiga][0]
        dependencies = {nova} if nova == "preliminares" else {nova, "preliminares"}
        for target in dependencies:
            required = {"SELECT"}
            if target == nova:
                required |= {g.privilege_type for g in acls[antiga][1]
                             if g.privilege_type in {"INSERT", "UPDATE", "DELETE"}}
            for privilege in required:
                if (
                    not op.get_bind()
                    .execute(
                        sa.text("SELECT has_table_privilege(:owner, :table, :privilege)"),
                        {"owner": owner, "table": q(target), "privilege": privilege},
                    )
                    .scalar_one()
                ):
                    raise RuntimeError("Preliminares: owner legado sem acesso canônico; reconciliação de ACL necessária")
    _backfill(q)
    for name in names[: len(FONTES)]:
        _sql(f"ALTER TABLE {q(name)} RENAME TO {name}_legado_171")
    _espelhos(q)
    _isolar_espelhos(q, acls)
    _views(q, defaults, acls)


def downgrade():
    q = _contexto()
    _sql("SET LOCAL lock_timeout='5s'")
    # Mesmo lock usado pelo upgrade; dados novos já estão nos espelhos.
    names = list(CANONICAS) + [f[0] + "_legado_171" for f in FONTES]
    _sql(f'LOCK TABLE {", ".join(q(n) for n in names)} IN ACCESS EXCLUSIVE MODE')
    _validar_espelhos(q)
    metadata = op.get_bind().execute(sa.text("SELECT obj_description(to_regprocedure(:function), 'pg_proc')"),
                                    {"function": q('espelhar_171_preliminares') + "()"}).scalar_one()
    acls = json.loads(metadata)
    if set(acls) != {f[0] for f in FONTES}:
        raise RuntimeError("Preliminares: metadados de rollback incompatíveis")
    for antiga, _, _, _ in reversed(FONTES):
        _sql(f"DROP VIEW {q(antiga)}")
    for nova in CANONICAS:
        name = f"espelhar_171_{nova}"
        _sql(f"DROP TRIGGER {name} ON {q(nova)}")
        _sql(f"DROP TRIGGER impedir_truncate_171_{nova} ON {q(nova)}")
        _sql(f"DROP FUNCTION {q(name)}()")
    for antiga, _, _, _ in FONTES:
        _sql(f'ALTER TABLE {q(antiga + "_legado_171")} RENAME TO {antiga}')
        _restaurar_acl(q, antiga, acls[antiga], view=False)
