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

    def test_main_and_manual_always_run_every_gate(self):
        for event, branch in [("push", "main"), ("manual", "feature/example")]:
            for paths in [[], ["docs/example.md"], ["frontend/src/pages/Page.tsx"]]:
                with self.subTest(event=event, paths=paths):
                    self.assertEqual(selected(self.workflow, event, branch, paths), self.all_steps)

    def test_docs_only_keeps_light_contracts_and_secret_scan(self):
        self.assertEqual(selected(self.workflow, "pull_request", "main", ["docs/example.md"]),
                         {"ops-contracts", "security-secrets"})

    def test_frontend_only_does_not_start_backend_tests(self):
        gates = selected(self.workflow, "pull_request", "main", ["frontend/src/pages/Page.tsx"])
        self.assertEqual(gates, {"frontend", "ops-contracts", "security-sast", "security-secrets"})

    def test_backend_test_only_does_not_start_frontend_tests(self):
        gates = selected(self.workflow, "pull_request", "main", ["backend/tests/test_example.py"])
        self.assertEqual(gates, {"backend", "ops-contracts", "security-sast", "security-secrets"})

    def test_sensitive_changes_require_full_suite(self):
        paths = [".gitleaks.toml", ".semgrepignore", ".env.example", ".woodpecker.yml",
                 "scripts/backup.sh", "scripts/tests/test_woodpecker_scopes.py",
                 "backend/alembic/versions/160_example.py", "backend/app/routers/auth.py",
                 "backend/app/services/ai_service.py", "backend/app/services/datajud_service.py",
                 "backend/app/middleware/auth.py", "backend/app/modules/legal/service.py",
                 "backend/requirements.txt", "frontend/package-lock.json", "backend/Dockerfile",
                 "frontend/src/lib/api.ts", "frontend/src/stores/authStore.ts",
                 "frontend/src/components/RouteGuards.tsx",
                 "infra/host-automation/woodpecker-approved-sha.sh", "ops/agents/runtime.py",
                 "docker-compose.yml", "CLAUDE.md", "docs/GOVERNANCA_IA.md"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(selected(self.workflow, "pull_request", "main", [path]), self.all_steps)

    def test_empty_diff_fails_closed(self):
        self.assertEqual(selected(self.workflow, "pull_request", "main", []), self.all_steps)

    def test_mixed_diff_retains_critical_gates(self):
        self.assertEqual(selected(self.workflow, "pull_request", "main",
                                  ["docs/example.md", "backend/app/services/datajud_service.py"]),
                         self.all_steps)

    def test_light_contracts_have_no_filter(self):
        self.assertNotIn("when", self.workflow["steps"]["ops-contracts"])
        self.assertNotIn("when", self.workflow["steps"]["security-secrets"])

    def test_glob_star_does_not_cross_directories(self):
        self.assertFalse(matches("frontend/*.json", "frontend/nested/package.json"))
        self.assertTrue(matches("**/package*.json", "package.json"))
        self.assertTrue(matches("**/package*.json", "frontend/nested/package.json"))
        self.assertTrue(matches("ops/**/requirements*.txt", "ops/requirements.txt"))
        self.assertTrue(matches("ops/**/requirements*.txt", "ops/agents/tests/requirements.txt"))


if __name__ == "__main__":
    unittest.main()
