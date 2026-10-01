"""Contrato de seleção do CI: casos externos à implementação dos filtros.

O avaliador cobre o subconjunto event/branch/path usado pelo workflow.
A interpretação completa do YAML continua sendo validada pelo Woodpecker.
"""
from fnmatch import fnmatchcase
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


def matches(pattern, path):
    # Glob por segmentos: * não atravessa /; ** inclui zero ou mais diretórios.
    def walk(pattern_parts, path_parts):
        if not pattern_parts:
            return not path_parts
        if pattern_parts[0] == "**":
            return walk(pattern_parts[1:], path_parts) or (
                bool(path_parts) and walk(pattern_parts, path_parts[1:])
            )
        return bool(path_parts) and fnmatchcase(path_parts[0], pattern_parts[0]) and walk(
            pattern_parts[1:], path_parts[1:]
        )
    return walk(pattern.split("/"), path.split("/"))


def selected(workflow, event, branch, paths):
    def condition(rule):
        if "event" in rule and rule["event"] != event:
            return False
        if "branch" in rule and rule["branch"] != branch:
            return False
        if "path" in rule:
            policy = rule["path"]
            if not paths:
                return policy.get("on_empty", True)
            return any(matches(pattern, path)
                       for pattern in policy["include"] for path in paths)
        return True

    return {name for name, step in workflow["steps"].items()
            if "when" not in step or any(condition(rule) for rule in step["when"])}


class ScopeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load((ROOT / ".woodpecker.yml").read_text())
        cls.all_steps = set(cls.workflow["steps"])
        cls.fast_steps = {"backend-fast", "frontend-fast"}
        cls.full_steps = cls.all_steps - cls.fast_steps

    def test_main_and_manual_run_full_suite_without_fast_duplicates(self):
        for event, branch in [("push", "main"), ("manual", "feature/example")]:
            for paths in [[], ["docs/example.md"], ["frontend/src/pages/Page.tsx"]]:
                with self.subTest(event=event, paths=paths):
                    self.assertEqual(
                        selected(self.workflow, event, branch, paths),
                        self.full_steps,
                    )

    def test_docs_only_keeps_light_contracts_and_secret_scan(self):
        self.assertEqual(selected(self.workflow, "pull_request", "main", ["docs/example.md"]),
                         {"ops-contracts", "deploy-validation", "security-secrets"})

    def test_frontend_only_uses_fast_frontend_gate(self):
        gates = selected(self.workflow, "pull_request", "main", ["frontend/src/pages/Page.tsx"])
        self.assertEqual(gates, {
            "frontend-fast", "ops-contracts", "deploy-validation",
            "graphify-guard", "security-sast", "security-secrets",
        })
        self.assertNotIn("frontend", gates)
        self.assertNotIn("frontend-e2e", gates)

    def test_backend_test_only_uses_fast_backend_gate(self):
        gates = selected(self.workflow, "pull_request", "main", ["backend/tests/test_example.py"])
        self.assertEqual(gates, {
            "backend-fast", "ops-contracts", "deploy-validation",
            "graphify-guard", "security-sast", "security-secrets",
        })
        self.assertNotIn("backend-tests", gates)

    def test_release_candidate_requires_full_suite(self):
        gates = selected(
            self.workflow, "pull_request", "main", ["config/release_candidate.json"]
        )
        self.assertTrue(self.full_steps <= gates)
        self.assertIn("backend-tests", gates)
        self.assertIn("frontend", gates)
        self.assertIn("frontend-e2e", gates)

    def test_release_candidate_fast_gates_saem_antes_de_recursos_compartilhados(self):
        backend_fast = "\n".join(self.workflow["steps"]["backend-fast"]["commands"])
        frontend_fast = "\n".join(self.workflow["steps"]["frontend-fast"]["commands"])
        self.assertIn("config/release_candidate.json", backend_fast)
        self.assertIn("exit 0", backend_fast)
        self.assertIn("config/release_candidate.json", frontend_fast)
        self.assertIn("exit 0", frontend_fast)

        # Full frontend só começa após backend-tests: evita as duas suítes
        # pesadas concorrendo por RAM/CPU quando um release candidate dispara
        # o gate integral.
        deps = self.workflow["steps"]["frontend"].get("depends_on", [])
        self.assertIn("backend-tests", deps)

    def test_normal_critical_pr_stays_fast_but_keeps_security(self):
        gates = selected(
            self.workflow, "pull_request", "main", ["backend/app/routers/auth.py"]
        )
        self.assertIn("backend-fast", gates)
        self.assertNotIn("backend-tests", gates)
        self.assertNotIn("frontend", gates)
        self.assertNotIn("frontend-e2e", gates)
        for required in (
            "security-secrets", "security-sast", "security-vulnerabilities",
            "lint", "migration-check", "graphify-guard",
        ):
            self.assertIn(required, gates)

    def test_empty_diff_fails_closed(self):
        gates = selected(self.workflow, "pull_request", "main", [])
        self.assertTrue(self.full_steps <= gates)

    def test_mixed_diff_retains_critical_fast_gates(self):
        gates = selected(
            self.workflow, "pull_request", "main",
            ["docs/example.md", "backend/app/services/datajud_service.py"],
        )
        self.assertIn("backend-fast", gates)
        self.assertNotIn("backend-tests", gates)
        for required in (
            "security-secrets", "security-sast", "security-vulnerabilities",
            "lint", "migration-check", "graphify-guard",
        ):
            self.assertIn(required, gates)

    def test_light_contracts_have_no_filter(self):
        self.assertNotIn("when", self.workflow["steps"]["ops-contracts"])
        self.assertNotIn("when", self.workflow["steps"]["security-secrets"])
        self.assertNotIn("when", self.workflow["steps"]["deploy-validation"])

    def test_migration_check_nao_roda_para_testes_documentais(self):
        gates = selected(self.workflow, "pull_request", "main",
                         ["backend/tests/test_outro.py"])
        self.assertNotIn("migration-check", gates)
        self.assertNotIn("lint", gates)

    def test_glob_star_does_not_cross_directories(self):
        self.assertFalse(matches("frontend/*.json", "frontend/nested/package.json"))
        self.assertTrue(matches("**/package*.json", "package.json"))
        self.assertTrue(matches("**/package*.json", "frontend/nested/package.json"))
        self.assertTrue(matches("ops/**/requirements*.txt", "ops/requirements.txt"))
        self.assertTrue(matches("ops/**/requirements*.txt", "ops/agents/tests/requirements.txt"))


if __name__ == "__main__":
    unittest.main()
