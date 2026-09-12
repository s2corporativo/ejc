# EJC — maintenance agents

Operational, non-production runner for repository maintenance using only the requested OpenAI Agents SDK orchestration surface:

- `SandboxAgent`
- Agents as tools (`Agent.as_tool()`)
- Handoffs
- Guardrails
- Tracing

The production FastAPI runtime does **not** import this package and `backend/requirements.txt` is unchanged.

## Safety model

The runner:

1. creates a temporary snapshot containing only Git-tracked files;
2. excludes common secret-bearing file names (`.env*` except examples, private keys and credential files);
3. refuses tracked symlinks rather than following them;
4. starts `UnixLocalSandboxClient` with host environment inheritance disabled;
5. exposes only a minimal environment allowlist (`PATH`, locale/terminal/temp variables), so `OPENAI_API_KEY` remains in the host runner and is not passed to the sandbox shell;
6. does not copy `.git`, so the sandbox cannot push, merge or change repository history;
7. runs a blocking input guardrail before the first agent turn;
8. runs an output guardrail that rejects high-confidence credential shapes;
9. records SDK tracing with `trace_include_sensitive_data=False`.

`SandboxAgent` is a beta SDK feature in `openai-agents==0.22.2`; keep the dependency pinned until a deliberate compatibility review.

## Agents

- **EJC Maintenance Orchestrator**: sandbox worker that inspects and may edit the temporary repository copy and run proportional checks.
- **EJC Independent Reviewer**: used as an agent tool. It reviews the orchestrator's concise diff/test summary before finalization.
- **EJC Security Reviewer**: handoff target for auth, permissions, uploads, CI/CD, dependency, core/middleware, security/configuration or production-adjacent changes.

## Install

Use a dedicated virtual environment outside the application runtime:

```bash
python -m venv .venv-agents
. .venv-agents/bin/activate
pip install -r ops/agents/requirements.txt
```

Python 3.10+ is required by the SDK. This runner uses `UnixLocalSandboxClient`, so execute it on Linux/macOS (the EJC CI/Linux environment is the intended target).

## Run

The model is deliberately not hard-coded. Select it explicitly so cost/capability can be controlled per execution.

```bash
export OPENAI_API_KEY='...'
export OPENAI_AGENTS_MODEL='<model-name>'
python -m ops.agents.runner "Analise e corrija o erro X; rode apenas os testes proporcionais ao diff."
```

Or:

```bash
python -m ops.agents.runner --model '<model-name>' "Analise o problema X."
```

The API key is consumed by the host process for the model call and is not inherited by the sandbox shell.

## Deterministic policy tests

These tests do not call any model and do not consume API credits:

```bash
python -m unittest discover -s ops/agents/tests -v
```

## Explicit non-goals

This initial layer does not:

- add a public API endpoint;
- alter the institutional AI gateway;
- merge or deploy code;
- touch `/opt/ejc` or any production database;
- use Sessions, Realtime, Voice, Skills, Memory or other higher-level SDK features;
- export sandbox edits automatically back into the host checkout.

Sandbox edits are intentionally ephemeral in this first safety boundary. Promotion of a reviewed change into a Git branch remains a separate controlled step in the existing governance flow.
