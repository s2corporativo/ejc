from __future__ import annotations

import sys
import unittest
from pathlib import Path


DIRETORIO_AGENTES = Path(__file__).resolve().parents[1]
if str(DIRETORIO_AGENTES) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_AGENTES))

from policy import (  # noqa: E402
    avaliar_tarefa,
    caminho_checkout_producao,
    caminho_sensivel_repositorio,
    contem_segredo_provavel,
    requer_revisao_seguranca,
)


class TestesPolitica(unittest.TestCase):
    """Valida a política determinística sem chamar Docker, modelo ou API externa."""

    def test_permite_tarefa_de_manutencao_segura(self) -> None:
        """Tarefa de manutenção isolada deve permanecer permitida."""
        decisao = avaliar_tarefa("Corrija o teste do backend em cópia isolada e rode pytest.")
        self.assertTrue(decisao.permitido)

    def test_bloqueia_force_push(self) -> None:
        """Force-push é uma ação destrutiva explicitamente proibida."""
        decisao = avaliar_tarefa("Execute git push --force para atualizar a main.")
        self.assertFalse(decisao.permitido)

    def test_bloqueia_caminho_de_producao_na_tarefa(self) -> None:
        """Menção operacional a `/opt/ejc` na tarefa deve ser bloqueada."""
        decisao = avaliar_tarefa("Entre em /opt/ejc e altere os arquivos de produção.")
        self.assertFalse(decisao.permitido)

    def test_bloqueia_checkout_opt_ejc_por_caminho_real(self) -> None:
        """O caminho do checkout é validado independentemente do texto da tarefa."""
        self.assertTrue(caminho_checkout_producao(Path("/opt/ejc")))
        self.assertTrue(caminho_checkout_producao(Path("/opt/ejc/backend")))

    def test_bloqueia_outros_roots_produtivos_conhecidos(self) -> None:
        """Roots alternativos de produção também não podem ser usados pelo runner."""
        self.assertTrue(caminho_checkout_producao(Path("/srv/ejc")))
        self.assertTrue(caminho_checkout_producao(Path("/var/www/ejc/app")))

    def test_nao_classifica_checkout_temporario_como_producao(self) -> None:
        """Workspace temporário fora dos roots produtivos deve ser elegível."""
        self.assertFalse(caminho_checkout_producao(Path("/tmp/ejc-worktree-seguro")))

    def test_detecta_chave_de_api_provavel(self) -> None:
        """Formato de API key de alta confiança deve ser detectado."""
        self.assertTrue(contem_segredo_provavel("token=sk-abcdefghijklmnopqrstuvwxyz123456"))

    def test_nao_bloqueia_nome_de_variavel(self) -> None:
        """Apenas citar o nome da variável não deve gerar falso positivo de segredo."""
        self.assertFalse(
            contem_segredo_provavel("Configure a variável OPENAI_API_KEY apenas no host.")
        )

    def test_exclui_env_real_e_permite_exemplo(self) -> None:
        """Arquivos `.env` reais ficam fora do snapshot, mas exemplos podem ser copiados."""
        self.assertTrue(caminho_sensivel_repositorio("backend/.env.production"))
        self.assertFalse(caminho_sensivel_repositorio("backend/.env.example"))

    def test_exige_revisao_para_dependencia(self) -> None:
        """Alteração de dependência deve exigir handoff de segurança."""
        self.assertTrue(requer_revisao_seguranca("Atualize uma dependência do backend."))

    def test_exige_revisao_para_migration(self) -> None:
        """Migration Alembic é área sensível e exige handoff de segurança."""
        self.assertTrue(requer_revisao_seguranca("Corrija uma migration Alembic."))

    def test_nao_exige_revisao_para_ajuste_visual_simples(self) -> None:
        """Mudança visual simples não deve ser classificada artificialmente como sensível."""
        self.assertFalse(
            requer_revisao_seguranca("Ajuste o espaçamento de um componente de apresentação.")
        )


if __name__ == "__main__":
    unittest.main()
