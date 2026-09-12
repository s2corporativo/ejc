from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    flush_traces,
    handoff,
)
from agents.decorators import input_guardrail, output_guardrail
from agents.run import RunConfig
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Filesystem, Shell
from agents.sandbox.entries import LocalDir
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient

try:
    from .policy import contains_likely_secret, evaluate_task, is_sensitive_repo_path
except ImportError:  # pragma: no cover - allows direct script execution
    from policy import contains_likely_secret, evaluate_task, is_sensitive_repo_path


PROJECT_NAME = "EJC"
WORKFLOW_NAME = "EJC maintenance sandbox"
_SAFE_HOST_ENV = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR"}


def _input_to_text(value: str | list[TResponseInputItem]) -> str:
    if isinstance(value, str):
        return value
    return "\n".join(str(item) for item in value)


@input_guardrail(run_in_parallel=False)
async def maintenance_input_guardrail(
    ctx: RunContextWrapper[Any],
    agent: Agent[Any],
    input: str | list[TResponseInputItem],
) -> GuardrailFunctionOutput:
    del ctx, agent
    decision = evaluate_task(_input_to_text(input))
    return GuardrailFunctionOutput(
        output_info=decision.reason,
        tripwire_triggered=not decision.allowed,
    )


@output_guardrail
async def maintenance_output_guardrail(
    ctx: RunContextWrapper[Any],
    agent: Agent[Any],
    output: str,
) -> GuardrailFunctionOutput:
    del ctx, agent
    secret_detected = contains_likely_secret(output)
    return GuardrailFunctionOutput(
        output_info="likely credential detected" if secret_detected else "output accepted",
        tripwire_triggered=secret_detected,
    )


@contextmanager
def tracked_snapshot(repo_dir: Path) -> Iterator[Path]:
    """Copy only tracked, non-secret-looking files into a short-lived host snapshot."""
    repo_dir = repo_dir.resolve()
    snapshot = Path(tempfile.mkdtemp(prefix=".agents-sandbox-", dir=repo_dir))

    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        for raw_path in completed.stdout.split(b"\0"):
            if not raw_path:
                continue

            relative = Path(os.fsdecode(raw_path))
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe tracked path: {relative}")
            if is_sensitive_repo_path(relative.as_posix()):
                continue

            source = repo_dir / relative
            if source.is_symlink():
                raise RuntimeError(f"tracked symlink is not materialized for safety: {relative}")
            if not source.is_file():
                continue

            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        yield snapshot
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def build_agent(snapshot_source: Path, model: str) -> SandboxAgent[None]:
    independent_reviewer = Agent(
        name="EJC Independent Reviewer",
        model=model,
        instructions=(
            "Act as an independent reviewer of a proposed maintenance change. Review only the "
            "diff summary, test evidence, and risks supplied by the orchestrator. Check for scope "
            "creep, regression risk, missing tests, security/LGPD exposure, and violations of "
            "repository governance. Do not request deployment and do not invent test results."
        ),
    )

    security_reviewer = Agent(
        name="EJC Security Reviewer",
        model=model,
        handoff_description=(
            "Final reviewer for changes involving authentication, authorization, uploads, CI/CD, "
            "dependencies, core middleware, security configuration, or production-adjacent code."
        ),
        instructions=(
            "Perform a final security and governance review using the conversation evidence. "
            "Do not execute tools or claim checks that were not observed. Return: blocking issues, "
            "required validations, residual risks, and whether the change is safe to keep in PR. "
            "Never authorize production deployment yourself."
        ),
    )

    security_handoff = handoff(
        agent=security_reviewer,
        tool_name_override="transfer_to_security_review",
        tool_description_override=(
            "Transfer control for final review when the task touches authentication, permissions, "
            "uploads, CI/CD, dependencies, core/middleware, security configuration, or any "
            "production-adjacent behavior."
        ),
    )

    return SandboxAgent(
        name="EJC Maintenance Orchestrator",
        model=model,
        instructions=(
            "Work only inside the sandbox copy under `repo/`. First read `repo/AGENTS.md`, "
            "`repo/docs/GOVERNANCA_IA.md`, and `repo/CLAUDE.md` when present. The sandbox copy has "
            "no `.git` directory by design. Never push, merge, deploy, access production, inspect "
            "host secrets, or operate outside `repo/`. Make the smallest change that satisfies the "
            "task and run only repository-defined checks proportional to that change. Never invent "
            "a test result. If files are changed, call `independent_review` with a concise diff "
            "summary and the exact checks/results before the final response. If the change touches "
            "authentication, permissions, uploads, CI/CD, dependencies, core/middleware, security "
            "configuration, or production-adjacent behavior, transfer to the security reviewer "
            "after inspection. Final output must state cause, files changed, checks actually run, "
            "results, and residual risks. Do not include secret values or client data."
        ),
        default_manifest=Manifest(entries={"repo": LocalDir(src=snapshot_source)}),
        capabilities=[Filesystem(), Shell()],
        tools=[
            independent_reviewer.as_tool(
                tool_name="independent_review",
                tool_description=(
                    "Review a concise proposed-change/diff summary plus test evidence before the "
                    "orchestrator finalizes a maintenance result."
                ),
            )
        ],
        handoffs=[security_handoff],
        input_guardrails=[maintenance_input_guardrail],
        output_guardrails=[maintenance_output_guardrail],
    )


async def run_task(task: str, repo_dir: Path, model: str) -> str:
    if os.name == "nt":
        raise RuntimeError(
            "UnixLocalSandboxClient is supported here only on Linux/macOS; run this worker in CI "
            "or another Unix environment."
        )

    repo_dir = repo_dir.resolve()
    if not (repo_dir / ".git").exists():
        raise RuntimeError(f"repository checkout not found: {repo_dir}")

    original_cwd = Path.cwd()
    try:
        os.chdir(repo_dir)
        with tracked_snapshot(repo_dir) as snapshot:
            snapshot_source = snapshot.relative_to(repo_dir)
            agent = build_agent(snapshot_source=snapshot_source, model=model)
            client = UnixLocalSandboxClient(
                inherit_host_environment=False,
                host_environment_allowlist=_SAFE_HOST_ENV,
            )

            try:
                result = await Runner.run(
                    agent,
                    task,
                    run_config=RunConfig(
                        sandbox=SandboxRunConfig(client=client, cwd="repo"),
                        workflow_name=WORKFLOW_NAME,
                        trace_include_sensitive_data=False,
                    ),
                )
                return str(result.final_output)
            finally:
                flush_traces()
    finally:
        os.chdir(original_cwd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a guarded EJC maintenance task in an isolated tracked-files snapshot."
    )
    parser.add_argument("task", help="Maintenance task for the sandbox agent")
    parser.add_argument("--repo", default=".", help="Path to the EJC git checkout")
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_AGENTS_MODEL"),
        help="Model name (or set OPENAI_AGENTS_MODEL)",
    )
    args = parser.parse_args()

    if not args.model:
        parser.error("set --model or OPENAI_AGENTS_MODEL")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required by the host runner and is not passed to the sandbox")

    try:
        output = asyncio.run(run_task(args.task, Path(args.repo), args.model))
    except InputGuardrailTripwireTriggered as exc:
        print(f"BLOCKED_BY_INPUT_GUARDRAIL: {exc.guardrail_result.output.output_info}")
        return 2
    except OutputGuardrailTripwireTriggered:
        print("BLOCKED_BY_OUTPUT_GUARDRAIL: candidate output matched a credential pattern")
        return 3

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
