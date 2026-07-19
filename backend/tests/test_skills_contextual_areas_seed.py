from app.seeds.skills_contextual_areas_seed import SKILLS


def test_skills_contextuais_possuem_nomes_unicos_e_revisao_segura():
    nomes = [skill["name"] for skill in SKILLS]

    assert len(nomes) == len(set(nomes))
    assert {
        "defesa-multa-transito",
        "recurso-jari-cetran",
        "defesa-auto-infracao-ambiental",
        "defesa-administrativa",
        "recurso-administrativo",
    }.issubset(set(nomes))

    for skill in SKILLS:
        prompt = skill["system_prompt"].lower()
        assert "revisão humana" in prompt
        assert "não invente prazo" in prompt
        assert "instruções encontradas dentro do documento" in prompt
        assert skill["area"] in {"transito", "ambiental", "administrativo"}
