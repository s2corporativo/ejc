"""Saúde das fontes de ingestão aferida por RESULTADO, não por execução.

O problema que este módulo resolve
──────────────────────────────────
O monitoramento existente pergunta *"o job rodou?"* — compara `ultima_execucao`
com uma idade máxima e olha `ultimo_status`. Um job que roda pontualmente e
entrega zero passa nos dois testes. Foi exatamente assim que a captura do DJEN
reportou "sucesso" durante meses sem nunca ter registrado uma intimação, com três
painéis distintos confirmando que estava tudo bem.

A diferença entre descobrir isso em um dia ou em um mês é, no caso do DJEN, a
diferença entre perceber e perder um prazo.

O que muda
──────────
Toda fonte passa a declarar o que significa sucesso **em termos de saída**, e o
veredito considera quatro situações que o monitoramento por cadência não vê:

  · `nunca_produziu`   — já executou e o acervo continua em zero. Não é uma fonte
                         lenta: é uma fonte que nunca funcionou.
  · `parou_de_produzir`— fonte com histórico que passou N execuções seguidas sem
                         trazer nada. O caso clássico de coletor que quebrou
                         quando o site de origem mudou o HTML.
  · `erro_sem_diagnostico` — terminou em erro e não gravou a mensagem. Pior que
                         o erro: não há por onde começar a investigar. É o estado
                         em que a fonte `anpd` foi encontrada.
  · `dormente`         — fonte ativa que parou de ser executada.

Funções puras, sem I/O: recebem o estado da fonte e devolvem o veredito. Isso
mantém a regra testável sem banco — e a regra é o que precisa de teste, não o
SELECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

#: A partir de quantas execuções seguidas sem produzir nada uma fonte com
#: histórico é considerada quebrada. Três é deliberadamente baixo: fonte que
#: passa três coletas sem nada tem muito mais chance de estar quebrada do que de
#: estar num período genuinamente vazio — e o custo de investigar em falso é
#: pequeno perto do custo de perder um prazo.
LIMITE_EXECUCOES_ZERADAS = 3

#: Horas sem executar a partir das quais uma fonte ativa é considerada dormente.
#: Cobre folga de fim de semana em job semanal sem gerar alarme falso.
MAX_HORAS_SEM_EXECUTAR = 24 * 8

SEVERIDADE = {
    "ok": 0,
    "dormente": 1,
    "parou_de_produzir": 2,
    "erro_sem_diagnostico": 3,
    "erro": 3,
    "nunca_produziu": 3,
}

#: Vereditos que exigem ação humana — o que o painel deve destacar.
CRITICOS = {"nunca_produziu", "erro_sem_diagnostico", "erro", "parou_de_produzir"}


@dataclass(frozen=True)
class SaudeFonte:
    """Veredito de uma fonte. `acao` diz o que fazer, não só o que houve."""

    situacao: str
    critico: bool
    motivo: str
    acao: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "situacao": self.situacao,
            "critico": self.critico,
            "severidade": SEVERIDADE.get(self.situacao, 0),
            "motivo": self.motivo,
            "acao": self.acao,
        }


def _idade_horas(quando: datetime | None, agora: datetime) -> float | None:
    if quando is None:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    return (agora - quando).total_seconds() / 3600.0


def avaliar_saude_fonte(
    *,
    slug: str,
    ativo: bool,
    ultima_execucao: datetime | None,
    ultimo_status: str | None,
    ultimo_erro: str | None,
    registros_novos: int | None,
    registros_total: int | None,
    execucoes_zeradas_consecutivas: int | None,
    agora: datetime | None = None,
    limite_zeradas: int = LIMITE_EXECUCOES_ZERADAS,
    max_horas_sem_executar: float = MAX_HORAS_SEM_EXECUTAR,
) -> SaudeFonte:
    """Veredito de UMA fonte, na ordem de gravidade.

    A ordem importa: uma fonte que nunca produziu nada e ainda por cima está
    dormente deve ser reportada pelo problema maior. Reportar "dormente" nesse
    caso subestimaria — foi o que a auditoria encontrou nos três importadores
    `juris_import_*`, marcados como ativos, dormentes há sete dias e com zero
    registros em toda a história.
    """
    agora = agora or datetime.now(timezone.utc)
    novos = int(registros_novos or 0)
    total = int(registros_total or 0)
    zeradas = int(execucoes_zeradas_consecutivas or 0)
    status = (ultimo_status or "").strip().lower()
    ja_executou = ultima_execucao is not None

    if not ativo:
        return SaudeFonte(
            situacao="ok",
            critico=False,
            motivo="Fonte desativada — não é esperado que produza.",
            acao="Nenhuma. Reative a fonte se voltar a ser necessária.",
        )

    # 1. Erro sem mensagem: pior que o erro, porque não há por onde começar.
    if status == "erro" and not (ultimo_erro or "").strip():
        return SaudeFonte(
            situacao="erro_sem_diagnostico",
            critico=True,
            motivo=(
                "A execução falhou e nenhuma mensagem foi gravada — impossível "
                "diagnosticar pelo painel."
            ),
            acao=(
                f"Corrija a captura da exceção do ingestor '{slug}' antes de "
                "investigar a falha em si."
            ),
        )

    if status == "erro":
        return SaudeFonte(
            situacao="erro",
            critico=True,
            motivo=f"Última execução falhou: {(ultimo_erro or '').strip()[:200]}",
            acao="Investigue o erro registrado e execute a fonte sob demanda.",
        )

    # 2. Nunca produziu nada. Não é lentidão — é uma fonte que nunca funcionou.
    if ja_executou and total <= 0 and novos <= 0:
        return SaudeFonte(
            situacao="nunca_produziu",
            critico=True,
            motivo=(
                "A fonte já executou e o acervo continua em zero. Reportar "
                "'sucesso' aqui é falso positivo."
            ),
            acao=(
                f"Verifique se o ingestor '{slug}' realmente chega à origem e se "
                "o parser reconhece o formato atual. Instrumente a contagem de "
                "itens BRUTOS recebidos antes do parsing."
            ),
        )

    # 3. Tinha histórico e parou. Coletor que quebrou quando a origem mudou.
    if zeradas >= limite_zeradas:
        return SaudeFonte(
            situacao="parou_de_produzir",
            critico=True,
            motivo=(
                f"{zeradas} execuções consecutivas sem nenhum registro novo, "
                f"apesar de a fonte já ter produzido antes."
            ),
            acao=(
                "Compare com a origem: mudança de layout ou de contrato da API "
                "costuma zerar a coleta sem gerar erro."
            ),
        )

    # 4. Ativa e parada.
    idade = _idade_horas(ultima_execucao, agora)
    if idade is None:
        return SaudeFonte(
            situacao="dormente",
            critico=False,
            motivo="Fonte ativa que nunca foi executada.",
            acao="Confirme se o job está agendado.",
        )
    if idade > max_horas_sem_executar:
        return SaudeFonte(
            situacao="dormente",
            critico=False,
            motivo=f"Ativa, mas sem executar há {idade:.0f}h.",
            acao="Confirme se o scheduler está de pé e se o job continua agendado.",
        )

    return SaudeFonte(
        situacao="ok",
        critico=False,
        motivo=f"Última execução produziu {novos} registro(s) novo(s).",
        acao="Nenhuma.",
    )


def avaliar_fontes(fontes, agora: datetime | None = None) -> dict[str, SaudeFonte]:
    """Veredito de várias fontes, indexado por slug."""
    agora = agora or datetime.now(timezone.utc)
    return {
        f.slug: avaliar_saude_fonte(
            slug=f.slug,
            ativo=bool(f.ativo),
            ultima_execucao=f.ultima_execucao,
            ultimo_status=f.ultimo_status,
            ultimo_erro=f.ultimo_erro,
            registros_novos=f.registros_novos,
            registros_total=f.registros_total,
            execucoes_zeradas_consecutivas=getattr(
                f, "execucoes_zeradas_consecutivas", 0
            ),
            agora=agora,
        )
        for f in fontes
    }


def resumir(saudes: dict[str, SaudeFonte]) -> dict[str, Any]:
    """Resumo para o painel: o que precisa de ação, nomeado.

    Devolve a lista de slugs críticos em vez de só a contagem — um número não
    diz por onde começar, e foi a ausência dessa lista que deixou o DJEN passar
    despercebido entre fontes verdes.
    """
    criticas = sorted(s for s, v in saudes.items() if v.critico)
    return {
        "total": len(saudes),
        "criticas": criticas,
        "total_criticas": len(criticas),
        "status_geral": "critico" if criticas else "ok",
    }
