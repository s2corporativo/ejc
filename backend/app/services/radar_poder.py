"""
Módulo Radar de Poder — EJC Intelligence v3.0
Monitoramento estratégico dos Três Poderes (Legislativo, Executivo e Judiciário).
"""
import httpx
import logging
from datetime import datetime

logger = logging.getLogger("ejc.radar_poder")

class RadarPoder:
    def __init__(self):
        self.camara_api = "https://dadosabertos.camara.leg.br/api/v2"
        self.senado_api = "https://legis.senado.leg.br/dadosabertos"

    async def monitorar_projetos_lei(self, keywords: list):
        """
        Busca Projetos de Lei recentes na Câmara que contenham as palavras-chave.
        """
        url = f"{self.camara_api}/proposicoes"
        params = {
            "dataInicio": datetime.now().strftime("%Y-01-01"),
            "ordem": "DESC",
            "ordenarPor": "id"
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
        except Exception as e:
            logger.error(f"Erro ao monitorar Câmara: {e}")
            return []

    async def monitorar_materias_senado(self, keywords: list):
        """
        Busca matérias do ano corrente no Senado (Dados Abertos) que contenham
        as palavras-chave. Uma chamada por keyword; falha de uma keyword não
        aborta as demais. Saída normalizada no shape da Câmara + casa/link.
        """
        ano = datetime.now().year
        alertas: list[dict] = []
        vistos: set = set()
        async with httpx.AsyncClient(
            timeout=15, headers={"Accept": "application/json"}
        ) as client:
            for kw in keywords:
                try:
                    r = await client.get(
                        f"{self.senado_api}/materia/pesquisa/lista",
                        params={"palavraChave": kw, "ano": ano},
                    )
                    r.raise_for_status()
                    alertas.extend(
                        m for m in _parse_materias_senado(r.json())
                        if m["id"] not in vistos and not vistos.add(m["id"])
                    )
                except Exception as e:
                    logger.error(f"Erro ao monitorar Senado (kw={kw!r}): {e}")
        return alertas

    # P2 (2026-07-05): stub monitorar_dou removido — o monitoramento REAL do
    # DOU é o de app/services/diario_oficial_service.py (job do scheduler).


def _parse_materias_senado(payload: dict) -> list[dict]:
    """Normaliza a resposta do Senado para o shape usado pelo radar
    (id/siglaTipo/numero/ano/ementa) + casa e link — função pura (testável)."""
    materias = (
        (payload.get("PesquisaBasicaMateria") or {}).get("Materias") or {}
    ).get("Materia") or []
    if isinstance(materias, dict):  # o Senado devolve dict quando há 1 resultado
        materias = [materias]
    saida = []
    for m in materias:
        ident = m.get("IdentificacaoMateria") or m
        codigo = ident.get("CodigoMateria")
        if not codigo:
            continue
        saida.append({
            "id": int(codigo),
            "siglaTipo": ident.get("SiglaSubtipoMateria") or ident.get("SiglaTipoMateria") or "MAT",
            "numero": int(ident.get("NumeroMateria") or 0),
            "ano": int(ident.get("AnoMateria") or 0),
            "ementa": m.get("EmentaMateria") or (m.get("DadosBasicosMateria") or {}).get("EmentaMateria") or "",
            "casa": "senado",
            "link": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}",
        })
    return saida


radar_poder = RadarPoder()
