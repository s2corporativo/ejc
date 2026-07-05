# ── app/services/due_diligence_empresarial.py ────────────────────────────────
# Gatilho ESTÁTICO "due_diligence_empresarial" — checklist fixo de due diligence
# para sociedades de clientes empresariais.
#
# Decisão de encaixe (auditoria do gap Empresarial):
#   • O sistema de checklists por CASO (routers/checklists.py) instancia
#     templates apenas sobre cases (case_checklists.case_id NOT NULL) e a
#     geração automática é só-IA (services/checklist_ia.py). Forçar instância
#     por SOCIEDADE exigiria migration extra no núcleo de checklists — caro.
#   • Já existe, porém, o mecanismo estático de templates de due diligence:
#     tabela `due_diligence_templates` (name, dd_type, items JSONB) com
#     endpoints em routers/novos_modulos.py (/due-diligence/templates).
#     REUSO barato: este módulo define o catálogo fixo e o router de
#     sociedades semeia (find-or-create idempotente por dd_type) o template.
#   • Ponto de extensão futuro: se checklists ganharem escopo por sociedade,
#     basta instanciar ITENS_DUE_DILIGENCE (formato compatível com
#     TemplateItemIn de checklists.py: texto/dica/categoria/obrigatorio).
GATILHO = "due_diligence_empresarial"
NOME_TEMPLATE = "Due Diligence Empresarial — Sociedades de Clientes"

# 5 eixos × 5 itens objetivos, com referência normativa em `dica`.
ITENS_DUE_DILIGENCE: list[dict] = [
    # ── Societário ────────────────────────────────────────────────────────────
    {"eixo": "societario", "texto": "Obter contrato/estatuto social consolidado e todas as alterações registradas na Junta Comercial", "dica": "CC arts. 997-1.038; Lei 8.934/94", "obrigatorio": True},
    {"eixo": "societario", "texto": "Conferir quadro societário atual (quotas/ações, administradores e poderes de representação)", "dica": "CC arts. 1.060-1.065; Lei 6.404/76 arts. 138-144", "obrigatorio": True},
    {"eixo": "societario", "texto": "Verificar acordo de sócios/acionistas e cláusulas de preferência, tag along e drag along", "dica": "Lei 6.404/76 art. 118", "obrigatorio": False},
    {"eixo": "societario", "texto": "Checar integralização do capital social e eventuais quotas em tesouraria ou gravadas", "dica": "CC art. 1.052 §§; IN DREI 81/2020", "obrigatorio": True},
    {"eixo": "societario", "texto": "Levantar participações em outras sociedades (controladas/coligadas) e grupos econômicos", "dica": "CC art. 1.097-1.101; CLT art. 2º §2º (risco de grupo)", "obrigatorio": False},
    # ── Fiscal ────────────────────────────────────────────────────────────────
    {"eixo": "fiscal", "texto": "Emitir CND/CPEN federal (RFB/PGFN) e certidões estaduais e municipais", "dica": "CTN art. 205-206", "obrigatorio": True},
    {"eixo": "fiscal", "texto": "Verificar regularidade do FGTS (CRF) e certidão negativa de débitos trabalhistas (CNDT)", "dica": "Lei 8.036/90 art. 27; CLT art. 642-A", "obrigatorio": True},
    {"eixo": "fiscal", "texto": "Levantar parcelamentos fiscais vigentes e passivo tributário contingente (autos de infração)", "dica": "CTN arts. 151, 155-A", "obrigatorio": True},
    {"eixo": "fiscal", "texto": "Conferir enquadramento tributário (Simples/presumido/real) e aderência ao faturamento", "dica": "LC 123/2006; RIR/2018", "obrigatorio": False},
    {"eixo": "fiscal", "texto": "Checar obrigações acessórias entregues (ECF, EFD, DCTF) nos últimos 5 exercícios", "dica": "CTN art. 173 (decadência)", "obrigatorio": False},
    # ── Trabalhista ───────────────────────────────────────────────────────────
    {"eixo": "trabalhista", "texto": "Levantar ações trabalhistas em curso e histórico de condenações (5 anos)", "dica": "CLT; consulta PJe/TRT", "obrigatorio": True},
    {"eixo": "trabalhista", "texto": "Auditar quadro de empregados: registro, jornada, horas extras e verbas recolhidas (INSS/FGTS)", "dica": "CLT arts. 41, 58-59; Lei 8.212/91", "obrigatorio": True},
    {"eixo": "trabalhista", "texto": "Verificar terceirização e PJs: risco de reconhecimento de vínculo", "dica": "Lei 13.429/2017; CLT art. 3º", "obrigatorio": True},
    {"eixo": "trabalhista", "texto": "Conferir normas coletivas aplicáveis (CCT/ACT) e cumprimento de pisos e benefícios", "dica": "CF art. 7º, XXVI; CLT art. 611-A", "obrigatorio": False},
    {"eixo": "trabalhista", "texto": "Checar programas obrigatórios de SST (PGR, PCMSO, CIPA) e passivo de insalubridade/periculosidade", "dica": "CLT arts. 154-201; NRs MTE", "obrigatorio": False},
    # ── Contratos / Cíveis ────────────────────────────────────────────────────
    {"eixo": "contratos_civeis", "texto": "Mapear contratos relevantes (clientes, fornecedores, locação) e cláusulas de change of control", "dica": "CC arts. 421-480", "obrigatorio": True},
    {"eixo": "contratos_civeis", "texto": "Levantar ações cíveis ativas e passivas e protestos/negativações da sociedade e sócios", "dica": "consulta TJ/Serasa/cartórios de protesto", "obrigatorio": True},
    {"eixo": "contratos_civeis", "texto": "Verificar garantias prestadas (avais, fianças, alienações fiduciárias) e ônus sobre ativos", "dica": "CC arts. 818-839, 1.361-1.368", "obrigatorio": True},
    {"eixo": "contratos_civeis", "texto": "Conferir propriedade intelectual: marcas, patentes e domínios registrados e vigentes", "dica": "Lei 9.279/96 (INPI)", "obrigatorio": False},
    {"eixo": "contratos_civeis", "texto": "Checar seguros empresariais vigentes (D&O, responsabilidade civil, patrimonial)", "dica": "CC arts. 757-802", "obrigatorio": False},
    # ── LGPD ──────────────────────────────────────────────────────────────────
    {"eixo": "lgpd", "texto": "Verificar existência de encarregado (DPO) designado e canal do titular divulgado", "dica": "LGPD art. 41", "obrigatorio": True},
    {"eixo": "lgpd", "texto": "Levantar registro das operações de tratamento (ROPA) e bases legais utilizadas", "dica": "LGPD arts. 7º e 37", "obrigatorio": True},
    {"eixo": "lgpd", "texto": "Conferir contratos com operadores/suboperadores e cláusulas de proteção de dados", "dica": "LGPD art. 39", "obrigatorio": True},
    {"eixo": "lgpd", "texto": "Checar histórico de incidentes de segurança e comunicações à ANPD", "dica": "LGPD art. 48", "obrigatorio": False},
    {"eixo": "lgpd", "texto": "Avaliar necessidade de RIPD para tratamentos de alto risco/dados sensíveis", "dica": "LGPD arts. 5º, XVII e 38", "obrigatorio": False},
]
