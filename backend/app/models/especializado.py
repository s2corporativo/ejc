# ── app/models/especializado.py ───────────────────────────────────────────────
# Modelos especializados por ramo jurídico — seguem o padrão do EnvironmentalCase:
# uma tabela satélite por área, vinculada ao Case genérico (1-1, única no caso).
# Cada modelo captura os metadados e prazos específicos daquele ramo.
# Base legal de referência em cada campo. Todas as saídas de IA são HITL.
from __future__ import annotations
import enum
from sqlalchemy import (
    Column, String, Date, DateTime, Text, Numeric, Boolean,
    Enum as SAEnum, ForeignKey, Integer, func,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


# ══════════════════════════════════════════════════════════════════════════════
# 1. DIREITO EMPRESARIAL
# Abrange: societário, recuperação judicial, contratos empresariais,
#          trabalhista empresarial, administrativo, tributário, concorrencial.
# ══════════════════════════════════════════════════════════════════════════════
class EmpresarialTipo(str, enum.Enum):
    societario           = "societario"           # constituição/alteração/dissolução
    recuperacao_judicial = "recuperacao_judicial" # Lei 11.101/2005
    recuperacao_extra    = "recuperacao_extrajudicial"
    falencia             = "falencia"
    contrato_empresarial = "contrato_empresarial" # revisão/elaboração
    due_diligence        = "due_diligence"        # M&A
    cade                 = "cade"                 # antitruste / SBDC
    propriedade_intelectual = "propriedade_intelectual"  # marcas INPI
    trabalhista_empresarial = "trabalhista_empresarial"  # passivo, PLR, PDV
    tributario_empresarial  = "tributario_empresarial"   # planejamento, CARF
    administrativo_empresarial = "administrativo_empresarial"  # contratos com o poder público, PPP
    consumidor_empresarial  = "consumidor_empresarial"   # Procon/SENACON defesa
    ambiental_empresarial   = "ambiental_empresarial"    # licenciamento, TCFA
    governanca              = "governanca"               # ESG, compliance, LGPD
    outro                   = "outro"


class EmpresarialStatus(str, enum.Enum):
    diagnostico      = "diagnostico"
    em_andamento     = "em_andamento"
    pendente_cliente = "pendente_cliente"
    aguardando_orgao = "aguardando_orgao"
    encerrado        = "encerrado"


class EmpresarialCase(Base):
    """
    Satélite de caso empresarial. Captura dados específicos do ramo.
    Prazo chave: RJ — 60 dias p/ apresentar plano (Lei 11.101/05 art. 53);
                  CADE — 30 dias para notificação de ato de concentração (art. 88 §2º Lei 12.529/11).
    """
    __tablename__ = "empresarial_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    tipo    = Column(SAEnum(EmpresarialTipo), nullable=False, default=EmpresarialTipo.contrato_empresarial)
    status  = Column(SAEnum(EmpresarialStatus), nullable=False, default=EmpresarialStatus.diagnostico)

    # Societário
    cnpj_empresa        = Column(String(18), nullable=True)
    tipo_societario     = Column(String(50), nullable=True)   # SA/LTDA/EIRELI/SLU
    capital_social      = Column(Numeric(16, 2), nullable=True)
    nire                = Column(String(20), nullable=True)    # Registro JUCEMG

    # Recuperação judicial
    data_distribuicao_rj = Column(Date, nullable=True)
    data_aprovacao_plano  = Column(Date, nullable=True)        # 60 dias da concessão
    valor_passivo_total   = Column(Numeric(16, 2), nullable=True)
    numero_credores       = Column(Integer, nullable=True)

    # CADE / Antitruste
    ato_concentracao_notificado = Column(Boolean, default=False)
    data_notificacao_cade       = Column(Date, nullable=True)  # prazo: 30 dias (art. 88 §2º)
    valor_operacao              = Column(Numeric(16, 2), nullable=True)

    # INPI / Propriedade intelectual
    numero_processo_inpi  = Column(String(30), nullable=True)
    tipo_pi               = Column(String(30), nullable=True)  # marca/patente/software/DI

    # Passivo trabalhista
    num_reclamacoes_trabalhistas = Column(Integer, nullable=True)
    valor_passivo_trabalhista    = Column(Numeric(16, 2), nullable=True)

    # Tributário empresarial
    regime_tributario     = Column(String(30), nullable=True)  # SN/LP/LR
    debito_fiscal_total   = Column(Numeric(16, 2), nullable=True)
    em_parcelamento       = Column(Boolean, default=False)      # REFIS/PERT

    # Documentação
    data_encerramento_estimado = Column(Date, nullable=True)
    honorarios_tipo            = Column(String(30), nullable=True)  # fixo/êxito/hora
    observacoes                = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="empresarial")


