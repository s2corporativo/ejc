"""`proximas_etapas` precisa apontar para FRENTE na jornada.

O motor detecta o estágio do processo a partir da linha do tempo real
(`_STAGE_MARKERS`) e devolve as etapas seguintes da jornada do rito. O estágio,
porém, é um CÓDIGO (`pos_sentenca`, `defesa`) e a jornada é texto jurídico
(`sentença`, `contestação`): os dois vocabulários quase nunca casam por
substring. A busca original procurava o rótulo pelo próprio código, localizava a
posição em 15 das 80 combinações rito × estágio e, nas outras 65, caía num
`etapas[:3]` — o COMEÇO da jornada.

O efeito era silencioso e visível ao advogado: um caso já sentenciado recebia
"petição inicial → análise inicial" como próximas etapas. Esse texto é
renderizado na tela do Raio-X (`RaioXProcesso.tsx` imprime o `rito_jornada`
inteiro), vai para o PDF/DOCX exportado e é entregue ao agente de IA pela tool
`identificar_rito_e_fase`.

É a mesma classe de defeito que o `CLAUDE.md` registra como recorrente no EJC —
vocabulário divergente entre duas camadas, sem exceção que denuncie.
"""
from app.services.rito_engine import _RULES, _STAGE_MARKERS, identificar_rito

CIVIL = "Ação de indenização por vício do produto"


def _rito(*descricoes: str) -> dict:
    """Mesmo caso, cronologia crescente — como o Raio-X monta `rito_context`."""
    return identificar_rito({
        "area": "consumidor",
        "resumo": CIVIL,
        "eventos": [{"descricao": d} for d in descricoes],
    })


def test_processo_sentenciado_nao_volta_para_a_peticao_inicial():
    """O caso que motivou a correção."""
    r = _rito("Distribuição da petição inicial",
              "Apresentada contestação",
              "Sentença: julgo procedente o pedido")
    assert r["etapa_atual"] == "pos_sentenca"
    assert "petição inicial" not in r["proximas_etapas"]
    assert r["proximas_etapas"][0] == "apelação"


def test_jornada_avanca_junto_com_a_linha_do_tempo():
    """Cada evento novo só pode empurrar as próximas etapas para frente."""
    etapas = list(_RULES[_indice("processo_civil_comum")].etapas)
    cronologia = [
        ("Distribuição da petição inicial",),
        ("Distribuição da petição inicial", "Apresentada contestação"),
        ("Apresentada contestação", "Designada audiência de instrução"),
        ("Audiência de instrução realizada", "Sentença: julgo procedente"),
        ("Sentença: julgo procedente", "Interposta apelação"),
    ]
    anterior = -1
    for eventos in cronologia:
        proximas = _rito(*eventos)["proximas_etapas"]
        assert proximas, f"jornada ficou muda em {eventos!r}"
        posicao = etapas.index(proximas[0])
        assert posicao > anterior, (
            f"{eventos!r} retrocedeu para {proximas[0]!r} na jornada")
        anterior = posicao


def test_fim_da_jornada_devolve_lista_vazia_em_vez_do_comeco():
    """Não há etapa depois do cumprimento de sentença — e dizer "petição
    inicial" seria pior que não dizer nada."""
    r = _rito("Sentença transitada em julgado",
              "Iniciado cumprimento de sentença com penhora")
    assert r["etapa_atual"] == "cumprimento_ou_execucao"
    assert r["proximas_etapas"] == []


def test_processo_que_nao_comecou_recebe_as_primeiras_etapas():
    """Sem sinal de andamento, o início da jornada é a resposta certa.

    Sem eventos o motor tem poucos sinais e o rito escolhido varia, então a
    asserção é sobre a POSIÇÃO na jornada devolvida, não sobre um rótulo fixo.
    """
    r = identificar_rito({"area": "consumidor", "resumo": CIVIL})
    assert r["etapa_atual"] == "triagem"
    assert r["etapas"].index(r["proximas_etapas"][0]) <= 1


def test_estagio_sem_correspondente_na_jornada_fica_em_silencio():
    """Processo que andou, mas cujo estágio não existe nesta jornada: o motor
    não tem o que sugerir e não inventa — mesma recusa do evento_processual."""
    r = identificar_rito({
        "area": "transito",
        "tipo_documento": "multa_transito",
        "resumo": "Auto de infração de trânsito; recurso à JARI",
        "eventos": [{"descricao": "Iniciada execução fiscal com penhora"}],
    })
    assert r["codigo"] == "transito_administrativo"
    assert r["etapa_atual"] == "cumprimento_ou_execucao"
    assert r["proximas_etapas"] == []


def test_nenhum_estagio_detectado_devolve_etapa_da_propria_jornada():
    """Rede de segurança do contrato: o que sai de `proximas_etapas` é sempre
    subconjunto ordenado das `etapas` do rito devolvido — em qualquer estágio,
    em qualquer rito."""
    for regra in _RULES:
        for estagio, marcadores in _STAGE_MARKERS:
            r = identificar_rito({
                "area": regra.area, "rito": regra.nome,
                "texto": " ".join(regra.sinais) + " " + marcadores[0],
            })
            etapas = r["etapas"]
            proximas = r["proximas_etapas"]
            assert all(p in etapas for p in proximas), (
                f"{regra.codigo}/{estagio}: {proximas} fora da jornada")
            posicoes = [etapas.index(p) for p in proximas]
            assert posicoes == sorted(posicoes), (
                f"{regra.codigo}/{estagio}: próximas etapas fora de ordem")


def _indice(codigo: str) -> int:
    return next(i for i, r in enumerate(_RULES) if r.codigo == codigo)
