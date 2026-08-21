from __future__ import annotations

from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: esperado 1 match, encontrados {count}: {old[:140]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, repl: str) -> None:
    text = read(path)
    new, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: regex esperava 1 match, encontrou {count}: {pattern[:140]!r}")
    write(path, new)


# Model: vínculo persistente + marcador imutável do kit.
replace_once(
    "backend/app/models/legal_doc.py",
    '    case_id    = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)\n    created_by = Column(String(36), nullable=True)\n',
    '    case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)\n'
    '    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)\n'
    '    # Identidade estável do kit de admissão; título/nome é só apresentação.\n'
    '    client_admission_kind = Column(String(40), nullable=True)\n'
    '    created_by = Column(String(36), nullable=True)\n',
)

# Router de clientes: endpoints privados, ownership e quotas distintas.
replace_once(
    "backend/app/routers/clients.py",
    'from app.core.security import get_current_user, require_roles\n',
    'from app.core.security import get_current_user, require_roles, requer_advogado\n',
)
replace_once(
    "backend/app/routers/clients.py",
    'from app.models.audit_log import criar_audit_log\n',
    'from app.models.audit_log import criar_audit_log\n'
    'from app.services.geracao_documental_cliente import listar_pecas_cliente\n',
)
replace_once(
    "backend/app/routers/clients.py",
    '''    await db.refresh(c)
    return c


@router.get("/{client_id}", response_model=ClientResponse)
''',
    '''    await db.refresh(c)
    return c


class GerarDocsClienteIn(BaseModel):
    tipo_poderes: str = "ad_judicia"
    permite_substabelecimento: bool = True
    poderes_especiais: Optional[str] = None
    forcar_novo: bool = False


@router.post(
    "/{client_id}/gerar-documentos",
    status_code=201,
    dependencies=[Depends(rate_limit("kit-documental", 5))],
)
async def gerar_documentos_cliente(
    client_id: str,
    payload: Optional[GerarDocsClienteIn] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    """Gera contrato + procuração como rascunhos vinculados ao cliente."""
    requer_advogado(cu)
    c = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not c or not await _pode_ver_cliente(cu, c, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    p = payload or GerarDocsClienteIn()
    from app.services.geracao_documental_cliente import gerar_documentos_cliente as _gerar
    return await _gerar(
        db,
        c,
        cu,
        tipo_poderes=p.tipo_poderes,
        permite_substabelecimento=p.permite_substabelecimento,
        poderes_especiais=p.poderes_especiais,
        forcar_novo=p.forcar_novo,
    )


@router.get(
    "/{client_id}/pecas-geradas",
    dependencies=[Depends(rate_limit("kit-documental-list", 30))],
)
async def listar_pecas_geradas(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    """Lista documentos de admissão da carteira autorizada."""
    requer_advogado(cu)
    c = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not c or not await _pode_ver_cliente(cu, c, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return await listar_pecas_cliente(db, c)


@router.get("/{client_id}", response_model=ClientResponse)
''',
)