# ══════════════════════════════════════════════════════════════════════════════
# 2. DIREITO CÍVEL — Família, Imobiliário, Consumidor, JEC, Responsabilidade Civil
# ══════════════════════════════════════════════════════════════════════════════
class CivelTipo(str, enum.Enum):
    responsabilidade_civil = "responsabilidade_civil"  # danos morais/materiais
    familia_divorcio       = "familia_divorcio"         # Lei 10.406/02 + CPC arts. 693-699
    familia_alimentos      = "familia_alimentos"        # Lei 5.478/68 + CPC art. 531
    familia_guarda         = "familia_guarda"           # ECA art. 28 + CC art. 1.583
    familia_inventario     = "familia_inventario"       # CPC art. 610 + CC arts. 1.784+
    familia_uniao_estavel  = "familia_uniao_estavel"    # CC arts. 1.723-1.727
    familia_adocao         = "familia_adocao"           # ECA arts. 39-52
    imobiliario_compra     = "imobiliario_compra_venda"
    imobiliario_locacao    = "imobiliario_locacao"      # Lei 8.245/91
    imobiliario_usucapiao  = "imobiliario_usucapiao"    # CC arts. 1.238-1.244
    imobiliario_vizinhanca = "imobiliario_vizinhanca"   # CC arts. 1.277-1.313
    imobiliario_condominio = "imobiliario_condominio"   # Lei 4.591/64 + CC arts. 1.331+
    consumidor             = "consumidor"               # CDC Lei 8.078/90
    jec                    = "jec"                      # Lei 9.099/95 (≤40 SM)
    cobranca               = "cobranca"                 # CPC art. 700 (monitória)
    indenizacao_acidente   = "indenizacao_acidente"
    outro_civel            = "outro_civel"


class CivelStatus(str, enum.Enum):
    pre_processual   = "pre_processual"
    inicial          = "inicial"
    citacao_pendente = "citacao_pendente"
    instrucao        = "instrucao"
    sentenca         = "sentenca"
    recursal         = "recursal"
    cumprimento      = "cumprimento_sentenca"
    acordo           = "acordo"
    encerrado        = "encerrado"


