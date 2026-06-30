# ── app/services/ingestors/stj.py ────────────────────────────────────────────
# Ingestor de jurisprudência do STJ via Portal de Dados Abertos (CKAN).
# Fonte oficial e gratuita de TEXTO de jurisprudência superior (a lacuna que o
# DataJud não cobre). Usa os "espelhos de acórdãos" — arquivos JSON mensais por
# órgão julgador, com EMENTA, tese jurídica, relator e referências legislativas.
#
# Estratégia: por execução, ingere o arquivo MENSAL MAIS RECENTE de cada órgão.
# Dedup por numeroRegistro evita reingestão. Conteúdo embebido = ementa + tese
# + dispositivos citados (partes juridicamente citáveis), NÃO o inteiro teor da
# decisão (volumoso e de baixo ganho semântico).
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.ingestao.stj")

CKAN = "https://dadosabertos.web.stj.jus.br/api/3/action"

# Órgãos julgadores (datasets CKAN). Corte Especial + 3 Seções + 6 Turmas.
ORGAOS = [
    "espelhos-de-acordaos-corte-especial",
    "espelhos-de-acordaos-primeira-secao",
    "espelhos-de-acordaos-segunda-secao",
    "espelhos-de-acordaos-terceira-secao",
    "espelhos-de-acordaos-primeira-turma",
    "espelhos-de-acordaos-segunda-turma",
    "espelhos-de-acordaos-terceira-turma",
    "espelhos-de-acordaos-quarta-turma",
    "espelhos-de-acordaos-quinta-turma",
    "espelhos-de-acordaos-sexta-turma",
]

MAX_POR_ORGAO = 800   # teto de acórdãos por órgão/execução (controle de volume)


def _monta_conteudo(rec: dict) -> str:
    """Concatena as partes juridicamente citáveis de um acórdão."""
    partes = []
    classe = rec.get("descricaoClasse") or rec.get("siglaClasse")
    if classe:
        partes.append(f"Classe: {classe}")
    if rec.get("ministroRelator"):
        partes.append(f"Relator: Min. {rec['ministroRelator']}")
    if rec.get("nomeOrgaoJulgador"):
        partes.append(f"Órgão: {rec['nomeOrgaoJulgador']}")
    if rec.get("dataPublicacao"):
        partes.append(f"Publicação: {rec['dataPublicacao']}")
    if rec.get("ementa"):
        partes.append(f"\nEMENTA:\n{rec['ementa']}")
    if rec.get("teseJuridica"):
        partes.append(f"\nTESE JURÍDICA:\n{rec['teseJuridica']}")
    if rec.get("tema"):
        partes.append(f"\nTema: {rec['tema']}")
    refs = rec.get("referenciasLegislativas")
    if refs and isinstance(refs, list):
        txt = "; ".join(str(x) for x in refs if x)
        if txt:
            partes.append(f"\nReferências legislativas: {txt}")
    return "\n".join(partes)


async def _ultimo_json(orgao: str) -> dict | None:
    """Localiza o recurso JSON mais recente (por nome AAAAMMDD.json) do órgão."""
    r = await fetch(f"{CKAN}/package_show", params={"id": orgao}, timeout=30)
    recursos = r.json().get("result", {}).get("resources", [])
    jsons = [x for x in recursos if (x.get("format") or "").upper() == "JSON"]
    if not jsons:
        return None
    # nomes no padrão AAAAMMDD.json → ordena lexicograficamente = cronológico
    jsons.sort(key=lambda x: x.get("name", ""))
    return jsons[-1]


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Ingere o lote mensal mais recente de cada órgão. Retorna (novos, total)."""
    novos = total = 0
    for orgao in ORGAOS:
        try:
            rec_json = await _ultimo_json(orgao)
            if not rec_json:
                continue
            r = await fetch(rec_json["url"], timeout=60)
            dados = r.json()
            if not isinstance(dados, list):
                continue
            sigla = orgao.replace("espelhos-de-acordaos-", "")
            n_orgao = 0
            for rec in dados[:MAX_POR_ORGAO]:
                if not rec.get("ementa"):
                    continue   # sem ementa não há valor semântico
                chave = f"stj:{rec.get('numeroRegistro') or rec.get('id')}"
                titulo = (
                    f"STJ {rec.get('siglaClasse','')} "
                    f"{rec.get('numeroProcesso','')} — {sigla}"
                ).strip()
                conteudo = _monta_conteudo(rec)
                total += 1
                res = await upsert_documento(
                    db, titulo=titulo[:500], categoria="jurisprudencia",
                    conteudo=conteudo, chave_origem=chave,
                    fonte="STJ — Dados Abertos (espelhos de acórdãos)",
                    tribunal="STJ",
                    extra={
                        "orgao": rec.get("nomeOrgaoJulgador"),
                        "relator": rec.get("ministroRelator"),
                        "classe": rec.get("siglaClasse"),
                        "data_decisao": rec.get("dataDecisao"),
                    },
                )
                if res in ("novo", "atualizado"):
                    novos += 1
                    n_orgao += 1
                # commit em lotes de 50 (não segura tudo em memória)
                if total % 50 == 0:
                    await db.commit()
            await db.commit()
            logger.info(f"STJ {sigla}: {n_orgao} novos")
        except Exception as e:
            await db.rollback()
            logger.warning(f"STJ {orgao}: {type(e).__name__}: {e}")
    return novos, total
