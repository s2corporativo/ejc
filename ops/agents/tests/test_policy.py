from __future__ import annotations

import sys
import unittest
from pathlib import Path


AGENTS_DIR = Path(__file__).resolve().parents[1]
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from policy import contains_likely_secret, evaluate_task, is_sensitive_repo_path  # noqa: E402


class PolicyTests(unittest.TestCase):
    def test_allows_safe_maintenance_task(self) -> None:
        decision = evaluate_task("Corrija o teste do backend em uma copia isolada e rode pytest.")
        self.assertTrue(decision.allowed)

    def test_blocks_force_push(self) -> None:
        decision = evaluate_task("Execute git push --force para atualizar a main.")
        self.assertFalse(decision.allowed)

    def test_blocks_production_path(self) -> None:
        decision = evaluate_task("Entre em /opt/ejc e altere os arquivos de producao.")
        self.assertFalse(decision.allowed)

    def test_detects_likely_api_key(self) -> None:
        self.assertTrue(contains_likely_secret("token=sk-abcdefghijklmnopqrstuvwxyz123456"))

    def test_does_not_block_variable_name_only(self) -> None:
        self.assertFalse(contains_likely_secret("Configure a variavel OPENAI_API_KEY no host."))

    def test_excludes_real_env_but_allows_example(self) -> None:
        self.assertTrue(is_sensitive_repo_path("backend/.env.production"))
        self.assertFalse(is_sensitive_repo_path("backend/.env.example"))


if __name__ == "__main__":
    unittest.main()