class CivelCase(Base):
    """
    Satélite de caso cível. Foco em família, imobiliário, consumidor, JEC.
    Prazos críticos:
      - Contestação: 15 dias úteis (CPC art. 335)
      - Recurso (Apelação): 15 dias (CPC art. 1.003 §5º)
      - JEC: 10 dias corridos para contestação (Lei 9.099/95 art. 30)
      - Alimentos provisionais: 15 dias (CPC art. 531)
    """
    __tablename__ = "civel_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    tipo   = Column(SAEnum(CivelTipo), nullable=False)
    status = Column(SAEnum(CivelStatus), nullable=False, default=CivelStatus.pre_processual)

    # Geral
    valor_causa      = Column(Numeric(14, 2), nullable=True)
    competencia      = Column(String(60), nullable=True)  # vara/JEC/fazenda
    polo_ativo       = Column(String(20), nullable=True)  # autor|reu
    tutela_urgencia  = Column(Boolean, default=False)     # houve/pleiteada
    data_tutela      = Column(Date, nullable=True)

    # Família
    regime_bens        = Column(String(40), nullable=True)  # comunhão parcial/universal/separação
    filhos_menores     = Column(Integer, default=0)
    guarda_tipo        = Column(String(30), nullable=True)   # unilateral/compartilhada
    alimentos_valor    = Column(Numeric(12, 2), nullable=True)
    alimentos_percentual = Column(Numeric(5, 2), nullable=True)  # % sobre salários/SM
    data_separacao     = Column(Date, nullable=True)

    # Imobiliário
    tipo_imovel        = Column(String(40), nullable=True)  # urbano/rural/apartamento/lote
    matricula_imovel   = Column(String(30), nullable=True)  # nº CRI
    area_m2            = Column(Numeric(10, 2), nullable=True)
    valor_imovel       = Column(Numeric(14, 2), nullable=True)
    data_posse         = Column(Date, nullable=True)         # para usucapião
    anos_posse         = Column(Numeric(4, 1), nullable=True)

    # Consumidor / JEC
    fornecedor         = Column(String(255), nullable=True)
    numero_contrato    = Column(String(60), nullable=True)
    valor_pedido       = Column(Numeric(12, 2), nullable=True)
    dano_moral_pedido  = Column(Numeric(12, 2), nullable=True)
    data_fato          = Column(Date, nullable=True)
    protocolo_procon   = Column(String(60), nullable=True)

    # Controle de prazos críticos
    data_citacao       = Column(Date, nullable=True)
    data_contestacao   = Column(Date, nullable=True)  # prazo calculado
    data_audiencia     = Column(Date, nullable=True)

    resultado          = Column(Text, nullable=True)
    observacoes        = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="civel")


# ══════════════════════════════════════════════════════════════════════════════
# 3. DIREITO PENAL
# ══════════════════════════════════════════════════════════════════════════════
class PenalTipo(str, enum.Enum):
    # Crimes mais comuns em atuação do escritório
    estelionato         = "estelionato"          # CP art. 171
    furto               = "furto"                # CP art. 155
    roubo               = "roubo"                # CP art. 157
    lesao_corporal      = "lesao_corporal"        # CP art. 129
    homicidio           = "homicidio"            # CP arts. 121-122
    trafico_drogas      = "trafico_drogas"        # Lei 11.343/2006
    crime_transito      = "crime_transito"        # Lei 9.503/97 CTB
    crime_ambiental     = "crime_ambiental"       # Lei 9.605/98
    violencia_domestica = "violencia_domestica"   # Lei 11.340/2006 (LMP)
    corrupção           = "corrupcao"             # CP arts. 317-318 + Lei 8.429/92
    sonegacao           = "sonegacao_fiscal"      # Lei 8.137/90
    crimes_informaticos = "crimes_informaticos"   # Lei 12.737/2012 + Lei 14.155/2021
    injuria_difamacao   = "injuria_difamacao"     # CP arts. 138-140
    ameaca              = "ameaca"               # CP art. 147
    outro_penal         = "outro_penal"


class PenalFase(str, enum.Enum):
    investigacao          = "investigacao"         # IP / TCO / SINPOL
    denuncia_pendente     = "denuncia_pendente"
    resposta_acusacao     = "resposta_acusacao"   # 10 dias (CPP art. 396-A)
    instrucao             = "instrucao"
    alegacoes_finais      = "alegacoes_finais"    # 10 dias (CPP art. 403)
    julgamento            = "julgamento"
    recursal_rese         = "recursal_rese"        # RESE: 5 dias (CPP art. 586)
    recursal_apelacao     = "recursal_apelacao"   # 5 dias CPP art. 593
    execucao_penal        = "execucao_penal"      # LEP Lei 7.210/84
    habeas_corpus         = "habeas_corpus"
    anpp                  = "anpp"               # Acordo não persecução penal (CPP art. 28-A)
    encerrado             = "encerrado"


