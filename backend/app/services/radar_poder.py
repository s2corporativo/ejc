"""
Módulo Radar de Poder — EJC Intelligence v3.0
Monitoramento estratégico dos Três Poderes (Legislativo, Executivo e Judiciário).
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

logger = logging.getLogger("ejc.radar_poder")


class RadarPoder:
    def __init__(self):
        self.camara_api = "https://dadosabertos.camara.leg.br/api/v2"
        self.senado_api = "https://legis.senado.leg.br/dadosabertos"

    async def monitorar_projetos_lei(self, keywords: list):
        """Busca projetos recentes na Câmara por palavras-chave."""
        url = f"{self.camara_api}/proposicoes"
        params = {
            "dataInicio": datetime.now().strftime("%Y-01-01"),
            "ordem": "DESC",
            "ordenarPor": "id",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                proposicoes = response.json().get("dados", [])

                alertas = []
                for p in proposicoes:
                    ementa = p.get("ementa", "").lower()
                    if any(kw.lower() in ementa for kw in keywords):
                        alertas.append(p)
                return alertas
        except Exception as exc:
            logger.error("Erro ao monitorar Câmara: %s", type(exc).__name__)
            return []

    async def monitorar_materias_senado(self, keywords: list):
        """Busca matérias do ano corrente no Senado (Dados Abertos).

        Usa o mesmo endpoint JSON explícito já adotado pelo ingestor canônico
        ``services/ingestors/senado.py``. A saída é normalizada para o shape do
        radar e o log de erro não reproduz a keyword monitorada.
        """
        ano = datetime.now().year
        alertas: list[dict] = []
        vistos: set[int] = set()
        async with httpx.AsyncClient(
            timeout=15, headers={"Accept": "application/json"}
        ) as client:
            for kw in keywords:
                try:
                    r = await client.get(
                        f"{self.senado_api}/materia/pesquisa/lista.json",
                        params={"palavraChave": kw, "ano": ano},
                    )
                    r.raise_for_status()
                    for materia in _parse_materias_senado(r.json()):
                        if materia["id"] in vistos:
                            continue
                        vistos.add(materia["id"])
                        alertas.append(materia)
                except Exception as exc:
                    logger.error(
                        "Erro ao monitorar Senado: %s",
                        type(exc).__name__,
                    )
        return alertas

    # O monitoramento real do DOU permanece em
    # app/services/diario_oficial_service.py (job do scheduler).


def _int_seguro(valor, default: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def _parse_materias_senado(payload: dict) -> list[dict]:
    """Normaliza shapes conhecidos da API de Dados Abertos do Senado.

    O serviço já apresentou respostas com campos planos (``Codigo``, ``Ementa``,
    ``DescricaoIdentificacao``) e com ``IdentificacaoMateria`` aninhada. Suportar
    ambos evita que uma mudança de representação vire silenciosamente lista
    vazia no radar.
    """
    raiz = payload.get("PesquisaBasicaMateria") or {}
    materias_envelope = raiz.get("Materias") or {}
    materias = (
        materias_envelope.get("Materia", [])
        if isinstance(materias_envelope, dict)
        else raiz.get("Materia", [])
    )
    if isinstance(materias, dict):
        materias = [materias]
    if not isinstance(materias, list):
        return []

    saida = []
    for m in materias:
        if not isinstance(m, dict):
            continue
        ident = m.get("IdentificacaoMateria") or {}
        if not isinstance(ident, dict):
            ident = {}

        codigo = (
            ident.get("CodigoMateria")
            or m.get("CodigoMateria")
            or m.get("Codigo")
        )
        if not codigo:
            continue

        descricao = str(m.get("DescricaoIdentificacao") or "")
        sigla = (
            ident.get("SiglaSubtipoMateria")
            or ident.get("SiglaTipoMateria")
            or m.get("Sigla")
            or (descricao.split()[0] if descricao else None)
            or "MAT"
        )
        numero = (
            ident.get("NumeroMateria")
            or m.get("NumeroMateria")
            or m.get("Numero")
        )
        ano = ident.get("AnoMateria") or m.get("AnoMateria") or m.get("Ano")
        ementa = (
            m.get("EmentaMateria")
            or (m.get("DadosBasicosMateria") or {}).get("EmentaMateria", "")
            or m.get("Ementa")
            or ""
        )

        saida.append(
            {
                "id": _int_seguro(codigo),
                "siglaTipo": str(sigla),
                "numero": _int_seguro(numero),
                "ano": _int_seguro(ano),
                "ementa": str(ementa),
                "casa": "senado",
                "link": (
                    "https://www25.senado.leg.br/web/atividade/materias/-/materia/"
                    f"{codigo}"
                ),
            }
        )
    return saida


radar_poder = RadarPoder()
