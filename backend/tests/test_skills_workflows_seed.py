import unittest

from app.seeds.skills_workflows_seed import SKILLS


EXPECTED = {
    "gerador-notificacao-extrajudicial",
    "transcritor-midias-audiencia",
    "defesa-administrativa-tributaria",
    "revisao-tributos-imobiliarios",
    "consignacao-aluguel-chaves",
    "embargos-terceiro",
    "repeticao-indebito-tributario",
    "anulatoria-declaratoria-fiscal",
    "atraso-entrega-distrato-imobiliario",
    "revisional-aluguel",
    "monitoria-execucao-titulo",
    "raio-x-cda",
    "renovatoria-locacao-comercial",
    "adjudicacao-compulsoria",
    "excecao-pre-executividade",
    "embargos-execucao-fiscal",
    "acao-possessoria",
    "mandado-seguranca",
    "acao-despejo",
    "acao-usucapiao",
    "vicio-defeito-produto-servico",
    "cobranca-indevida-consumidor",
}


class SkillsWorkflowsSeedTest(unittest.TestCase):
    def test_catalogo_tem_todos_os_fluxos_sem_duplicidade(self):
        nomes = [skill["name"] for skill in SKILLS]
        self.assertEqual(set(nomes), EXPECTED)
        self.assertEqual(len(nomes), len(set(nomes)))
        self.assertEqual(
            len({skill["display_name"] for skill in SKILLS}),
            len(SKILLS),
        )

    def test_todos_os_fluxos_exigem_triagem_fontes_e_revisao(self):
        for skill in SKILLS:
            with self.subTest(skill=skill["name"]):
                prompt = skill["system_prompt"]
                self.assertTrue(skill["description"])
                self.assertTrue(skill["area"])
                self.assertIn("STATUS: INCOMPLETO", prompt)
                self.assertIn("[VALIDAR FONTE]", prompt)
                self.assertIn("revisão humana", prompt)
                self.assertIn("DADO AUSENTE", prompt)

    def test_alertas_corrigem_generalizacoes_dos_cards_de_referencia(self):
        prompts = {skill["name"]: skill["system_prompt"] for skill in SKILLS}
        self.assertIn(
            "CARF é realmente competente",
            prompts["defesa-administrativa-tributaria"],
        )
        self.assertIn("presunção relativa", prompts["revisao-tributos-imobiliarios"])
        self.assertIn(
            "não se aplica indistintamente à execução fiscal",
            prompts["embargos-terceiro"],
        )
        self.assertIn(
            "efeito suspensivo automático",
            prompts["embargos-execucao-fiscal"],
        )
        self.assertIn("não são automáticos", prompts["cobranca-indevida-consumidor"])


if __name__ == "__main__":
    unittest.main()