class PenalCase(Base):
    """
    Satélite de caso penal.
    Prazos críticos:
      - Resposta à acusação: 10 dias (CPP art. 396-A)
      - RESE: 5 dias (CPP art. 586)
      - Apelação: 5 dias (CPP art. 593 §4º)
      - Alegações finais: 10 dias (CPP art. 403)
      - HC: urgente — sem prazo legal, celeridade máxima
    """
    __tablename__ = "penal_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    tipo_crime  = Column(SAEnum(PenalTipo), nullable=False)
    fase        = Column(SAEnum(PenalFase), nullable=False, default=PenalFase.investigacao)

    # Identificação
    numero_bo        = Column(String(40), nullable=True)   # boletim de ocorrência
    numero_ip        = Column(String(40), nullable=True)   # inquérito policial
    delegacia        = Column(String(100), nullable=True)
    data_fato        = Column(Date, nullable=True)
    local_fato       = Column(String(255), nullable=True)

    # Situação processual
    polo             = Column(String(20), nullable=True)   # reu|vitima|investigado
    preso            = Column(Boolean, default=False)
    tipo_prisao      = Column(String(30), nullable=True)   # preventiva/temporária/em flagrante
    data_prisao      = Column(Date, nullable=True)
    data_alvara      = Column(Date, nullable=True)         # alvará de soltura
    fianca_valor     = Column(Numeric(14, 2), nullable=True)

    # Penas
    artigo_imputado  = Column(String(100), nullable=True)  # ex: CP art. 157 §2º I
    pena_min_anos    = Column(Numeric(3, 1), nullable=True)
    pena_max_anos    = Column(Numeric(3, 1), nullable=True)
    pena_aplicada    = Column(String(60), nullable=True)   # ex: 4 anos regime semiaberto
    sursis           = Column(Boolean, default=False)
    pena_alternativa = Column(Boolean, default=False)

    # ANPP (art. 28-A CPP — desde Pacote Anticrime 2019)
    anpp_proposto    = Column(Boolean, default=False)
    anpp_aceito      = Column(Boolean, nullable=True)
    anpp_condicoes   = Column(Text, nullable=True)

    # Prazos críticos
    data_denuncia          = Column(Date, nullable=True)
    prazo_resposta_acusacao = Column(Date, nullable=True)  # +10 dias úteis
    data_audiencia          = Column(Date, nullable=True)

    resultado        = Column(Text, nullable=True)  # absolvido/condenado/extinção punibilidade
    observacoes      = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="penal")


# ══════════════════════════════════════════════════════════════════════════════
# 4. DIREITO TRABALHISTA (escritório — cliente PF/PJ)
# ══════════════════════════════════════════════════════════════════════════════
class TrabalhistaTipo(str, enum.Enum):
    verbas_rescisorias   = "verbas_rescisorias"    # rescisão sem justa causa
    reconhecimento_vinculo = "reconhecimento_vinculo" # CLT art. 3º
    horas_extras         = "horas_extras"           # CLT art. 59
    insalubridade        = "insalubridade"          # CLT art. 189 + NR-15
    periculosidade       = "periculosidade"         # CLT art. 193 + NR-16
    dano_moral_trab      = "dano_moral_trabalhista"
    assedio_moral        = "assedio_moral"
    assedio_sexual       = "assedio_sexual"          # Lei 10.224/2001
    acidente_trabalho    = "acidente_trabalho"       # Lei 8.213/91 art. 86
    estabilidade_gestante = "estabilidade_gestante"  # ADCT art. 10 II
    rescisao_indireta    = "rescisao_indireta"       # CLT art. 483
    equiparacao_salarial = "equiparacao_salarial"    # CLT art. 461
    adicional_noturno    = "adicional_noturno"       # CLT art. 73
    intervalo_intrajornada = "intervalo_intrajornada" # CLT art. 71
    plr_participacao     = "plr_participacao"        # Lei 10.101/2000
    nulidade_demissao    = "nulidade_demissao"
    outro_trabalhista    = "outro_trabalhista"


