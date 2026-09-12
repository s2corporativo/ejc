"""
EJC — Seed das tabelas de configuração do redesign (migração 057).
Popula: document_types_master (14 tipos), area_modulos_mapping (16 áreas)
e module_help (3 exemplos: casos, prazos, documentos). Idempotente por chave
natural (tipo_key / area+module_key / module_key+titulo).

⚠️ tabela_oab_honorarios NÃO é semeada de propósito: não existe no repositório
dado estruturado da Tabela OAB/MG com fonte oficial identificada (o RAG
categoria "tabela_honorarios_oab" é consultado em runtime, mas nenhum seed a
ingere; app/services/honorarios_oab.py declara-se explicitamente REFERENCIAL
e "NÃO substitui a tabela oficial"). Inventar valores é proibido (CLAUDE.md).
Quando a tabela oficial OAB/MG for obtida, ingerir citando a fonte em `fonte`.

Execução: python -m app.seeds.redesign_seed
(não roda automaticamente no entrypoint — mesmo padrão dos demais app/seeds)
"""
import json
import os
import sys
from uuid import uuid4

# ══════════════════════════════════════════════════════════════════════════════
# 1. DOCUMENT_TYPES_MASTER — 14 tipos p/ importação/classificação (R3/B5)
#    campos_extracao: campos que a extração IA deve tentar preencher no tipo.
# ══════════════════════════════════════════════════════════════════════════════
_EXT_PADRAO = ["pdf", "docx", "jpg", "jpeg", "png"]

