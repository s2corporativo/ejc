from __future__ import annotations

import sys
import unittest
from pathlib import Path


DIRETORIO_AGENTES = Path(__file__).resolve().parents[1]
if str(DIRETORIO_AGENTES) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_AGENTES))

from policy import (  # noqa: E402
    avaliar_tarefa,
    caminho_sensivel_repositorio,
    contem_segredo_provavel,
    requer_revisao_seguranca,
)


class TestesPolitica(unittest.TestCase):
    def test_permite_tarefa_de_manutencao_segura(self) -> None:
        decisao = avaliar_tarefa("Corrija o teste do backend em cópia isolada e rode pytest.")
        self.assertTrue(decisao.permitido)

    def test_bloqueia_force_push(self) -> None:
        decisao = avaliar_tarefa("Execute git push --force para atualizar a main.")
        self.assertFalse(decisao.permitido)

    def test_bloqueia_caminho_de_producao(self) -> None:
        decisao = avaliar_tarefa("Entre em /opt/ejc e altere os arquivos de produção.")
        self.assertFalse(decisao.permitido)

    def test_detecta_chave_de_api_provavel(self) -> None:
        self.assertTrue(contem_segredo_provavel("token=sk-abcdefghijklmnopqrstuvwxyz123456"))

    def test_nao_bloqueia_nome_de_variavel(self) -> None:
        self.assertFalse(
            contem_segredo_provavel("Configure a variável OPENAI_API_KEY apenas no host.")
        )

    def test_exclui_env_real_e_permite_exemplo(self) -> None:
        self.assertTrue(caminho_sensivel_repositorio("backend/.env.production"))
        self.assertFalse(caminho_sensivel_repositorio("backend/.env.example"))

    def test_exige_revisao_para_dependencia(self) -> None:
        self.assertTrue(requer_revisao_seguranca("Atualize uma dependência do backend."))

    def test_exige_revisao_para_migration(self) -> None:
        self.assertTrue(requer_revisao_seguranca("Corrija uma migration Alembic."))

    def test_nao_exige_revisao_para_ajuste_visual_simples(self) -> None:
        self.assertFalse(
            requer_revisao_seguranca("Ajuste o espaçamento de um componente de apresentação.")
        )


if __name__ == "__main__":
    unittest.main()