class TrabalhistaFase(str, enum.Enum):
    pre_processual         = "pre_processual"        # tentativa extrajudicial
    reclamacao_protocolada = "reclamacao_protocolada"
    audiencia_conciliacao  = "audiencia_conciliacao" # CLT art. 843
    instrucao              = "instrucao"
    alegacoes_finais       = "alegacoes_finais"
    sentenca               = "sentenca"
    recurso_ordinario      = "recurso_ordinario"     # 8 dias CLT art. 895
    embargos_declaracao    = "embargos_declaracao"
    recurso_de_revista     = "recurso_de_revista"    # TST
    liquidacao             = "liquidacao"
    execucao               = "execucao"
    acordo_homologado      = "acordo_homologado"
    encerrado              = "encerrado"


class TrabalhistaCase(Base):
    """
    Satélite de caso trabalhista.
    Prazos críticos (CLT):
      - Reclamação trabalhista: 2 anos da rescisão, 5 anos do direito (CLT art. 11 / Súm. TST 308)
      - Recurso Ordinário: 8 dias corridos (CLT art. 895 I)
      - Depósito recursal RO: simultâneo ao recurso (Súm. TST 245)
      - Embargos declaração: 5 dias (CLT art. 897-A)
    """
    __tablename__ = "trabalhista_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    tipo  = Column(SAEnum(TrabalhistaTipo), nullable=False)
    fase  = Column(SAEnum(TrabalhistaFase), nullable=False, default=TrabalhistaFase.pre_processual)
    polo  = Column(String(20), nullable=True)   # reclamante|reclamado

    # Dados do empregado/empregador
    salario_base          = Column(Numeric(12, 2), nullable=True)
    data_admissao         = Column(Date, nullable=True)
    data_demissao         = Column(Date, nullable=True)
    tipo_rescisao         = Column(String(40), nullable=True)  # sem_justa/justa/indireta/acordo_484a
    cargo                 = Column(String(100), nullable=True)
    cbo                   = Column(String(10), nullable=True)   # código CBO
    regime_contratacao    = Column(String(30), nullable=True)  # CLT/PJ/temporário/doméstico

    # Verbas em disputa
    valor_causa_estimado  = Column(Numeric(14, 2), nullable=True)
    horas_extras_semana   = Column(Numeric(4, 1), nullable=True)
    adicional_percentual  = Column(Numeric(5, 2), nullable=True)  # % insalubridade/periculosidade

    # Dados do acidente (se aplicável)
    data_acidente         = Column(Date, nullable=True)
    cat_emitida           = Column(Boolean, nullable=True)  # CAT — Lei 8.213/91 art. 22
    cid                   = Column(String(10), nullable=True)
    afastamento_dias      = Column(Integer, nullable=True)
    sequela_permanente    = Column(Boolean, default=False)

    # Dano moral
    dano_moral_pedido     = Column(Numeric(14, 2), nullable=True)
    dano_moral_concedido  = Column(Numeric(14, 2), nullable=True)

    # Valores e acordos
    deposito_recursal     = Column(Numeric(12, 2), nullable=True)
    valor_acordo          = Column(Numeric(14, 2), nullable=True)
    valor_condenacao      = Column(Numeric(14, 2), nullable=True)

    # Prazos
    prazo_recurso_ordinario = Column(Date, nullable=True)  # +8 dias da sentença
    data_audiencia_inaugural = Column(Date, nullable=True)

    resultado   = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="trabalhista_esp")


# ══════════════════════════════════════════════════════════════════════════════
# 5. DIREITO ADMINISTRATIVO — multas, servidores, improbidade, contratos públicos
# ══════════════════════════════════════════════════════════════════════════════
class AdminTipo(str, enum.Enum):
    recurso_multa_transito  = "recurso_multa_transito"    # CTB Lei 9.503/97
    recurso_multa_ambiental = "recurso_multa_ambiental"   # Dec. 6.514/08
    recurso_multa_tributaria = "recurso_multa_tributaria" # Lei 9.784/99
    recurso_multa_vigilancia = "recurso_multa_sanitaria"  # Lei 6.437/77 (ANVISA)
    recurso_multa_trabalhista_adm = "recurso_autuacao_mte" # autuação MTe/SRTE
    improbidade_admin       = "improbidade_administrativa" # Lei 8.429/92
    mandado_seguranca       = "mandado_seguranca_admin"    # Lei 12.016/2009
    servidor_publico        = "servidor_publico"           # PAD/sindicância
    desapropriacao          = "desapropriacao"             # DL 3.365/41
    indenizacao_estado      = "indenizacao_estado"         # responsabilidade civil CF art. 37 §6º
    licença_negada          = "licenca_negada_admin"
    outro_admin             = "outro_admin"


