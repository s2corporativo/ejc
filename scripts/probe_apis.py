#!/usr/bin/env python3
"""Sondagem ao vivo das APIs candidatas do catálogo (docs/CATALOGO_APIS_EJC.md).

Roda em ambiente com egress aberto (GitHub Actions) e imprime uma tabela de
viabilidade REAL: alcançável? autentica? devolve o dado esperado? latência?
Sempre sai com exit 0 — o resultado é o relatório, não um gate de CI.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

UA = {"User-Agent": "EJC-Probe/1.0 (avaliacao de viabilidade; contato@depaulateixeira.adv.br)"}
# Chave PÚBLICA divulgada pelo CNJ na wiki oficial do DataJud.
DATAJUD_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

def get(url: str, headers: dict | None = None, data: bytes | None = None,
        timeout: int = 25) -> tuple[int, float, str]:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    t0 = time.time()
    try:
        # Sonda de viabilidade rodada a mao pelo operador: as URLs sao todas
        # literais neste arquivo (lista do catalogo, mais abaixo). Nao ha
        # request nem servico chamando isto, entao nao ha SSRF a alcancar.
        # Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(4000).decode("utf-8", "replace")
            return r.status, time.time() - t0, body
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0, e.read(400).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, time.time() - t0, f"{type(e).__name__}: {e}"


def check(nome: str, url: str, valida, headers=None, data=None):
    code, dt, body = get(url, headers=headers, data=data)
    ok, detalhe = False, ""
    if code == 200:
        try:
            ok, detalhe = valida(body)
        except Exception as e:  # noqa: BLE001
            detalhe = f"parse: {e}"
    else:
        detalhe = body[:110].replace("\n", " ")
    status = "OK" if ok else ("HTTP %s" % code if code else "FALHA")
    print(f"| {nome} | {status} | {dt:.1f}s | {detalhe[:120]} |")
    return ok


def v_json_lista_valor(body):
    d = json.loads(body)
    assert isinstance(d, list) and d and "valor" in d[0]
    return True, f"último={d[-1].get('data')}: {d[-1].get('valor')}"


def v_json(body, chave=None, texto=""):
    d = json.loads(body)
    if chave:
        assert chave in (d[0] if isinstance(d, list) and d else d)
    return True, texto or (str(d)[:100])


def main() -> None:
    print("## Sondagem ao vivo — APIs candidatas\n")
    print("| API | Status | Latência | Amostra/erro |")
    print("|---|---|---|---|")

    # ── BCB SGS: todos os códigos do módulo de cálculos ─────────────────────
    for cod, nome in [(11, "SELIC diária"), (432, "SELIC meta"),
                      (4390, "SELIC acum. mês"), (12, "CDI diária"),
                      (4391, "CDI acum. mês"), (433, "IPCA"), (188, "INPC"),
                      (189, "IGP-M"), (7478, "IPCA-15"), (10764, "IPCA-E"),
                      (226, "TR"), (25, "Poupança(-2012)"),
                      (195, "Poupança(2012+)"), (29543, "TAXA LEGAL 14.905")]:
        check(f"BCB SGS {cod} ({nome})",
              f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados/ultimos/2?formato=json",
              v_json_lista_valor)

    # Olinda exige que o ALIAS do parâmetro OData tenha o MESMO nome do
    # parâmetro declarado (aliases curtos @i/@f → HTTP 400 "has no function
    # with parameter"). Mesma sintaxe já usada em indices_service.OLINDA_PTAX.
    check("BCB Olinda PTAX (dólar)",
          "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
          "CotacaoDolarPeriodo(dataInicialCotacao=@dataInicialCotacao,dataFinalCotacao=@dataFinalCotacao)?"
          "@dataInicialCotacao='07-07-2026'&@dataFinalCotacao='07-10-2026'&$top=2&$format=json",
          lambda b: v_json(b := b, texto=f"itens={len(json.loads(b).get('value', []))}"))
    check("BCB Olinda taxaJuros (por instituição)",
          "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/"
          "TaxasJurosMensalPorMes?$top=2&$format=json",
          lambda b: v_json(b, texto=f"itens={len(json.loads(b).get('value', []))}"))

    # ── Cadastrais / prazos ──────────────────────────────────────────────────
    check("BrasilAPI feriados 2026",
          "https://brasilapi.com.br/api/feriados/v1/2026",
          lambda b: (True, f"{len(json.loads(b))} feriados; 1º={json.loads(b)[0]['date']}"))
    check("BrasilAPI CEP v2 (Betim)",
          "https://brasilapi.com.br/api/cep/v2/32600000",
          lambda b: v_json(b, texto=json.loads(b).get("city", "")))
    check("BrasilAPI CNPJ (BB)",
          "https://brasilapi.com.br/api/cnpj/v1/00000000000191",
          lambda b: v_json(b, texto=json.loads(b).get("razao_social", "")[:60]))
    check("OpenCNPJ (BB)",
          "https://api.opencnpj.org/00000000000191",
          lambda b: v_json(b, texto=json.loads(b).get("razao_social", str(json.loads(b))[:60])[:60]))
    check("ViaCEP (Betim)",
          "https://viacep.com.br/ws/32600000/json/",
          lambda b: v_json(b, texto=json.loads(b).get("localidade", "")))
    check("IBGE agregados IPCA (1737)",
          "https://servicodados.ibge.gov.br/api/v3/agregados/1737/periodos/-1/"
          "variaveis/63?localidades=N1%5Ball%5D",
          lambda b: (True, str(json.loads(b))[:90]))

    # ── Legislativo / diários ────────────────────────────────────────────────
    check("Câmara v2 proposições",
          "https://dadosabertos.camara.leg.br/api/v2/proposicoes?itens=1&ordem=DESC&ordenarPor=id",
          lambda b: v_json(b, texto=f"dados={len(json.loads(b).get('dados', []))}"))
    check("Senado matérias atualizadas",
          "https://legis.senado.leg.br/dadosabertos/materia/atualizadas.json",
          lambda b: (True, str(b)[:80]))
    check("ALMG v2 proposições",
          "https://dadosabertos.almg.gov.br/api/v2/proposicoes/pesquisa/direcionada"
          "?tp=1000&formato=json&qtde=1",
          lambda b: (True, str(b)[:80]))
    check("Querido Diário — Betim coberta?",
          "https://queridodiario.ok.org.br/api/cities?city_name=Betim",
          lambda b: (True, str(json.loads(b))[:120]))
    check("Querido Diário — BH gazettes",
          "https://queridodiario.ok.org.br/api/gazettes?territory_ids=3106200&size=1",
          lambda b: v_json(b, texto=f"total={json.loads(b).get('total_gazettes')}"))

    # ── Conhecimento ─────────────────────────────────────────────────────────
    check("TCU acórdãos (REST)",
          "https://contas.tcu.gov.br/ords/condenacao/consulta/acordaos?pagina=1",
          lambda b: (True, str(b)[:80]))
    check("TCU dados abertos (site)",
          "https://sites.tcu.gov.br/dados-abertos/",
          lambda b: (True, "página ok"))
    check("STJ dados abertos (CKAN)",
          "https://dadosabertos.web.stj.jus.br/api/3/action/package_list",
          lambda b: v_json(b, texto=f"datasets={len(json.loads(b).get('result', []))}"))
    check("Normas RFB (busca querystring)",
          "http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action?termoBusca=lgpd",
          lambda b: (True, "página ok"))
    check("ANPD regulamentações (gov.br)",
          "https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd",
          lambda b: (True, "página ok"))

    # ── Judiciário ───────────────────────────────────────────────────────────
    check("DataJud TJMG (chave pública CNJ)",
          "https://api-publica.datajud.cnj.jus.br/api_publica_tjmg/_search",
          lambda b: (True, str(b)[:80]),
          headers={"Authorization": f"APIKey {DATAJUD_KEY}",
                   "Content-Type": "application/json"},
          data=json.dumps({"size": 1, "query": {"match_all": {}}}).encode())
    check("CNJ TPU/SGT (página do webservice)",
          "https://www.cnj.jus.br/sgt/consulta_publica_classes.php",
          lambda b: (True, "página ok"))
    check("DJEN/Comunica CNJ (API)",
          "https://comunicaapi.pje.jus.br/api/v1/comunicacao?itensPorPagina=1&pagina=1",
          lambda b: (True, str(b)[:80]))
    check("Portal Transparência (sem token → espera 401/403)",
          "https://api.portaldatransparencia.gov.br/api-de-dados/ceis?pagina=1",
          lambda b: (True, str(b)[:60]))

    print("\nFim da sondagem.")


if __name__ == "__main__":
    main()

# Sondagem re-executada em 2026-07-17 (pré-go-live) — dispara o workflow probe-apis.
