"""
Simulador War Room — EJC v3.0
Simula o "Advogado da Parte Contrária" para blindagem de teses.

Auditoria 2026-07-15 (relatório final do Núcleo Único de IA, seção 13, item 1):
este service passa pela sanitização de PII (dentro de `ai_brain`), mas até então
não recebia `db`/`user` e por isso NÃO gravava AILog — nenhuma trilha de
auditoria/custo para chamadas de IA usadas no dia a dia do escritório. `db` e
`user` agora são opcionais: se o chamador não os fornecer (ex.: uso interno sem
sessão), o comportamento de geração é IDÊNTICO ao anterior, só que sem log
(mesma regra de `audit_logger.registrar`, que também aceita None).
"""
from app.core.ai_brain import ai_brain
from app.services.sanitizer import sanitizar_pii


class WarRoom:
    def __init__(self):
        self.ai = ai_brain

    async def _registrar_auditoria(self, *, db, user, case_id, prompt_bruto, resultado, modelo):
        """AILog via a mesma ponte usada pelo orchestrator (auditoria, não IA nova).

        Sem db/user, `registrar()` já retorna None (uso interno sem sessão).
        QUANDO db/user são fornecidos, erro de gravação PROPAGA — mesmo
        invariante documentado em `audit_logger.registrar`/`orchestrator.run`:
        IA sem trilha de auditoria deve falhar, não responder em silêncio sem
        log (não é aceitável engolir a exceção aqui).
        """
        if db is None or user is None:
            return None
        from app.services.ai.core.audit_logger import registrar
        from app.services.system_prompts import TarefaIA

        prompt_sanitizado, pii_removida = sanitizar_pii(prompt_bruto)
        return await registrar(
            db, user=user, tarefa=TarefaIA.ANALISE_CASO, case_id=case_id,
            prompt_sanitizado=prompt_sanitizado, pii_removida=pii_removida,
            resposta=resultado, modelo=modelo,
        )

    async def simular_contestacao(
        self, peticao_inicial: str, *, db=None, user=None, case_id: str | None = None,
    ):
        """
        Gera uma contra-argumentação agressiva para testar a robustez da inicial.
        """
        prompt = f"""
        Você é o Advogado da Parte Contrária, altamente agressivo e técnico.
        Seu objetivo é DESTRUIR esta petição inicial.
        Aponte:
        1. Nulidades processuais.
        2. Contradições fáticas.
        3. Jurisprudência defensiva (que derruba a tese).
        4. Falta de provas essenciais.

        Petição Inicial: {peticao_inicial}

        Retorne um relatório de vulnerabilidades.
        """
        r = await self.ai.generate_com_metadados(prompt, "principal")
        await self._registrar_auditoria(
            db=db, user=user, case_id=case_id,
            prompt_bruto=prompt, resultado=r["texto"], modelo=r["modelo"],
        )
        return r["texto"]

    async def preparar_replica_blindada(
        self, contestacao_adversaria: str, tese_original: str,
        *, db=None, user=None, case_id: str | None = None,
    ):
        """
        Sugere argumentos para a réplica com base nos ataques identificados.
        """
        prompt = f"""
        Com base nesta contestação: {contestacao_adversaria}
        E na nossa tese original: {tese_original}

        Sugira 3 argumentos de blindagem para a réplica que anulem os ataques da contraparte.
        """
        r = await self.ai.generate_com_metadados(prompt, "secundario")
        await self._registrar_auditoria(
            db=db, user=user, case_id=case_id,
            prompt_bruto=prompt, resultado=r["texto"], modelo=r["modelo"],
        )
        return r["texto"]

war_room = WarRoom()