class AdminStatus(str, enum.Enum):
    prazo_recurso          = "prazo_recurso"
    recurso_protocolado    = "recurso_protocolado"
    aguardando_julgamento  = "aguardando_julgamento"
    segunda_instancia_adm  = "segunda_instancia_adm"
    judicial               = "judicial"                 # levou ao Judiciário
    encerrado_favoravel    = "encerrado_favoravel"
    encerrado_desfavoravel = "encerrado_desfavoravel"


class AdminCase(Base):
    """
    Satélite de caso administrativo.
    Prazos críticos:
      - Recurso multa trânsito: 30 dias (CTB art. 283 §4º)
      - Recurso administrativo geral (Lei 9.784/99 art. 59): 10 dias
      - MS impetração: 120 dias do ato (Lei 12.016/09 art. 23)
      - Improbidade (ação): 8 anos da prática (Lei 8.429/92 art. 23)
    """
    __tablename__ = "admin_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    tipo   = Column(SAEnum(AdminTipo), nullable=False)
    status = Column(SAEnum(AdminStatus), nullable=False, default=AdminStatus.prazo_recurso)

    # Auto / ato administrativo
    numero_auto_infracao  = Column(String(50), nullable=True)
    orgao_autuador        = Column(String(100), nullable=True)  # DETRAN/IBAMA/MTe/ANVISA…
    data_infracao         = Column(Date, nullable=True)
    data_notificacao      = Column(Date, nullable=True)   # marco para prazo recursal
    codigo_infracao       = Column(String(20), nullable=True)  # ex: CTB art. 218 I

    # Multa
    valor_multa_original  = Column(Numeric(12, 2), nullable=True)
    valor_com_desconto    = Column(Numeric(12, 2), nullable=True)  # pagamento antecipado
    pontuacao_cnh         = Column(Integer, nullable=True)          # pontos CNH (CTB)
    suspensao_cnh         = Column(Boolean, default=False)

    # Prazos recursais
    prazo_recurso_1a_inst = Column(Date, nullable=True)   # 1ª instância administrativa
    prazo_recurso_2a_inst = Column(Date, nullable=True)   # 2ª instância / CETRAN / JARI
    protocolo_recurso     = Column(String(60), nullable=True)

    # Mandado de segurança
    data_ato_coator       = Column(Date, nullable=True)
    prazo_ms              = Column(Date, nullable=True)   # +120 dias
    autoridade_coatora    = Column(String(100), nullable=True)

    # PAD / Servidor público
    numero_pad            = Column(String(40), nullable=True)
    cargo_servidor        = Column(String(100), nullable=True)
    penalidade_imputada   = Column(String(60), nullable=True)   # advertência/suspensão/demissão

    resultado             = Column(Text, nullable=True)
    observacoes           = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="admin_esp")


# ══════════════════════════════════════════════════════════════════════════════
# 6. DIREITO BANCÁRIO E FINANCEIRO
# ══════════════════════════════════════════════════════════════════════════════
class BancarioTipo(str, enum.Enum):
    revisao_juros       = "revisao_contrato_juros"    # Súm. STJ 381, 530; Lei 4.595/64
    negativacao_indevida = "negativacao_indevida"     # CDC art. 43 + Súm. STJ 388
    cobrança_abusiva    = "cobranca_abusiva"
    superendividamento  = "superendividamento"        # Lei 14.181/2021 (art. 54-A CDC)
    consignado_indevido = "consignado_indevido"       # Lei 10.820/2003
    fraude_bancaria     = "fraude_bancaria"           # Súm. STJ 479 — resp objetiva banco
    busca_apreensao     = "busca_apreensao"           # Dec.-Lei 911/69 (alienação fiduciária)
    execucao_bancaria   = "execucao_bancaria"         # CPC art. 784 (título extrajudicial)
    fraude_cartao       = "fraude_cartao_credito"
    pix_golpe           = "pix_golpe"                 # fraudes Pix — Circ. BCB 3.978/20
    limite_conta_fatura = "limite_conta_fatura"        # tarifas abusivas
    leasing_alienacao   = "leasing_alienacao_fiduciaria"
    hipoteca_garantia   = "hipoteca_garantia_real"
    outro_bancario      = "outro_bancario"


