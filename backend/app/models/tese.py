# ── app/models/tese.py ────────────────────────────────────────────────────────
# Banco de Teses Jurídicas — repositório institucional de argumentos vencedores.
# Integrado ao RAG e à IA para reaproveitamento inteligente.
from __future__ import annotations
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, DateTime, ForeignKey, Enum as SAEnum,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class TeseTipo(str, enum.Enum):
    escritorio   = "escritorio"    # elaborada internamente
    sugerida_ia  = "sugerida_ia"  # gerada pela IA e validada
    doutrina     = "doutrina"     # fundamento doutrinário
    jurisprudencia = "jurisprudencia"  # baseada em julgado
    externa      = "externa"      # copiada de outro escritório / publicação


class TeseStatus(str, enum.Enum):
    rascunho  = "rascunho"
    ativa     = "ativa"
    arquivada = "arquivada"


class Tese(Base):
    __tablename__ = "teses"

    id           = Column(String(36), primary_key=True)
    titulo       = Column(String(300), nullable=False)
    descricao    = Column(Text, nullable=False)
    fundamentacao = Column(Text)           # artigos, súmulas, princípios
    jurisprudencia = Column(Text)          # julgados de suporte
    contra_argumento = Column(Text)        # o que o adversário pode responder
    area_juridica = Column(String(60))     # trabalhista, civel, ambiental...
    tribunal     = Column(String(120))     # ex: TRT-3, TJMG, STJ
    magistrado   = Column(String(200))     # magistrado associado (analytics)
    tags         = Column(Text)            # CSV: "responsabilidade,consumidor"
    observacoes  = Column(Text)

    # ── Ficha viva (§5) ──────────────────────────────────────────────────────
    # QUANDO a ficha se aplica. Era o que faltava para o catálogo sair de
    # "biblioteca que alguém consulta" para "ficha que o sistema oferece na
    # hora certa": sem gatilho, casar tese com caso depende de o advogado já
    # saber que a tese existe. Lista de strings em JSONB (ex.: ["contrato de
    # adesão", "cobrança após quitação"]) — texto livre de propósito nesta
    # versão: o vocabulário certo só aparece depois de uso real, e cristalizá-lo
    # agora num enum seria adivinhação.
    gatilhos     = Column(JSONB, nullable=False, default=list, server_default="[]")
    # Versão CORRENTE da ficha. O histórico vive em `tese_versoes`; este número
    # é o ponteiro para a última fotografia gravada.
    versao       = Column(Integer, nullable=False, default=1, server_default="1")

    tipo         = Column(SAEnum(TeseTipo),   nullable=False, default=TeseTipo.escritorio)
    status       = Column(SAEnum(TeseStatus), nullable=False, default=TeseStatus.ativa)

    # Métricas de desempenho
    vezes_usada  = Column(Integer, default=0, nullable=False)
    vezes_venceu = Column(Integer, default=0, nullable=False)
    vezes_perdeu = Column(Integer, default=0, nullable=False)
    taxa_sucesso = Column(Float)           # calculada: vezes_venceu/vezes_usada

    # Metadados
    created_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    deleted_at   = Column(DateTime(timezone=True), nullable=True)  # soft-delete

    def __repr__(self):
        return f"<Tese {self.titulo[:40]}>"


class TeseCasoLink(Base):
    """Vínculo entre tese e caso (N:N) + resultado da aplicação."""
    __tablename__ = "tese_caso_links"

    id       = Column(String(36), primary_key=True)
    tese_id  = Column(String(36), ForeignKey("teses.id",  ondelete="CASCADE"), nullable=False)
    case_id  = Column(String(36), ForeignKey("cases.id",  ondelete="CASCADE"), nullable=False)
    resultado = Column(String(20))   # procedente | improcedente | acordo | pendente
    observacao = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


