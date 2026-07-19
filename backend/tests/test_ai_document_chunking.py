import unittest

from app.services.ai_document_chunking import dividir_documento_em_blocos


class DocumentoChunkingTest(unittest.TestCase):
    def test_divisao_preserva_documento_inteiro_sem_truncar_final(self):
        paragrafos = [
            f"MARCADOR-{indice:03d} " + (f"conteudo-{indice} " * 45)
            for indice in range(40)
        ]
        texto = "INICIO\n" + "\n".join(paragrafos) + "\nFIM-DO-DOCUMENTO"

        blocos = dividir_documento_em_blocos(
            texto,
            tamanho=2_400,
            sobreposicao=180,
        )

        self.assertGreater(len(blocos), 1)
        self.assertTrue(blocos[0].startswith("INICIO"))
        self.assertTrue(blocos[-1].endswith("FIM-DO-DOCUMENTO"))
        self.assertTrue(all(len(bloco) <= 2_400 for bloco in blocos))
        combinado = "\n".join(blocos)
        for indice in range(40):
            self.assertIn(f"MARCADOR-{indice:03d}", combinado)

    def test_divisao_limpa_nulo_e_aceita_texto_vazio(self):
        self.assertEqual(dividir_documento_em_blocos("   "), [])
        self.assertEqual(dividir_documento_em_blocos("abc\x00def"), ["abcdef"])

    def test_divisao_rejeita_parametros_inseguros(self):
        for tamanho, sobreposicao in [(1_999, 10), (2_000, -1), (2_000, 1_000)]:
            with self.subTest(tamanho=tamanho, sobreposicao=sobreposicao):
                with self.assertRaises(ValueError):
                    dividir_documento_em_blocos(
                        "texto suficiente",
                        tamanho=tamanho,
                        sobreposicao=sobreposicao,
                    )

    def test_teto_padrao_de_120_mil_caracteres_cabe_em_12_blocos(self):
        texto = ("x" * 10_900 + "\n") * 11
        texto = (texto + "FIM").ljust(120_000, "y")

        blocos = dividir_documento_em_blocos(texto)

        self.assertLessEqual(len(blocos), 12)
        self.assertTrue(blocos[-1].endswith("y"))


if __name__ == "__main__":
    unittest.main()