# LegalDocs: client_id é segundo domínio de ownership, além de case_id.
replace_once(
    "backend/app/routers/legal_docs.py",
    'from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks\n',
    'from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request\n',
)
replace_once(
    "backend/app/routers/legal_docs.py",
    'from app.core.ownership import verificar_acesso_caso, is_gestao\n',
    'from app.core.ownership import verificar_acesso_caso, is_gestao\n'
    'from app.core.client_ownership import (\n'
    '    cliente_id_visivel,\n'
    '    ids_clientes_visiveis,\n'
    '    visao_total_clientes,\n'
    ')\n',
)
replace_once(
    "backend/app/routers/legal_docs.py",
    'router = APIRouter(prefix="/legal-docs", tags=["Peças Jurídicas"])\n',
    '''async def _enforce_client_legal_doc_scope(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
) -> None:
    """Gate transversal de peça avulsa por client_id; usa 404 anti-enumeração."""
    doc_id = request.path_params.get("doc_id")
    if not doc_id:
        return
    row = (
        await db.execute(
            select(LegalDoc.client_id).where(
                LegalDoc.id == doc_id,
                LegalDoc.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return
    client_id = row[0]
    if client_id and not await cliente_id_visivel(db, cu, client_id):
        raise HTTPException(status_code=404, detail="Peça não encontrada")


router = APIRouter(
    prefix="/legal-docs",
    tags=["Peças Jurídicas"],
    dependencies=[Depends(_enforce_client_legal_doc_scope)],
)
''',
)
regex_once(
    "backend/app/routers/legal_docs.py",
    r'    # Ownership por caso \(IDOR\): não-gestão só vê peças dos seus casos\n'
    r'    # \(responsável/auxiliar/sem-dono\) ou sem caso vinculado\.\n'
    r'    if not is_gestao\(cu\):\n'
    r'        casos_visiveis = select\(Case\.id\)\.where\(\n'
    r'.*?'
    r'        q = q\.where\(LegalDoc\.case_id\.is_\(None\) \| LegalDoc\.case_id\.in_\(casos_visiveis\)\)\n',
    '''    # Ownership por caso + cliente. Peça avulsa legada sem client_id
    # preserva a visibilidade histórica; peça vinculada segue a carteira do CRM.
    if not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            (
                (Case.advogado_responsavel_id == cu.id)
                | (Case.advogado_auxiliar_id == cu.id)
                | (Case.advogado_responsavel_id.is_(None) & Case.advogado_auxiliar_id.is_(None))
            ),
        )
        visiveis = [
            LegalDoc.case_id.in_(casos_visiveis),
            and_(LegalDoc.case_id.is_(None), LegalDoc.client_id.is_(None)),
        ]
        if visao_total_clientes(cu):
            visiveis.append(
                and_(LegalDoc.case_id.is_(None), LegalDoc.client_id.is_not(None))
            )
        else:
            visiveis.append(
                and_(
                    LegalDoc.case_id.is_(None),
                    LegalDoc.client_id.in_(ids_clientes_visiveis(cu)),
                )
            )
        q = q.where(or_(*visiveis))
''',
)
replace_once(
    "backend/app/routers/legal_docs.py",
    '    escopo_cli = None\n    if d.case_id:\n',
    '    escopo_cli = getattr(d, "client_id", None)\n    if d.case_id:\n',
)

# RAG: documento avulso vinculado não pode cair em escopo global.
replace_once(
    "backend/app/services/case_intel.py",
    '            client_id = None\n            nomes_proteger: list[str] = []\n',
    '            client_id = getattr(d, "client_id", None)\n            nomes_proteger: list[str] = []\n',
)
replace_once(
    "backend/app/services/case_intel.py",
    '''                                if n:
                                    nomes_proteger.append(n)

            # LGPD — NUNCA indexar PII na RAG. Mascara também nomes próprios
''',
    '''                                if n:
                                    nomes_proteger.append(n)
            elif client_id:
                cli = await db.get(Client, client_id)
                if cli:
                    for n in (
                        getattr(cli, "nome", None),
                        getattr(cli, "razao_social", None),
                        getattr(cli, "nome_fantasia", None),
                    ):
                        if n:
                            nomes_proteger.append(n)

            # LGPD — NUNCA indexar PII na RAG. Mascara também nomes próprios
''',
)

# Alembic: reserva e testes de head.
reservations = "backend/alembic/MIGRATION_RESERVATIONS.md"
text = read(reservations)
old146 = '| 146_case_sigilo_reforcado | 145_drop_orphan_db_only_columns | claude/auditoria-ia-juridica-c2tbf2 | [#1195](https://github.com/s2corporativo/ejc/pull/1195) | Claude Code | Em PR |'
if old146 in text:
    text = text.replace(
        old146,
        '| 146_case_sigilo_reforcado | 145_drop_orphan_db_only_columns | main | [#1195](https://github.com/s2corporativo/ejc/pull/1195) | Claude Code | Mesclada |',
        1,
    )
if "| 147_legal_doc_client_id |" not in text:
    lines = text.splitlines()
    idx = next((i for i, line in enumerate(lines) if line.startswith("| 146_case_sigilo_reforcado |")), None)
    if idx is None:
        raise SystemExit("MIGRATION_RESERVATIONS: linha 146 não encontrada")
    lines.insert(
        idx + 1,
        "| 147_legal_doc_client_id | 146_case_sigilo_reforcado | fix/1199-client-document-isolation-v4 | [#1231](https://github.com/s2corporativo/ejc/pull/1231) | ChatGPT | Em PR | Issue #1199: `LegalDoc.client_id` + `client_admission_kind`, aditiva, sem backfill; downgrade protegido após uso. |",
    )
    text = "\n".join(lines) + "\n"