# ═══════════════════════════════════════════════════════════════════════════════
# FICHA VIVA (Legal Drafting 2.0 §5 — "LEGAL KNOWLEDGE SKILLS")
#
# A missão pedia quatro tabelas novas: LegalSkillVersion, LegalSkillSource,
# LegalSkillOverride e LegalSkillCaseUsage. Elas NÃO foram criadas com esses
# nomes, e a razão está escrita no ledger de migrations do próprio repositório:
#
#   "A fonte de verdade é `teses` + `tese_caso_links`. Não criar `legal_theses`,
#    `teses_juridicas`, `teses_v2`, `teses_v4` ou outro banco paralelo. Qualquer
#    evolução deve estender a estrutura canônica de forma aditiva."
#
# `Tese` JÁ é a ficha viva do catálogo de habilidades jurídicas: título,
# `fundamentacao` (artigos/súmulas/princípios), `jurisprudencia` (julgados de
# suporte), `contra_argumento` (o que o adversário responde), área, tribunal,
# tags e — o mais difícil de obter — `vezes_venceu`/`vezes_perdeu`/`taxa_sucesso`
# MEDIDOS em casos reais. Um catálogo paralelo nasceria com confiança declarada
# em vez de medida, e as duas taxas divergiriam no primeiro mês.
#
# O mapeamento efetivo:
#
#   LegalSkillCaseUsage → `TeseCasoLink`   (JÁ EXISTIA, sem mudança)
#   LegalSkillVersion   → `TeseVersao`     (novo — histórico IMUTÁVEL da ficha)
#   LegalSkillSource    → `TeseFonte`      (novo — cada elemento da ficha ligado
#                                           a uma fonte REAL e rastreável)
#   LegalSkillOverride  → `TeseOverride`   (novo — decisão humana que afasta a
#                                           ficha num caso concreto)
#   gatilhos            → `Tese.gatilhos`  (novo — quando a ficha se aplica)
#
# Tipos String + domínio validado no service: mesmo trade-off de matriz_teses.py
# (sem ENUM nativo do Postgres, mudanças ficam aditivas).
# ═══════════════════════════════════════════════════════════════════════════════

# Que parte da ficha a fonte lastreia. Validado no service.
ELEMENTOS_FONTE: tuple[str, ...] = (
    "fundamentacao",     # artigo de lei, súmula, princípio
    "jurisprudencia",    # julgado de suporte
    "contra_argumento",  # julgado/norma que o adversário invocará
    "gatilho",           # o que caracteriza a aplicação da ficha
)

# Espelha `matriz_teses.STATUS_VERIFICACAO` de propósito: a verificação da fonte
# é a MESMA pergunta, e dois vocabulários divergiriam nos relatórios.
STATUS_FONTE: tuple[str, ...] = ("nao_verificada", "verificada", "nao_encontrada")

# Por que a ficha foi afastada num caso. Validado no service.
MOTIVOS_OVERRIDE: tuple[str, ...] = (
    "fato_distinto",        # os fatos do caso não casam com o gatilho
    "jurisprudencia_virou", # a orientação mudou depois da ficha
    "estrategia",           # decisão tática do advogado neste caso
    "erro_na_ficha",        # a ficha está errada — vira revisão do catálogo
    "outro",
)


class TeseVersao(Base):
    """Fotografia IMUTÁVEL da ficha a cada alteração (§5 — LegalSkillVersion).

    Sem histórico, uma peça protocolada em março não pode ser explicada em
    outubro: a ficha que a fundamentou já mudou, e não há como saber o que ela
    dizia. Isto é auditoria de fundamentação, não conveniência — é o que permite
    responder "com base em quê o escritório sustentou isto naquele dia".

    NUNCA sofre UPDATE: uma correção gera uma versão nova. `conteudo` guarda o
    snapshot inteiro em JSONB (e não colunas espelhadas) justamente para que
    acrescentar campo à ficha no futuro não invalide o histórico já gravado.
    """
    __tablename__ = "tese_versoes"

    id       = Column(String(36), primary_key=True)
    tese_id  = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    versao   = Column(Integer, nullable=False)      # 1, 2, 3… único por tese
    conteudo = Column(JSONB, nullable=False)        # snapshot completo da ficha
    # O QUE mudou e POR QUÊ — a pergunta que o histórico existe para responder.
    resumo_mudanca = Column(Text, nullable=True)

    criado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    criado_em  = Column(DateTime(timezone=True), server_default=func.now(),
                        nullable=False)

    __table_args__ = (
        UniqueConstraint("tese_id", "versao", name="uq_tese_versoes_tese_versao"),
    )


