# ── app/core/degradacao.py ───────────────────────────────────────────────────
# Degradação POR SEÇÃO em respostas agregadas (padrão único do EJC).
#
# Problema que isto resolve: uma tela consolidada (dossiê do cliente, relatório
# financeiro, painel) monta N agregações independentes. Sem isolamento, UMA
# consulta que falha derruba a resposta inteira em 500 e a tela não abre — foi
# exatamente o que a auditoria reproduziu em `/clients/{id}/dossie` e em
# `/clients/{id}/relatorio-financeiro`.
#
# Regra: cada seção roda isolada. Falhou → a seção vem com o valor neutro
# (lista/dict vazio), o nome dela entra em `secoes_indisponiveis` e o erro vai
# para o log sanitizado + Sentry. O resto da tela abre. Nunca falha silenciosa:
# o cliente da API sabe QUAL seção faltou e pode dizer isso ao usuário.
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, TypeVar

from app.core.log_sanitizer import safe_exception_log

logger = logging.getLogger("ejc.degradacao")

T = TypeVar("T")


class ColetorDeSecoes:
    """Acumula seções de uma resposta agregada, isolando a falha de cada uma.

    Uso:

        secoes = ColetorDeSecoes("dossie_cliente")
        casos = await secoes.tentar("casos", carregar_casos(), padrao=[])
        ...
        return {"casos": casos, **secoes.rodape()}

    `rodape()` devolve `{"secoes_indisponiveis": [...]}` — sempre presente, para
    o consumidor não precisar checar a existência da chave.
    """

    def __init__(self, contexto: str, db: Any | None = None) -> None:
        self.contexto = contexto
        # Sessão a rolar de volta quando uma seção falha: no PostgreSQL, o erro
        # de UMA query aborta a transação inteira e TODA seção seguinte falharia
        # com "current transaction is aborted". Sem o rollback, isolar a seção
        # não isolaria nada — a primeira falha ainda esvaziaria a tela.
        self.db = db
        self.indisponiveis: list[str] = []

    async def tentar(
        self,
        nome: str,
        coro: Awaitable[T],
        *,
        padrao: T,
    ) -> T:
        """Executa a seção; devolve `padrao` e registra a falha se ela quebrar."""
        try:
            return await coro
        except Exception as e:  # noqa: BLE001 — isolar a seção é o objetivo
            self.registrar_falha(nome, e)
            await self._recuperar_sessao()
            return padrao

    async def _recuperar_sessao(self) -> None:
        if self.db is None:
            return
        try:
            await self.db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug(
                f"[{self.contexto}] rollback pós-falha não concluiu (ignorado)",
                exc_info=True,
            )

    def registrar_falha(self, nome: str, exc: Exception) -> None:
        """Marca a seção como indisponível e reporta (log + Sentry)."""
        if nome not in self.indisponiveis:
            self.indisponiveis.append(nome)
        logger.warning(
            f"[{self.contexto}] seção '{nome}' indisponível — resposta degradada",
            extra=safe_exception_log(exc),
        )
        _reportar_sentry(exc, self.contexto, nome)

    def rodape(self) -> dict[str, Any]:
        return {"secoes_indisponiveis": list(self.indisponiveis)}


def _reportar_sentry(exc: Exception, contexto: str, secao: str) -> None:
    """Envia ao Sentry SE houver coletor ativo. Nunca levanta: a degradação não
    pode ser derrubada pela própria observabilidade."""
    try:
        from app.core.observability import coletor_erros_ativo

        if not coletor_erros_ativo():
            return
        import sentry_sdk

        # sentry-sdk 2.x: `new_scope()` (o `push_scope()` do 1.x está depreciado).
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("degradacao.contexto", contexto)
            scope.set_tag("degradacao.secao", secao)
            sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        logger.debug("Falha ao reportar degradação ao Sentry (ignorada)", exc_info=True)


def executar_secao(
    coletor: ColetorDeSecoes,
    nome: str,
    fn: Callable[[], T],
    *,
    padrao: T,
) -> T:
    """Variante síncrona de `ColetorDeSecoes.tentar` (cálculo em memória que
    depende de dados possivelmente ausentes)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        coletor.registrar_falha(nome, e)
        return padrao
