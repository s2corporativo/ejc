# ── app/services/seed_conhecimento.py ────────────────────────────────────────
# Seed IDEMPOTENTE da Base de Conhecimento (RAG).
#
# "Preenche" a base com conteúdo interno SEGURO e útil desde o primeiro dia:
#   • README de uso da base (guia operacional para a equipe);
#   • Padrão-ouro de redação de peças (regra estrutural do escritório);
#   • Diretrizes internas de análise por área (dos system_prompts existentes);
#   • Modelos de estrutura de documento (templates_documentos.py).
#
# NADA aqui é inventado: são os artefatos internos já versionados no código,
# expostos como documentos de referência consultáveis pela busca semântica e
# pelo RAG das peças/entrevista. Jurisprudência REAL entra pelo importador
# oficial (services/juris_import — LexML/STJ); este módulo apenas OFERECE o
# agendamento opcional de uma importação inicial de temas comuns, com
# tratamento gracioso quando as APIs/fontes estão indisponíveis.
#
# Idempotência: cada documento tem `chave_origem = "ejc_seed:<slug>"` e passa
# por ingestion_service.upsert_documento — reexecutar não duplica ("inalterado")
# e mudanças no conteúdo versionam (migration 068), nunca sobrescrevem.
from __future__ import annotations

import logging
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import upsert_documento

logger = logging.getLogger("ejc.seed_conhecimento")

# Fonte exibida no painel de Conhecimento para todo documento deste seed.
FONTE_SEED = "ejc_seed"

# Categoria dedicada (fora de _RESTRICTED_CATS de ai_service — o material é
# metodologia interna do escritório, não peça de cliente; pode ser recuperado
# por qualquer busca autenticada).
CATEGORIA_REFERENCIA = "referencia_interna"
CATEGORIA_MODELO = "modelo_documento_juridico"

# Temas comuns para a importação inicial OPCIONAL de jurisprudência real
# (LexML/STJ via services/juris_import — dedup idempotente por chave_origem).
TEMAS_JURISPRUDENCIA_INICIAL: list[str] = [
    "dano moral consumidor",
    "responsabilidade civil prestação de serviço",
    "revisional contrato bancário juros",
    "horas extras vínculo empregatício",
    "alimentos guarda compartilhada",
]

_README_BASE = """
BASE DE CONHECIMENTO DO EJC — GUIA DE USO

1. O QUE É. A Base de Conhecimento é o repositório institucional consultado
pela busca semântica (página Conhecimento) e pelo RAG que fundamenta as peças,
dossiês e a Entrevista Inteligente. Todo documento ingerido vira "fonte" que a
IA pode citar — por isso a curadoria importa.

2. COMO ALIMENTAR.
- Upload manual: página Conhecimento → Ingerir (texto, PDF com OCR ou URL).
  Escolha a categoria correta e o nível de confiança (alta/media/baixa).
- Importador de jurisprudência REAL: página Conhecimento → Importar
  Jurisprudência (fontes oficiais LexML/Senado e STJ Dados Abertos). NUNCA
  cadastre jurisprudência manualmente sem conferir no tribunal de origem.
- Google Drive: com GOOGLE_DRIVE_ENABLED=true, a pasta de conhecimento é
  sincronizada por /api/rag/google-drive/sync (somente leitura).
- Destilação de IA: outputs de IA aprovados no HITL podem ser ingeridos via
  "ingerir-ai-log" (gate humano obrigatório).

3. CATEGORIAS PRINCIPAIS. legislacao_*, sumula_*, jurisprudencia_*, doutrina,
tese_vitoriosa, modelo_documento_juridico, precedente_interno (restrita por
cliente), referencia_interna (material metodológico do escritório, como este).

4. CONFIANÇA E GOVERNANÇA. Cada documento carrega confidence_level
(alta|media|baixa|bloqueado), revisável na Curadoria (Governança da IA).
Documento "bloqueado" não alimenta a IA. A busca sempre expõe a confiança da
fonte para o revisor ponderar.

5. BUSCA. A busca é semântica (pgvector + embeddings locais fastembed, sem
API externa) com fusão lexical; se os embeddings estiverem indisponíveis, o
sistema degrada automaticamente para busca textual — nada quebra.

6. VERSIONAMENTO. Reingerir a mesma fonte não duplica: conteúdo idêntico é
ignorado e conteúdo alterado gera NOVA versão, preservando a anterior como
histórico auditável.
"""