class TeseFonte(Base):
    """Lastro REAL de um elemento da ficha (§5 — LegalSkillSource).

    Hoje `Tese.fundamentacao` e `Tese.jurisprudencia` são texto livre: a ficha
    afirma "Súmula 297/TST" e nada no sistema sabe se essa súmula existe, se
    continua vigente, ou de onde a afirmação veio. Esta tabela dá a cada
    elemento uma fonte rastreável e um status de verificação.

    `trecho` é OBRIGATÓRIO pelo mesmo motivo de `AuthorityRecord.trecho`: uma
    fonte sem o texto que ela diz não é verificável, e uma referência solta é
    exatamente o formato de uma citação alucinada. A invariante
    "verificada ⇒ tem referência" é validada no service, espelhando a regra
    "verificada ⇒ fonte_oficial" que a Matriz de Teses já aplica.

    Aponta para `knowledge_docs` (base curada) OU `authority_records`
    (precedente colhido num caso) — ambos opcionais, porque uma fonte pode ser
    uma referência externa ainda não ingerida; nesse caso fica `nao_verificada`.
    """
    __tablename__ = "tese_fontes"

    id      = Column(String(36), primary_key=True)
    tese_id = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    elemento = Column(String(20), nullable=False)   # ELEMENTOS_FONTE

    referencia = Column(String(300), nullable=False)  # "Súmula 297/TST", "art. 7º, XXIX CF"
    trecho     = Column(Text, nullable=False)         # texto REAL da fonte
    fonte_url  = Column(String(500), nullable=True)   # link oficial, quando houver

    # Vínculos com o que o EJC já guarda (nenhum obrigatório).
    knowledge_doc_id   = Column(String(36), nullable=True, index=True)
    authority_record_id = Column(String(36),
                                 ForeignKey("authority_records.id", ondelete="SET NULL"),
                                 nullable=True)

    status_verificacao = Column(String(20), nullable=False, default="nao_verificada")
    verificado_em      = Column(DateTime(timezone=True), nullable=True)

    criado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    criado_em  = Column(DateTime(timezone=True), server_default=func.now(),
                        nullable=False)


class TeseOverride(Base):
    """Decisão humana que AFASTA a ficha num caso concreto (§5 —
    LegalSkillOverride).

    Sem isto, o advogado que não segue a ficha simplesmente não a usa, e o
    catálogo nunca fica sabendo: a ficha continua parecendo boa porque só é
    medida quando é usada. Registrar a recusa é o que transforma o catálogo em
    ficha VIVA — `erro_na_ficha` repetido é sinal de revisão, e `fato_distinto`
    repetido é sinal de gatilho mal escrito.

    Não altera a ficha nem as métricas de vitória/derrota: aquelas medem
    RESULTADO de aplicação (`tese_caso_links`); esta mede NÃO-aplicação.
    """
    __tablename__ = "tese_overrides"

    id      = Column(String(36), primary_key=True)
    tese_id = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    # Versão da ficha que foi afastada: se a ficha mudar depois, o registro
    # continua dizendo o que foi recusado de fato.
    versao_tese = Column(Integer, nullable=True)

    motivo       = Column(String(30), nullable=False)   # MOTIVOS_OVERRIDE
    justificativa = Column(Text, nullable=False)        # obrigatória (auditoria)

    criado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    criado_em  = Column(DateTime(timezone=True), server_default=func.now(),
                        nullable=False)