DOCUMENT_TYPES = [
    {
        "tipo_key": "contrato", "nome": "Contrato", "categoria": "juridico",
        "descricao": "Contratos em geral (prestação de serviços, compra e venda, locação, societário).",
        "campos_extracao": ["partes", "cpf_cnpj_partes", "objeto", "valor",
                            "data_assinatura", "vigencia_inicio", "vigencia_fim",
                            "foro", "clausulas_criticas"],
        "extensoes_aceitas": ["pdf", "docx", "txt"],
    },
    {
        "tipo_key": "multa_transito", "nome": "Multa de Trânsito", "categoria": "administrativo",
        "descricao": "Notificação de autuação/penalidade de trânsito (CTB).",
        "campos_extracao": ["codigo_infracao", "orgao_autuador", "placa",
                            "data_infracao", "valor", "prazo_defesa", "condutor_identificado"],
        "extensoes_aceitas": ["pdf", "jpg", "jpeg", "png"],
    },
    {
        "tipo_key": "multa_ambiental", "nome": "Multa Ambiental", "categoria": "administrativo",
        "descricao": "Auto de infração ambiental (IBAMA, SEMAD, Polícia Ambiental).",
        "campos_extracao": ["numero_auto", "orgao_autuador", "enquadramento_legal",
                            "valor", "data_infracao", "local_infracao", "prazo_defesa"],
        "extensoes_aceitas": _EXT_PADRAO,
    },
    {
        "tipo_key": "auto_infracao", "nome": "Auto de Infração (geral)", "categoria": "administrativo",
        "descricao": "Autos de infração administrativos em geral (fiscais, sanitários, regulatórios).",
        "campos_extracao": ["numero_auto", "orgao_autuador", "enquadramento_legal",
                            "valor", "data_infracao", "prazo_defesa"],
        "extensoes_aceitas": _EXT_PADRAO,
    },
    {
        "tipo_key": "nfe_xml", "nome": "Nota Fiscal Eletrônica (XML)", "categoria": "fiscal",
        "descricao": "NF-e/NFS-e em XML para análise fiscal e tributária.",
        "campos_extracao": ["chave_acesso", "ncm", "cfop", "cnpj_emitente",
                            "cnpj_destinatario", "valor_total", "data_emissao"],
        "extensoes_aceitas": ["xml"],
    },
    {
        "tipo_key": "denuncia", "nome": "Denúncia / Queixa-crime", "categoria": "juridico",
        "descricao": "Peça acusatória do MP ou queixa-crime (área criminal).",
        "campos_extracao": ["tipificacao_artigo", "orgao", "denunciado",
                            "data_fato", "comarca", "resumo_fatos"],
        "extensoes_aceitas": ["pdf", "docx"],
    },
    {
        "tipo_key": "boletim_ocorrencia", "nome": "Boletim de Ocorrência", "categoria": "juridico",
        "descricao": "B.O. policial (registro de ocorrência).",
        "campos_extracao": ["numero_bo", "orgao", "natureza", "data_fato",
                            "local_fato", "envolvidos"],
        "extensoes_aceitas": _EXT_PADRAO,
    },
    {
        "tipo_key": "peticao", "nome": "Petição", "categoria": "juridico",
        "descricao": "Petições e peças processuais (inicial, contestação, recurso).",
        "campos_extracao": ["tipo_peca", "numero_processo", "vara", "comarca",
                            "partes", "pedidos"],
        "extensoes_aceitas": ["pdf", "docx"],
    },
    {
        "tipo_key": "procuracao", "nome": "Procuração", "categoria": "juridico",
        "descricao": "Procuração ad judicia ou com poderes especiais.",
        "campos_extracao": ["outorgante", "cpf_cnpj_outorgante", "outorgado",
                            "poderes", "data_assinatura", "validade"],
        "extensoes_aceitas": _EXT_PADRAO,
    },
    {
        "tipo_key": "doc_identificacao", "nome": "Documento de Identificação", "categoria": "pessoal",
        "descricao": "RG, CNH, CPF ou outro documento de identificação pessoal.",
        "campos_extracao": ["nome", "cpf", "rg", "data_nascimento", "orgao_emissor"],
        "extensoes_aceitas": ["pdf", "jpg", "jpeg", "png"],
    },
    {
        "tipo_key": "comprovante_residencia", "nome": "Comprovante de Residência", "categoria": "pessoal",
        "descricao": "Conta de consumo ou correspondência que comprove endereço.",
        "campos_extracao": ["nome", "endereco", "cep", "data_emissao", "emissor"],
        "extensoes_aceitas": ["pdf", "jpg", "jpeg", "png"],
    },
    {
        "tipo_key": "laudo_tecnico", "nome": "Laudo Técnico / Perícia", "categoria": "juridico",
        "descricao": "Laudos periciais, pareceres e relatórios técnicos.",
        "campos_extracao": ["perito", "area_pericia", "data_laudo",
                            "numero_processo", "conclusao"],
        "extensoes_aceitas": ["pdf", "docx"],
    },
    {
        "tipo_key": "outro", "nome": "Outro Documento", "categoria": "outro",
        "descricao": "Documento sem tipo específico — extração genérica.",
        "campos_extracao": None,
        "extensoes_aceitas": _EXT_PADRAO,
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# 2. AREA_MODULOS_MAPPING — 16 áreas → módulos REAIS do sistema (R6)
#    module_key = rota do frontend (src/App.tsx) sem barra inicial.
#    ferramentas = endpoints REAIS de ramos.py (relativos ao prefixo /api).
#    Conservador: só módulos/rotas que existem hoje.
# ══════════════════════════════════════════════════════════════════════════════
_CORE = ["casos", "prazos", "documentos", "pecas", "checklists", "workflow"]


def _area(area, extras=None):
    """Monta as linhas de uma área: módulos-núcleo + módulos específicos."""
    linhas = [{"area": area, "module_key": mk, "ordem": i}
              for i, mk in enumerate(_CORE)]
    for j, extra in enumerate(extras or []):
        linhas.append({"area": area, "module_key": extra["module_key"],
                       "ordem": len(_CORE) + j,
                       "ferramentas": extra.get("ferramentas")})
    return linhas


def _f(nome, endpoint):
    return {"nome": nome, "endpoint": endpoint}


AREA_MODULOS = (
    _area("civel", [{
        "module_key": "ramos/civel",
        "ferramentas": [
            _f("Prazos de contestação", "/civel/ferramentas/prazos-contestacao"),
            _f("Cálculo de alimentos", "/civel/ferramentas/alimentos-calcular"),
            _f("Verificador de usucapião", "/civel/ferramentas/usucapiao-verificar"),
        ]}])
    + _area("consumidor", [{
        "module_key": "ramos/consumidor",
        "ferramentas": [
            _f("Devolução em dobro (CDC art. 42)", "/consumidor/ferramentas/devolucao-dobro"),
            _f("Prazos CDC (decadência/prescrição)", "/consumidor/ferramentas/prazos-cdc"),
            _f("Negativação indevida", "/consumidor/ferramentas/negativacao-indevida"),
        ]}])
    + _area("familia", [{
        "module_key": "ramos/familia",
        "ferramentas": [
            _f("Débito de alimentos", "/familia/ferramentas/debito-alimentos"),
            _f("ITCMD em inventário", "/familia/ferramentas/itcmd-inventario"),
        ]}])
    # Sucessões não tem ramo próprio — as ferramentas de inventário vivem no
    # ramo Família (itcmd-inventario). Mapeamento conservador.
    + _area("sucessoes", [{
        "module_key": "ramos/familia",
        "ferramentas": [
            _f("ITCMD em inventário", "/familia/ferramentas/itcmd-inventario"),
        ]}])
    + _area("trabalhista", [{
        "module_key": "ramos/trabalhista",
        "ferramentas": [
            _f("Horas extras", "/trabalhista-esp/ferramentas/horas-extras"),
            _f("Prazos trabalhistas", "/trabalhista-esp/ferramentas/prazos"),
            _f("Prescrição trabalhista", "/trabalhista-esp/ferramentas/prescricao-trabalhista"),
            _f("Depósito recursal", "/trabalhista-esp/ferramentas/deposito-recursal"),
        ]}])
    + _area("previdenciario", [{
        "module_key": "ramos/previdenciario",  # gitleaks:allow -- chave semântica de módulo, não credencial
        "ferramentas": [
            _f("Prazos previdenciários", "/previdenciario/ferramentas/prazos"),
            _f("Tempo de contribuição", "/previdenciario/ferramentas/tempo-contribuicao"),
            _f("Carência", "/previdenciario/ferramentas/carencia"),
        ]}])
    + _area("empresarial", [{
        "module_key": "ramos/empresarial",
        "ferramentas": [
            _f("Prazos de recuperação judicial", "/empresarial/ferramentas/prazos-rj"),
            _f("Verificação CADE", "/empresarial/ferramentas/verificar-cade"),
            _f("Juros de mora", "/empresarial/ferramentas/juros-mora"),
        ]}])
    + _area("tributario", [{
        "module_key": "ramos/tributario",
        "ferramentas": [
            _f("Multa de mora", "/tributario/ferramentas/multa-mora"),
        ]}])
    # Contratos e Juizados Especiais: sem ramo/módulo dedicado hoje — só núcleo.
    + _area("contratos")
    + _area("juizados_especiais")
    + _area("imobiliario", [{
        "module_key": "ramos/imobiliario",
        "ferramentas": [
            _f("Reajuste de aluguel", "/imobiliario/ferramentas/reajuste-aluguel"),
            _f("Prazos de despejo", "/imobiliario/ferramentas/prazos-despejo"),
            _f("Distrato imobiliário", "/imobiliario/ferramentas/distrato"),
        ]}])
    + _area("bancario", [{
        "module_key": "ramos/bancario",
        "ferramentas": [
            _f("Análise de juros", "/bancario/ferramentas/analise-juros"),
            _f("Juros abusivos", "/bancario/ferramentas/juros-abusivos"),
            _f("Superendividamento", "/bancario/ferramentas/superendividamento"),
            _f("Busca e apreensão", "/bancario/ferramentas/busca-apreensao"),
        ]}])
    + _area("administrativo", [{
        "module_key": "ramos/administrativo",
        "ferramentas": [
            _f("Recurso de multa de trânsito", "/admin-esp/ferramentas/recurso-multa-transito"),
            _f("Mandado de segurança (prazos)", "/admin-esp/ferramentas/mandado-seguranca"),
        ]}])
    + _area("criminal", [{
        "module_key": "ramos/penal",
        "ferramentas": [
            _f("Prazos processuais penais", "/penal/ferramentas/prazos-processuais"),
            _f("Verificador de ANPP", "/penal/ferramentas/verificar-anpp"),
            _f("Prescrição penal", "/penal/ferramentas/prescricao-penal"),
            _f("Dosimetria", "/penal/ferramentas/dosimetria"),
        ]}])
    + _area("ambiental", [{"module_key": "ramos/ambiental"}])
)

# ══════════════════════════════════════════════════════════════════════════════
# 3. MODULE_HELP — 3 exemplos (casos, prazos, documentos). Conteúdo baseado no
#    comportamento REAL do sistema. Demais módulos: preencher via UI (F4/R1).
# ══════════════════════════════════════════════════════════════════════════════
MODULE_HELP = [
    {
        "module_key": "casos",
        "titulo": "Gestão de Casos",
        "conteudo_md": """## O que este módulo faz
Centraliza todos os casos do escritório — judiciais e consultivos. Cada caso reúne cliente, área do direito, processos vinculados, partes, prazos, documentos, honorários, checklist e workflow.

## Quando usar
Sempre que chegar uma nova demanda (consulta, autuação, citação ou contratação). O caso é a unidade central: prazos, documentos e honorários são vinculados a ele.

## Passo a passo
1. Clique em **Novo Caso**.
2. Preencha os campos obrigatórios: **título**, **cliente** e **área do direito**.
3. Opcionais úteis: número do processo (CNJ), tribunal/comarca/vara, parte contrária, valor da causa e descrição dos fatos.
4. Defina o advogado responsável (controla quem enxerga o caso — equipe só acessa casos em que é responsável ou auxiliar).
5. Informe tipo de ação e data do fato para cálculo automático de **prescrição**.
6. Após criar: vincule documentos, cadastre prazos e aplique checklist/workflow da área.

## Campos obrigatórios
- Título
- Cliente
- Área do direito

## Resultado esperado
Caso criado em status **triagem**, visível ao responsável e à gestão, pronto para receber prazos, documentos e movimentações. O ciclo de vida é: triagem → ativo → (suspenso/acordo) → encerrado → arquivado.

> Arquivamento e exclusão são restritos a admin/sócio; exclusão é reversível pela **Lixeira** e registrada no log de auditoria.""",
    },
    {
        "module_key": "prazos",
        "titulo": "Controle de Prazos",
        "conteudo_md": """## O que este módulo faz
Controla prazos processuais e administrativos com cálculo automático em **dias úteis** (CPC) ou corridos, considerando feriados nacionais, feriados municipais de Betim/MG e suspensões por tribunal.

## Quando usar
Ao receber intimação, publicação no Diário Oficial ou qualquer ato com prazo. Cadastre imediatamente — o sistema dispara alertas automáticos a **7, 3 e 1 dia** do vencimento (verificação diária às 7h15).

## Passo a passo
1. Clique em **Novo Prazo**.
2. Informe o **título** (ex.: "Contestação — Proc. 0001234-56").
3. Escolha uma das formas de data:
   - **Data final direta** (data do prazo), ou
   - **Data da intimação + quantidade de dias** — o sistema calcula o vencimento (dias úteis por padrão; desmarque para dias corridos em prazos administrativos).
4. Informe o tribunal para considerar suspensões por portaria (TJMG/TRT3 etc.).
5. Vincule ao caso e defina o responsável e a prioridade.

## Campos obrigatórios
- Título
- Data do prazo **ou** data da intimação + dias

## Resultado esperado
Prazo cadastrado com vencimento calculado corretamente e alertas automáticos programados (notificação interna, e-mail e push conforme configuração). Prazos vencendo aparecem no dashboard e no morning brief.""",
    },
    {
        "module_key": "documentos",
        "titulo": "Gestão Documental",
        "conteudo_md": """## O que este módulo faz
Repositório central de documentos do escritório com **OCR automático** (PDF, DOCX, imagens), análise por IA (extração de partes, CPF/CNPJ, datas, valores e área do direito) e 5 níveis de confidencialidade.

## Quando usar
Para guardar qualquer documento de cliente ou caso: contratos, procurações, autos de infração, laudos, comprovantes. Use a **Importação Inteligente** quando quiser que a IA leia e classifique o documento.

## Passo a passo
1. Clique em **Upload** (ou arraste o arquivo).
2. Formatos aceitos: PDF, DOCX, JPG/PNG e TXT.
3. Selecione o **tipo de documento** (contrato, procuração, multa, laudo…) — a IA pode sugerir o tipo, mas a confirmação é sua.
4. Vincule ao **cliente** e/ou **caso** correspondente.
5. Defina o nível de **confidencialidade** (controla quem pode visualizar).
6. Aguarde o OCR — o texto extraído torna o documento pesquisável.

## Campos obrigatórios
- Arquivo
- Tipo de documento

## Resultado esperado
Documento armazenado, pesquisável por conteúdo (OCR) e visível conforme confidencialidade e permissões do caso. Na importação inteligente, a IA devolve um resumo estruturado (partes, valores, prazos e estratégia sugerida) — **sempre revise antes de aproveitar o resultado** (revisão humana obrigatória).""",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER (sync, idempotente — mesmo padrão de checklists_seed.py)
# ══════════════════════════════════════════════════════════════════════════════
def seed():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://")
    if not url:
        print("❌ DATABASE_URL(_SYNC) não configurada."); sys.exit(1)

    engine = create_engine(url)
    with Session(engine) as s:
        # 1. document_types_master (idempotente por tipo_key)
        ins = skip = 0
        for i, dt in enumerate(DOCUMENT_TYPES):
            row = s.execute(
                text("SELECT id FROM document_types_master WHERE tipo_key=:k"),
                {"k": dt["tipo_key"]},
            ).fetchone()
            if row:
                skip += 1; continue
            s.execute(text("""
                INSERT INTO document_types_master
                    (id, tipo_key, nome, descricao, categoria,
                     campos_extracao, extensoes_aceitas, ativo, ordem)
                VALUES (:id, :k, :nome, :descricao, :categoria,
                        CAST(:campos AS jsonb), CAST(:ext AS jsonb), true, :ordem)
            """), {
                "id": str(uuid4()), "k": dt["tipo_key"], "nome": dt["nome"],
                "descricao": dt["descricao"], "categoria": dt["categoria"],
                "campos": json.dumps(dt["campos_extracao"]) if dt["campos_extracao"] else None,
                "ext": json.dumps(dt["extensoes_aceitas"]) if dt["extensoes_aceitas"] else None,
                "ordem": i,
            })
            ins += 1
        print(f"  ✅ document_types_master: inseridos={ins} ignorados={skip}")

        # 2. area_modulos_mapping (idempotente por area+module_key)
        ins = skip = 0
        for m in AREA_MODULOS:
            row = s.execute(
                text("SELECT id FROM area_modulos_mapping "
                     "WHERE area_juridica=:a AND module_key=:m"),
                {"a": m["area"], "m": m["module_key"]},
            ).fetchone()
            if row:
                skip += 1; continue
            s.execute(text("""
                INSERT INTO area_modulos_mapping
                    (id, area_juridica, module_key, habilitado, ordem, ferramentas)
                VALUES (:id, :a, :m, true, :ordem, CAST(:ferr AS jsonb))
            """), {
                "id": str(uuid4()), "a": m["area"], "m": m["module_key"],
                "ordem": m.get("ordem", 0),
                "ferr": json.dumps(m["ferramentas"], ensure_ascii=False)
                        if m.get("ferramentas") else None,
            })
            ins += 1
        print(f"  ✅ area_modulos_mapping: inseridos={ins} ignorados={skip}")

        # 3. module_help (idempotente por module_key+titulo)
        ins = skip = 0
        for h in MODULE_HELP:
            row = s.execute(
                text("SELECT id FROM module_help WHERE module_key=:k AND titulo=:t"),
                {"k": h["module_key"], "t": h["titulo"]},
            ).fetchone()
            if row:
                skip += 1; continue
            s.execute(text("""
                INSERT INTO module_help (id, module_key, titulo, conteudo_md, ordem, ativo)
                VALUES (:id, :k, :t, :c, 0, true)
            """), {"id": str(uuid4()), "k": h["module_key"],
                   "t": h["titulo"], "c": h["conteudo_md"]})
            ins += 1
        print(f"  ✅ module_help: inseridos={ins} ignorados={skip}")

        # 4. tabela_oab_honorarios — SEM seed (ver docstring do módulo).
        print("  ⏭️  tabela_oab_honorarios: sem seed — aguardando tabela oficial "
              "OAB/MG com fonte identificada (nunca inventar valores).")

        s.commit()
    print("\nREDESIGN SEED concluído.")


if __name__ == "__main__":
    print("EJC — Redesign Seed (migração 057)\n")
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass
    seed()