class BancarioStatus(str, enum.Enum):
    analise_contrato     = "analise_contrato"
    notificacao_enviada  = "notificacao_enviada"
    negociacao           = "negociacao"
    processual           = "processual"
    acordo               = "acordo"
    encerrado            = "encerrado"


class BancarioCase(Base):
    """
    Satélite de caso bancário/financeiro.
    Prazos críticos:
      - Negativação indevida: prescrição 3 anos (CC art. 206 §3º V + Súm. STJ 149)
      - Busca e apreensão (alienação fiduciária): 5 dias para purga (Dec.-Lei 911/69 art. 3º §2º)
      - Superendividamento (Lei 14.181/21): audiência em 15 dias do protocolo (art. 104-A §1º CDC)
      - Dano moral negativação: Súm. STJ 388 (presumido / in re ipsa)
    """
    __tablename__ = "bancario_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    tipo   = Column(SAEnum(BancarioTipo), nullable=False)
    status = Column(SAEnum(BancarioStatus), nullable=False, default=BancarioStatus.analise_contrato)

    # Dados do contrato
    instituicao_financeira  = Column(String(100), nullable=True)
    numero_contrato         = Column(String(60), nullable=True)
    modalidade_credito      = Column(String(50), nullable=True)  # pessoal/consignado/CDC/leasing/cheque esp.
    data_contrato           = Column(Date, nullable=True)
    valor_contratado        = Column(Numeric(14, 2), nullable=True)
    valor_pago              = Column(Numeric(14, 2), nullable=True)

    # Juros e encargos
    taxa_mensal_contratada  = Column(Numeric(7, 4), nullable=True)  # % ao mês
    taxa_mensal_legal       = Column(Numeric(7, 4), nullable=True)  # referência BCB/média mercado
    cet_contratado          = Column(Numeric(7, 4), nullable=True)  # CET % ao ano (Res. CMN 3.517/07)
    spread_excessivo        = Column(Boolean, default=False)

    # Saldo devedor e revisão
    saldo_devedor_declarado = Column(Numeric(14, 2), nullable=True)
    saldo_devedor_revisado  = Column(Numeric(14, 2), nullable=True)  # após cálculo pericial
    valor_cobrado_indevido  = Column(Numeric(14, 2), nullable=True)

    # Negativação
    negativado              = Column(Boolean, default=False)
    orgao_negativacao       = Column(String(40), nullable=True)  # SPC/Serasa/SCR-BCB
    data_negativacao        = Column(Date, nullable=True)
    valor_negativado        = Column(Numeric(12, 2), nullable=True)
    dano_moral_pedido       = Column(Numeric(12, 2), nullable=True)

    # Superendividamento (Lei 14.181/21)
    superendividamento      = Column(Boolean, default=False)
    renda_mensal            = Column(Numeric(12, 2), nullable=True)
    total_dividas           = Column(Numeric(14, 2), nullable=True)
    minimo_existencial      = Column(Boolean, default=False)  # comprometimento > mín. existencial

    # Busca e apreensão / Execução
    data_notificacao_ba     = Column(Date, nullable=True)   # p/ purga da mora (5 dias)
    prazo_purga             = Column(Date, nullable=True)
    bem_garantia            = Column(String(255), nullable=True)  # veículo/imóvel + identificação

    resultado               = Column(Text, nullable=True)
    observacoes             = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="bancario")