write(reservations, text)

replace_once(
    "backend/tests/test_alembic_single_head.py",
    'HEAD_REVISION = "146_case_sigilo_reforcado"\n',
    'HEAD_REVISION = "147_legal_doc_client_id"\n',
)
p = "backend/tests/test_alembic_single_head.py"
text = read(p)
if "test_legal_doc_client_id_encadeia_apos_sigilo_reforcado" not in text:
    text += '''\n\ndef test_legal_doc_client_id_encadeia_apos_sigilo_reforcado():
    revision = _script_directory().get_revision("147_legal_doc_client_id")
    assert revision.down_revision == "146_case_sigilo_reforcado"
'''
write(p, text)
replace_once(
    "backend/tests/test_schema_dr_parity.py",
    'HEAD_REVISION = "146_case_sigilo_reforcado"\n',
    'HEAD_REVISION = "147_legal_doc_client_id"\n',
)
replace_once(
    "backend/tests/test_preliminares_fundacao_schema_140.py",
    '    assert script.get_heads() == ["146_case_sigilo_reforcado"]\n',
    '    assert script.get_heads() == ["147_legal_doc_client_id"]\n',
)
replace_once(
    "backend/tests/test_preliminares_fundacao_schema_140.py",
    '''    assert (
        script.get_revision("146_case_sigilo_reforcado").down_revision
        == "145_drop_orphan_db_only_columns"
    )
''',
    '''    assert (
        script.get_revision("146_case_sigilo_reforcado").down_revision
        == "145_drop_orphan_db_only_columns"
    )
    assert (
        script.get_revision("147_legal_doc_client_id").down_revision
        == "146_case_sigilo_reforcado"
    )
''',
)
replace_once(
    "backend/tests/test_rotas_registro_explicito.py",
    '    ("/api/signatures/{sig_id}/documento", "GET"),\n',
    '    ("/api/signatures/{sig_id}/documento", "GET"),\n'
    '    # #1199: documentos de admissão privados e vinculados ao cliente.\n'
    '    ("/api/clients/{client_id}/pecas-geradas", "GET"),\n'
    '    ("/api/clients/{client_id}/gerar-documentos", "POST"),\n',
)

# Frontend: opt-in explícito no cadastro.
replace_once(
    "frontend/src/pages/Clientes.tsx",
    '  const [salvando, setSalvando] = useState(false);\n  const [erro, setErro] = useState(false);\n',
    '  const [salvando, setSalvando] = useState(false);\n'
    '  const [gerarDocsNoCadastro, setGerarDocsNoCadastro] = useState(false);\n'
    '  const [erro, setErro] = useState(false);\n',
)
replace_once(
    "frontend/src/pages/Clientes.tsx",
    '''    try {
      await api.post("/clients/", form);
      setModal(false);
      setForm({ tipo: "PF", cidade: "Betim", estado: "MG" });
      setConflito(null);
      load();
''',
    '''    try {
      const { data: clienteCriado } = await api.post("/clients/", form);
      if (gerarDocsNoCadastro) {
        try {
          await api.post(`/clients/${clienteCriado.id}/gerar-documentos`, {});
          toast.success("Cliente salvo e minutas geradas como rascunho");
        } catch (docsErr: any) {
          const detail = docsErr.response?.data?.detail;
          toast.warning(
            `Cliente salvo, mas as minutas não foram geradas: ${typeof detail === "string" ? detail : "verifique sua permissão e tente pelo Dossiê"}`,
          );
        }
      }
      setModal(false);
      setForm({ tipo: "PF", cidade: "Betim", estado: "MG" });
      setGerarDocsNoCadastro(false);
      setConflito(null);
      load();
''',
)
replace_once(
    "frontend/src/pages/Clientes.tsx",
    '''        onClose={() => {
          setModal(false);
          setConflito(null);
        }}
''',
    '''        onClose={() => {
          setModal(false);
          setGerarDocsNoCadastro(false);
          setConflito(null);
        }}
''',
)
replace_once(
    "frontend/src/pages/Clientes.tsx",
    '''        </div>

        {conflito && conflito.conflito && conflito.nivel !== "nenhum" && (
''',
    '''        </div>

        <label className="mt-4 flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={gerarDocsNoCadastro}
            onChange={(e) => setGerarDocsNoCadastro(e.target.checked)}
          />
          <span>
            <span className="font-medium text-navy">Gerar contrato e procuração após salvar</span>
            <span className="block text-xs text-slate-500 mt-0.5">
              As minutas são templates determinísticos, nascem como rascunho e exigem validação e revisão profissional antes do uso.
            </span>
          </span>
        </label>

        {conflito && conflito.conflito && conflito.nivel !== "nenhum" && (
''',
)

