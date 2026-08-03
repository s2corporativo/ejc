"""039 â€” Jurimetria: schema completo para coleta e anÃ¡lise de decisÃµes pÃºblicas.

Tabelas criadas nesta migration:
  jur_tribunais          â€” cadastro dos tribunais monitorados
  jur_classes            â€” TPU CNJ: classes processuais (ex: ApelaÃ§Ã£o = 65)
  jur_assuntos           â€” TPU CNJ: assuntos (ex: Responsabilidade Civil = 7619)
  jur_processos          â€” metadados por processo
  jur_partes             â€” partes de cada processo
  jur_movimentos         â€” andamentos/movimentaÃ§Ãµes
  jur_decisoes           â€” decisÃµes extraÃ­das (acÃ³rdÃ£o, monocrÃ¡tica, etc.)
  jur_ingestao_logs      â€” histÃ³rico de coletas (para rastreabilidade e retry)
  jur_modelos            â€” registro dos modelos ML treinados e suas mÃ©tricas
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "039_jurimetria"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # â”€â”€ 1. Tribunais â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Tabela de referÃªncia: cada linha representa um tribunal monitorado.
    # sigla_datajud = nome do Ã­ndice ElasticSearch no DataJud (ex: "api_publica_tjmg")
    op.create_table(
        "jur_tribunais",
        sa.Column("id",              sa.Integer,     primary_key=True),
        sa.Column("sigla",           sa.String(20),  nullable=False, unique=True),  # "TJMG"
        sa.Column("nome",            sa.Text,        nullable=False),
        sa.Column("sigla_datajud",   sa.String(60),  nullable=True),   # Ã­ndice ES
        sa.Column("uf",              sa.String(2),   nullable=True),
        sa.Column("esfera",          sa.String(20),  nullable=True),   # estadual|federal|superior
        sa.Column("ativo",           sa.Boolean,     default=True),
        sa.Column("config",          JSONB,          nullable=True),   # parÃ¢metros extras de coleta
        sa.Column("criado_em",       sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # â”€â”€ 2. Classes processuais (TPU CNJ) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Tabela de lookup para os cÃ³digos de classe do CNJ.
    # Fonte: https://www.cnj.jus.br/sgt/consulta_publica_classes.php
    op.create_table(
        "jur_classes",
        sa.Column("codigo",      sa.Integer,    primary_key=True),   # cÃ³digo TPU
        sa.Column("nome",        sa.Text,       nullable=False),
        sa.Column("nome_norm",   sa.Text,       nullable=True),      # versÃ£o normalizada p/ join
        sa.Column("grupo",       sa.String(60), nullable=True),      # recurso|acao|incidente
    )

    # â”€â”€ 3. Assuntos processuais (TPU CNJ) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    op.create_table(
        "jur_assuntos",
        sa.Column("codigo",      sa.Integer,    primary_key=True),
        sa.Column("nome",        sa.Text,       nullable=False),
        sa.Column("nome_norm",   sa.Text,       nullable=True),
        sa.Column("ramo",        sa.String(60), nullable=True),      # civil|penal|tributario...
        sa.Column("pai_codigo",  sa.Integer,    nullable=True),      # hierarquia TPU
    )

    # â”€â”€ 4. Processos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # NÃºcleo do sistema: um registro por processo Ãºnico (nrCNJ).
    # Campos derivados (tempo_tramitacao_dias, provimento) sÃ£o calculados
    # no pipeline de processamento e gravados aqui para consultas rÃ¡pidas.
    op.create_table(
        "jur_processos",
        sa.Column("id",                     sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("nr_cnj",                 sa.String(25), nullable=False, unique=True),  # "0000001-00.2020.8.13.0024"
        sa.Column("tribunal_id",            sa.Integer,    sa.ForeignKey("jur_tribunais.id"), nullable=False),
        sa.Column("classe_codigo",          sa.Integer,    sa.ForeignKey("jur_classes.codigo"), nullable=True),
        sa.Column("assunto_principal_cod",  sa.Integer,    sa.ForeignKey("jur_assuntos.codigo"), nullable=True),
        sa.Column("assuntos_raw",           JSONB,         nullable=True),  # lista completa do DataJud
        sa.Column("orgao_julgador",         sa.Text,       nullable=True),
        sa.Column("relator",                sa.Text,       nullable=True),
        sa.Column("relator_norm",           sa.Text,       nullable=True),  # nome normalizado
        sa.Column("comarca",                sa.Text,       nullable=True),
        sa.Column("grau",                   sa.String(5),  nullable=True),  # "G1"|"G2"|"JE"|"SUP"
        sa.Column("data_ajuizamento",       sa.Date,       nullable=True),
        sa.Column("data_ultimo_mov",        sa.Date,       nullable=True),
        sa.Column("data_transito",          sa.Date,       nullable=True),
        sa.Column("situacao",               sa.String(40), nullable=True),  # "Em Andamento"|"Arquivado"
        # â”€â”€ VariÃ¡veis derivadas (calculadas no processamento) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        sa.Column("tempo_tramitacao_dias",  sa.Integer,    nullable=True),
        sa.Column("provimento",             sa.SmallInteger, nullable=True),  # 1=sim, 0=nÃ£o, NULL=indeterminado
        sa.Column("tipo_provimento",        sa.String(40), nullable=True),   # "total"|"parcial"|"negado"
        sa.Column("valor_causa",            sa.Numeric(18, 2), nullable=True),
        # â”€â”€ Controle de ingestÃ£o â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        sa.Column("fonte",                  sa.String(20), nullable=True),   # "datajud"|"stj"|"stf"|"tjmg"
        sa.Column("fonte_id",               sa.Text,       nullable=True),   # ID original na fonte
        sa.Column("raw_datajud",            JSONB,         nullable=True),   # payload completo (auditoria)
        sa.Column("criado_em",              sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em",          sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_jur_processos_tribunal",  "jur_processos", ["tribunal_id"])
    op.create_index("ix_jur_processos_classe",    "jur_processos", ["classe_codigo"])
    op.create_index("ix_jur_processos_relator",   "jur_processos", ["relator_norm"])
    op.create_index("ix_jur_processos_ajuiz",     "jur_processos", ["data_ajuizamento"])

    # â”€â”€ 5. Partes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    op.create_table(
        "jur_partes",
        sa.Column("id",           sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("processo_id",  sa.BigInteger, sa.ForeignKey("jur_processos.id", ondelete="CASCADE")),
        sa.Column("nome",         sa.Text,       nullable=False),
        sa.Column("polo",         sa.String(10), nullable=True),   # "ativo"|"passivo"|"outros"
        sa.Column("tipo",         sa.String(20), nullable=True),   # "pf"|"pj"|"mpu"|"dp"
        sa.Column("doc",          sa.String(20), nullable=True),   # CPF/CNPJ mascarado
    )
    op.create_index("ix_jur_partes_processo", "jur_partes", ["processo_id"])

    # â”€â”€ 6. Movimentos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Andamentos processuais. CÃ³digo TPU de movimentos (1 a 999+).
    op.create_table(
        "jur_movimentos",
        sa.Column("id",           sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("processo_id",  sa.BigInteger, sa.ForeignKey("jur_processos.id", ondelete="CASCADE")),
        sa.Column("codigo_tpu",   sa.Integer,    nullable=True),   # cÃ³digo TPU do movimento
        sa.Column("nome",         sa.Text,       nullable=True),   # descriÃ§Ã£o do movimento
        sa.Column("data",         sa.Date,       nullable=True),
        sa.Column("complemento",  JSONB,         nullable=True),   # campos extras variÃ¡veis
    )
    op.create_index("ix_jur_mov_processo", "jur_movimentos", ["processo_id"])
    op.create_index("ix_jur_mov_data",     "jur_movimentos", ["data"])

    # â”€â”€ 7. DecisÃµes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Textos e metadados das decisÃµes. Separado de processos para permitir
    # mÃºltiplas decisÃµes por processo (ex: decisÃ£o + acÃ³rdÃ£o de embargos).
    op.create_table(
        "jur_decisoes",
        sa.Column("id",              sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("processo_id",     sa.BigInteger, sa.ForeignKey("jur_processos.id", ondelete="CASCADE")),
        sa.Column("tipo",            sa.String(30), nullable=True),   # "acordao"|"mono"|"despacho"
        sa.Column("data_julgamento", sa.Date,       nullable=True),
        sa.Column("relator",         sa.Text,       nullable=True),
        sa.Column("ementa",          sa.Text,       nullable=True),
        sa.Column("acordao",         sa.Text,       nullable=True),   # texto completo (pode ser grande)
        sa.Column("resultado",       sa.String(40), nullable=True),   # "provido"|"negado"|"parcial"
        sa.Column("votacao",         sa.String(60), nullable=True),   # "unanime"|"maioria"
        sa.Column("url_fonte",       sa.Text,       nullable=True),
        sa.Column("metadata_extra",  JSONB,         nullable=True),
        sa.Column("criado_em",       sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jur_decisoes_processo",    "jur_decisoes", ["processo_id"])
    op.create_index("ix_jur_decisoes_julgamento",  "jur_decisoes", ["data_julgamento"])

    # â”€â”€ 8. Logs de ingestÃ£o â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Rastreabilidade: cada execuÃ§Ã£o do pipeline grava um registro aqui.
    # Permite retry em caso de falha e auditoria do que foi coletado.
    op.create_table(
        "jur_ingestao_logs",
        sa.Column("id",               sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fonte",            sa.String(20), nullable=False),   # "datajud"|"stj"...
        sa.Column("tribunal_sigla",   sa.String(20), nullable=True),
        sa.Column("parametros",       JSONB,         nullable=True),    # filtros usados
        sa.Column("status",           sa.String(20), nullable=False),   # "ok"|"erro"|"parcial"
        sa.Column("processos_novos",  sa.Integer,    default=0),
        sa.Column("processos_atuali", sa.Integer,    default=0),
        sa.Column("erros",            sa.Integer,    default=0),
        sa.Column("mensagem",         sa.Text,       nullable=True),
        sa.Column("iniciado_em",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finalizado_em",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("duracao_seg",      sa.Numeric(10, 2), nullable=True),
    )

    # â”€â”€ 9. Modelos ML treinados â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Registro de cada modelo preditivo treinado: parÃ¢metros, mÃ©tricas e artefato.
    op.create_table(
        "jur_modelos",
        sa.Column("id",            sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column("nome",          sa.String(80), nullable=False),    # "provimento_tjmg_2024"
        sa.Column("algoritmo",     sa.String(40), nullable=True),     # "LogisticRegression"
        sa.Column("tribunal",      sa.String(20), nullable=True),
        sa.Column("filtros",       JSONB,         nullable=True),     # filtros usados no treino
        sa.Column("metricas",      JSONB,         nullable=True),     # accuracy, f1, roc_auc...
        sa.Column("features",      JSONB,         nullable=True),     # lista de features usadas
        sa.Column("caminho",       sa.Text,       nullable=True),     # path do arquivo .pkl no disco
        sa.Column("ativo",         sa.Boolean,    default=True),
        sa.Column("treinado_em",   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("amostras",      sa.Integer,    nullable=True),     # n de amostras de treino
    )


def downgrade() -> None:
    for t in ["jur_modelos", "jur_ingestao_logs", "jur_decisoes",
              "jur_movimentos", "jur_partes", "jur_processos",
              "jur_assuntos", "jur_classes", "jur_tribunais"]:
        op.drop_table(t)