_CHECKLIST_CURADORIA = """
CHECKLIST INTERNO — CURADORIA DE CONHECIMENTO (antes de ingerir)

1. FONTE VERIFICÁVEL: o documento tem origem identificável (diário oficial,
   tribunal, doutrina publicada, material interno revisado)? Sem origem clara,
   não ingerir.
2. JURISPRUDÊNCIA: só entra pelo importador oficial (LexML/STJ) ou com ementa
   conferida no site do tribunal — número do processo, órgão julgador e data
   de julgamento presentes. Jurisprudência sem tribunal+data é citação
   bloqueante no gate anti-alucinação.
3. VIGÊNCIA: legislação revogada ou súmula cancelada deve ser marcada com
   confiança "baixa" ou "bloqueado" na Curadoria, nunca "alta".
4. DADOS PESSOAIS (LGPD): material com dados de cliente identificável só nas
   categorias restritas por cliente (precedente_interno com client_id) — nunca
   em categoria aberta.
5. CONFIANÇA: "alta" apenas para fonte oficial conferida ou material interno
   aprovado por sócio; "media" para material útil não conferido; "baixa" para
   rascunhos e apontamentos.
6. TÍTULO: descritivo e pesquisável (ex.: "STJ REsp 1.737.412 — dano moral
   por negativação indevida", não "documento1").
"""


def _doc(slug: str, titulo: str, categoria: str, conteudo: str,
         tribunal: str | None = None) -> dict[str, Any]:
    return {
        "chave_origem": f"ejc_seed:{slug}",
        "titulo": titulo,
        "categoria": categoria,
        "conteudo": conteudo.strip(),
        "tribunal": tribunal,
    }


def montar_documentos_seed() -> list[dict[str, Any]]:
    """Corpus determinístico do seed (puro — sem I/O), 1 dict por documento.

    Importa os prompts/templates internos já existentes no código; qualquer
    reajuste neles reflete aqui automaticamente (e vira nova VERSÃO do
    documento no RAG, graças ao hash do upsert)."""
    from app.services.system_prompts import SYSTEM_PROMPTS
    from app.services.system_prompts.padrao_ouro import PADRAO_OURO_PECA
    from app.services.system_prompts import templates_documentos as tpl

    docs: list[dict[str, Any]] = [
        _doc("readme", "README — Como usar a Base de Conhecimento do EJC",
             CATEGORIA_REFERENCIA, _README_BASE),
        _doc("checklist_curadoria",
             "Checklist interno — curadoria de conhecimento",
             CATEGORIA_REFERENCIA, _CHECKLIST_CURADORIA),
        _doc("padrao_ouro_peca",
             "Padrão-ouro de redação de peças — estrutura obrigatória",
             CATEGORIA_REFERENCIA, PADRAO_OURO_PECA),
    ]

    # Diretrizes internas de análise por área/tarefa (system prompts do Núcleo
    # de IA como documentos de referência para a equipe humana também).
    rotulos = {
        "triagem": "Triagem de atendimento",
        "analise_caso": "Análise estratégica de caso",
        "minutas": "Elaboração de minutas",
        "prazos": "Contagem e gestão de prazos",
        "honorarios": "Honorários advocatícios",
        "ambiental": "Direito Ambiental",
        "consumidor": "Direito do Consumidor",
        "tributario": "Direito Tributário",
        "previdenciario": "Direito Previdenciário",
        "empresarial": "Direito Empresarial",
        "trabalhista": "Direito do Trabalho",
        "criminal": "Direito Penal",
        "familia": "Direito de Família",
        "administrativo": "Direito Administrativo",
        "sucessoes": "Direito das Sucessões",
        "imobiliario": "Direito Imobiliário",
        "constitucional": "Direito Constitucional",
        "juizados": "Juizados Especiais",
        "civel": "Direito Cível",
    }
    for chave, rotulo in rotulos.items():
        prompt = SYSTEM_PROMPTS.get(chave)
        if prompt and len(prompt.strip()) >= 50:
            docs.append(_doc(
                f"diretrizes_{chave}",
                f"Diretrizes internas — {rotulo}",
                CATEGORIA_REFERENCIA, prompt,
            ))

    # Modelos de ESTRUTURA de documento (não são peças prontas — são o
    # esqueleto padronizado do escritório por tipo de documento).
    modelos = {
        "peticao_inicial": ("Modelo de estrutura — Petição inicial",
                            getattr(tpl, "TEMPLATE_PETICAO_INICIAL", "")),
        "contestacao": ("Modelo de estrutura — Contestação",
                        getattr(tpl, "TEMPLATE_CONTESTACAO", "")),
        "parecer": ("Modelo de estrutura — Parecer jurídico",
                    getattr(tpl, "TEMPLATE_PARECER", "")),
        "notificacao": ("Modelo de estrutura — Notificação extrajudicial",
                        getattr(tpl, "TEMPLATE_NOTIFICACAO", "")),
        "relatorio_caso": ("Modelo de estrutura — Relatório de caso ao cliente",
                           getattr(tpl, "TEMPLATE_RELATORIO_CASO", "")),
        "proposta_honorarios": ("Modelo de estrutura — Proposta de honorários",
                                getattr(tpl, "TEMPLATE_PROPOSTA_HONORARIOS", "")),
        "defesa_ibama": ("Modelo de estrutura — Defesa administrativa IBAMA",
                         getattr(tpl, "TEMPLATE_DEFESA_IBAMA", "")),
    }
    for slug, (titulo, conteudo) in modelos.items():
        if conteudo and len(conteudo.strip()) >= 50:
            docs.append(_doc(f"modelo_{slug}", titulo, CATEGORIA_MODELO, conteudo))

    return docs