# Dossiê: geração/listagem/download; aprovação continua somente no módulo Peças.
replace_once(
    "frontend/src/pages/DossieCliente.tsx",
    'interface DossieData {\n',
    '''interface PecaAdmissao {
  id: string;
  titulo: string;
  tipo: string;
  status: string;
  admission_kind?: string | null;
  created_at?: string | null;
}

interface DossieData {
''',
)
replace_once(
    "frontend/src/pages/DossieCliente.tsx",
    '''  const [abaAtiva, setAbaAtiva] = useState(
    requestedTab && validTabs.includes(requestedTab) ? requestedTab : "resumo",
  );
''',
    '''  const [abaAtiva, setAbaAtiva] = useState(
    requestedTab && validTabs.includes(requestedTab) ? requestedTab : "resumo",
  );
  const [pecasAdmissao, setPecasAdmissao] = useState<PecaAdmissao[]>([]);
  const [pecasAdmissaoErro, setPecasAdmissaoErro] = useState("");
  const [pecasAdmissaoLoading, setPecasAdmissaoLoading] = useState(false);
  const [gerandoAdmissao, setGerandoAdmissao] = useState(false);
''',
)
replace_once(
    "frontend/src/pages/DossieCliente.tsx",
    '''  useEffect(() => {
    carregarDossie();
  }, [carregarDossie]);

  const [editOpen, setEditOpen] = useState(false);
''',
    '''  useEffect(() => {
    carregarDossie();
  }, [carregarDossie]);

  const carregarPecasAdmissao = useCallback(async () => {
    if (!clientId) return;
    setPecasAdmissaoLoading(true);
    setPecasAdmissaoErro("");
    try {
      const r = await api.get(`/clients/${clientId}/pecas-geradas`);
      setPecasAdmissao(Array.isArray(r.data) ? r.data : []);
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setPecasAdmissaoErro(
        typeof detail === "string"
          ? detail
          : "Não foi possível carregar os documentos de admissão.",
      );
    } finally {
      setPecasAdmissaoLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    if (abaAtiva === "documentos") carregarPecasAdmissao();
  }, [abaAtiva, carregarPecasAdmissao]);

  const [editOpen, setEditOpen] = useState(false);
''',
)
replace_once(
    "frontend/src/pages/DossieCliente.tsx",
    '  const [ultimaInteracao, setUltimaInteracao] = useState<string | null>(null);\n',
    '''  const baixarPecaAdmissao = async (docId: string, titulo: string) => {
    try {
      const r = await api.get(`/legal-docs/${docId}/pdf-minuta`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${titulo || "minuta"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Não foi possível baixar a minuta");
    }
  };

  const gerarPecasAdmissao = async (forcarNovo = false) => {
    if (!clientId) return;
    setGerandoAdmissao(true);
    try {
      await api.post(`/clients/${clientId}/gerar-documentos`, {
        forcar_novo: forcarNovo,
      });
      toast.success(
        forcarNovo ? "Novas minutas geradas como rascunho" : "Minutas geradas como rascunho",
      );
      await carregarPecasAdmissao();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      toast.error(
        typeof detail === "string" ? detail : "Não foi possível gerar as minutas",
      );
    } finally {
      setGerandoAdmissao(false);
    }
  };

  const [ultimaInteracao, setUltimaInteracao] = useState<string | null>(null);
''',
)
regex_once(
    "frontend/src/pages/DossieCliente.tsx",
    r'      \{abaAtiva === "documentos" && \(\n'
    r'        <div className="card overflow-hidden animate-fade-in">.*?'
    r'      \)\}\n\n      \{abaAtiva === "ia_cliente"',
    '''      {abaAtiva === "documentos" && (
        <div className="space-y-4 animate-fade-in">
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-bronze-pale flex items-center justify-between gap-3">
              <div>
                <p className="eyebrow flex items-center gap-2">
                  <FileText className="w-3 h-3" /> Documentos de Admissão
                </p>
                <p className="text-[11px] text-slate-400 mt-1">
                  Templates determinísticos; nenhuma minuta é aprovada automaticamente.
                </p>
              </div>
              <button
                type="button"
                disabled={gerandoAdmissao}
                onClick={() => gerarPecasAdmissao(pecasAdmissao.length > 0)}
                className="btn-secondary text-xs whitespace-nowrap"
              >
                {gerandoAdmissao
                  ? "Gerando..."
                  : pecasAdmissao.length > 0
                    ? "Gerar nova versão"
                    : "Gerar minutas"}
              </button>
            </div>
            {pecasAdmissaoErro && (
              <div className="m-4 rounded-lg border border-warn-200 bg-warn-50 p-3 text-sm text-warn-700">
                <p>{pecasAdmissaoErro}</p>
                <button type="button" onClick={carregarPecasAdmissao} className="mt-1 underline font-medium">
                  Tentar novamente
                </button>
              </div>
            )}
            {pecasAdmissaoLoading ? (
              <div className="p-5 flex justify-center"><Spinner /></div>
            ) : pecasAdmissao.length === 0 && !pecasAdmissaoErro ? (
              <p className="p-4 text-sm text-slate-500">
                Nenhum contrato ou procuração de admissão foi gerado para este cliente.
              </p>
            ) : (
              <div className="divide-y divide-bronze-pale/50">
                {pecasAdmissao.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 px-4 py-3 group">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-navy-900 font-medium truncate">{p.titulo}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        {p.tipo === "contrato" ? "Contrato de honorários" : "Procuração"}
                        {p.created_at ? ` · ${new Date(p.created_at).toLocaleDateString("pt-BR")}` : ""}
                      </p>
                    </div>
                    <StatusBadge value={p.status} />
                    <Link to="/pecas" title="Abrir fluxo canônico de revisão" className="text-xs font-medium text-bronze hover:underline whitespace-nowrap">
                      Revisar em Peças
                    </Link>
                    <button type="button" onClick={() => baixarPecaAdmissao(p.id, p.titulo)} title="Baixar minuta para leitura" className="p-1">
                      <Download className="w-4 h-4 text-slate-300 group-hover:text-bronze" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <p className="px-4 py-2.5 text-[11px] text-slate-400 border-t border-bronze-pale/40">
              Aprovação, finalização e protocolo continuam sujeitos aos gates de validação jurídica, revisão profissional e auditoria da área de Peças.
            </p>
          </div>

          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-bronze-pale">
              <p className="eyebrow flex items-center gap-2">
                <FileText className="w-3 h-3" /> Acervo Documental
              </p>
            </div>
            <div className="divide-y divide-bronze-pale/50">
              {documentos_recentes.map((doc) => (
                <div key={doc.id} className="flex items-center gap-3 px-4 py-3 hover:bg-bronze-50/60 transition-colors group">
                  <Link to={`/casos/${doc.case_id}`} className="flex-1 min-w-0">
                    <p className="text-sm text-navy-900 font-medium truncate">{doc.nome}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">Caso #{doc.case_id} · {doc.tipo}</p>
                  </Link>
                  <button onClick={() => baixarDocumento(doc.id, doc.nome)} title="Baixar documento" className="p-1">
                    <Download className="w-4 h-4 text-slate-300 group-hover:text-bronze" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {abaAtiva === "ia_cliente"''',
)

# Remove toda ferramenta temporária antes do commit final.
for temp in (
    ".github/workflows/pr1199-v4-one-shot.yml",
    ".github/workflows/pr1199-v4-trigger.yml",
    "scripts/pr1199_v4_patch.py",
):
    Path(temp).unlink(missing_ok=True)
