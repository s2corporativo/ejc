"""
IA de Análise de Sentimento de Magistrados — EJC v3.0
Identifica tendências e "humor" decisório em tempo real.

Auditoria 2026-07-15 (relatório final do Núcleo Único de IA, seção 13, item 1):
sanitizado pela barreira do `ai_brain`, mas sem `db`/`user` — logo sem AILog.
`db`/`user` agora são opcionais (mesma regra do `audit_logger`: sem os dois,
não há como auditar, e a geração segue igual, só sem trilha).
"""
from app.core.ai_brain import ai_brain
from app.services.sanitizer import sanitizar_pii


class SentimentoMagistrado:
    def __init__(self):
        self.ai = ai_brain

    async def analisar_tendencia(
        self, ultimas_decisoes: list, *, db=None, user=None, case_id: str | None = None,
    ):
        """
        Analisa o tom das últimas decisões para identificar rigor ou flexibilidade.
        """
        texto_consolidado = "\n".join(ultimas_decisoes[:10])
        prompt = f"""
        Analise o padrão destas últimas 10 decisões do magistrado:
        {texto_consolidado}

        Classifique:
        1. Tendência Atual (Rigorosa / Flexível / Neutra).
        2. Temas Sensíveis (O que ele mais tem negado?).
        3. Recomendação de Tom para a Petição (Agressivo / Conciliador / Estritamente Técnico).
        """
        r = await self.ai.generate_com_metadados(prompt, "secundario")

        if db is not None and user is not None:
            from app.services.ai.core.audit_logger import registrar
            from app.services.system_prompts import TarefaIA

            prompt_sanitizado, pii_removida = sanitizar_pii(prompt)
            # Erro de gravação PROPAGA (mesmo invariante de audit_logger.registrar/
            # orchestrator.run): IA sem trilha de auditoria deve falhar, não
            # responder em silêncio sem log.
            await registrar(
                db, user=user, tarefa=TarefaIA.ANALISE_CASO, case_id=case_id,
                prompt_sanitizado=prompt_sanitizado, pii_removida=pii_removida,
                resposta=r["texto"], modelo=r["modelo"],
            )
        return r["texto"]

sentimento_ia = SentimentoMagistrado()