async def executar_seed_conhecimento(
    db: AsyncSession, *, embutir_vetores: bool = True
) -> dict[str, Any]:
    """Aplica o seed na base (idempotente). NÃO comita — o chamador decide.

    Retorna contadores {total, novos, atualizados, inalterados} + detalhe por
    documento. Com embeddings indisponíveis os docs ficam "pendente" e são
    vetorizados depois (scripts/vetorizar_documentos.py ou reconciliação) —
    a busca textual já os encontra imediatamente (degradação graciosa)."""
    docs = montar_documentos_seed()
    contagem = {"novo": 0, "atualizado": 0, "inalterado": 0}
    detalhe: list[dict[str, str]] = []
    for d in docs:
        resultado = await upsert_documento(
            db,
            titulo=d["titulo"],
            categoria=d["categoria"],
            conteudo=d["conteudo"],
            chave_origem=d["chave_origem"],
            fonte=FONTE_SEED,
            tribunal=d.get("tribunal"),
            extra={"rag_status": "aprovado", "origem": "seed_interno_curado"},
            confianca="alta",   # material interno curado do escritório
            embutir_vetores=embutir_vetores,
        )
        contagem[resultado] = contagem.get(resultado, 0) + 1
        detalhe.append({"chave_origem": d["chave_origem"], "resultado": resultado})
    resumo = {
        "total": len(docs),
        "novos": contagem.get("novo", 0),
        "atualizados": contagem.get("atualizado", 0),
        "inalterados": contagem.get("inalterado", 0),
        "documentos": detalhe,
    }
    logger.info(
        "[SeedConhecimento] total=%s novos=%s atualizados=%s inalterados=%s",
        resumo["total"], resumo["novos"], resumo["atualizados"], resumo["inalterados"],
    )
    return resumo


def agendar_jurisprudencia_inicial(
    background_tasks: BackgroundTasks,
    user_id: str | None,
    user_role: str | None,
) -> list[dict[str, str]]:
    """Agenda (opcional) a importação inicial de jurisprudência REAL para os
    temas comuns do escritório, usando o importador oficial (LexML/STJ).

    Gracioso por construção: fontes desabilitadas (JURIS_IMPORT_FONTES) ou
    módulo indisponível → retorna lista vazia, sem exceção. Cada job roda em
    background e NUNCA levanta (executar_importacao captura tudo); dedup por
    chave_origem torna reexecuções inofensivas."""
    jobs: list[dict[str, str]] = []
    try:
        from uuid import uuid4
        from app.services.juris_import import FONTES
        from app.services.juris_import.ingest import executar_importacao

        fontes_ativas = [slug for slug, f in FONTES.items() if f.get("enabled")]
        if not fontes_ativas:
            logger.info("[SeedConhecimento] nenhuma fonte de jurisprudência habilitada — importação inicial pulada")
            return jobs
        for fonte in fontes_ativas:
            for tema in TEMAS_JURISPRUDENCIA_INICIAL:
                job_id = str(uuid4())
                background_tasks.add_task(
                    executar_importacao, job_id, fonte, tema,
                    None, 10, user_id, user_role,
                )
                jobs.append({"job_id": job_id, "fonte": fonte, "consulta": tema})
    except Exception as e:  # noqa: BLE001 — seed é best-effort, nunca derruba o request
        logger.warning("[SeedConhecimento] importação inicial de jurisprudência indisponível: %s", e)
    return jobs
