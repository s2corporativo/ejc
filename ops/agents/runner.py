from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from docker import from_env as docker_from_env  # type: ignore[import-untyped]
from docker.errors import DockerException, ImageNotFound  # type: ignore[import-untyped]

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
from agents.items import HandoffOutputItem
from agents.run import RunConfig
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Filesystem, Shell
from agents.sandbox.entries import LocalDir
from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions

try:
    from .policy import (
        avaliar_tarefa,
        caminho_sensivel_repositorio,
        contem_segredo_provavel,
        requer_revisao_seguranca,
    )
except ImportError:  # pragma: no cover - permite execução direta do arquivo
    from policy import (
        avaliar_tarefa,
        caminho_sensivel_repositorio,
        contem_segredo_provavel,
        requer_revisao_seguranca,
    )


NOME_PROJETO = "EJC"
NOME_FLUXO = "EJC - manutenção em sandbox"
NOME_REVISOR_SEGURANCA = "Revisor de Segurança EJC"
IMAGEM_SANDBOX_PADRAO = "ejc-agents-sandbox:0.22.2"


def _entrada_para_texto(valor: str | list[TResponseInputItem]) -> str:
    if isinstance(valor, str):
        return valor
    return "\n".join(str(item) for item in valor)


@input_guardrail(run_in_parallel=False)
async def guardrail_entrada_manutencao(
    contexto: RunContextWrapper[Any],
    agente: Agent[Any],
    entrada: str | list[TResponseInputItem],
) -> GuardrailFunctionOutput:
    del contexto, agente
    decisao = avaliar_tarefa(_entrada_para_texto(entrada))
    return GuardrailFunctionOutput(
        output_info=decisao.motivo,
        tripwire_triggered=not decisao.permitido,
    )


@output_guardrail
async def guardrail_saida_manutencao(
    contexto: RunContextWrapper[Any],
    agente: Agent[Any],
    saida: str,
) -> GuardrailFunctionOutput:
    del contexto, agente
    segredo_detectado = contem_segredo_provavel(saida)
    return GuardrailFunctionOutput(
        output_info="credencial provável detectada" if segredo_detectado else "saída aceita",
        tripwire_triggered=segredo_detectado,
    )


@contextmanager
def snapshot_rastreado(diretorio_repo: Path) -> Iterator[Path]:
    """Copia somente arquivos Git rastreados e não sensíveis para uma área temporária."""
    diretorio_repo = diretorio_repo.resolve()
    snapshot = Path(tempfile.mkdtemp(prefix=".agents-sandbox-", dir=diretorio_repo))

    try:
        resultado = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=diretorio_repo,
            check=True,
            capture_output=True,
        )
        for caminho_bruto in resultado.stdout.split(b"\0"):
            if not caminho_bruto:
                continue

            relativo = Path(os.fsdecode(caminho_bruto))
            if relativo.is_absolute() or ".." in relativo.parts:
                raise RuntimeError(f"caminho Git inseguro: {relativo}")
            if caminho_sensivel_repositorio(relativo.as_posix()):
                continue

            origem = diretorio_repo / relativo
            if origem.is_symlink():
                raise RuntimeError(
                    f"symlink rastreado não é materializado por segurança: {relativo}"
                )
            if not origem.is_file():
                continue

            destino = snapshot / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)

        yield snapshot
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def resultado_tem_handoff_seguranca(itens: Iterable[Any]) -> bool:
    """Confirma que ocorreu handoff real para o revisor de segurança configurado."""
    for item in itens:
        if not isinstance(item, HandoffOutputItem):
            continue
        agente_destino = item.target_agent
        if agente_destino is not None and agente_destino.name == NOME_REVISOR_SEGURANCA:
            return True
    return False


def criar_opcoes_docker(imagem: str) -> DockerSandboxClientOptions:
    """Cria a configuração obrigatória de isolamento do sandbox."""
    return DockerSandboxClientOptions(
        image=imagem,
        network_mode="none",
        labels={
            "com.s2corporativo.projeto": "ejc",
            "com.s2corporativo.finalidade": "manutencao-agentes",
        },
    )


def construir_agente(origem_snapshot: Path, modelo: str) -> SandboxAgent[None]:
    revisor_independente = Agent(
        name="Revisor Independente EJC",
        model=modelo,
        instructions=(
            "Atue como revisor independente de uma alteração de manutenção do EJC. "
            "Revise somente o resumo do diff, as evidências de teste e os riscos fornecidos pelo "
            "orquestrador. Verifique ampliação indevida de escopo, risco de regressão, testes "
            "ausentes, exposição de segurança/LGPD e violações da governança do repositório. "
            "Não solicite deploy e nunca invente resultado de teste."
        ),
        output_guardrails=[guardrail_saida_manutencao],
    )

    revisor_seguranca = Agent(
        name=NOME_REVISOR_SEGURANCA,
        model=modelo,
        handoff_description=(
            "Revisão final obrigatória para autenticação, autorização, uploads, CI/CD, "
            "dependências, core/middlewares, migrations, segurança ou código próximo de produção."
        ),
        instructions=(
            "Faça revisão final de segurança e governança usando somente as evidências da conversa. "
            "Não execute ferramentas nem declare verificações não observadas. Informe bloqueios, "
            "validações exigidas, riscos residuais e se a mudança é segura para permanecer em PR. "
            "Você não autoriza deploy de produção."
        ),
        output_guardrails=[guardrail_saida_manutencao],
    )

    handoff_seguranca = handoff(
        agent=revisor_seguranca,
        tool_name_override="transfer_to_security_review",
        tool_description_override=(
            "Transfira o controle para revisão final quando a tarefa tocar autenticação, "
            "permissões, uploads, CI/CD, dependências, core/middlewares, migrations, configuração "
            "de segurança ou comportamento próximo de produção."
        ),
    )

    return SandboxAgent(
        name="Orquestrador de Manutenção EJC",
        model=modelo,
        instructions=(
            "Trabalhe exclusivamente na cópia isolada em `repo/`. Leia primeiro `repo/AGENTS.md`, "
            "`repo/docs/GOVERNANCA_IA.md` e `repo/CLAUDE.md`, quando presentes. A cópia não possui "
            "`.git`. Nunca faça push, merge, deploy, acesso a produção, leitura de segredos do host "
            "ou operação fora do workspace. Faça a menor alteração capaz de resolver a tarefa. "
            "Execute apenas verificações proporcionais ao diff e nunca invente resultado de teste. "
            "Se alterar arquivos, chame `revisao_independente` com resumo objetivo do diff e os "
            "comandos/resultados realmente observados. Tarefas sensíveis devem obrigatoriamente "
            "ser transferidas ao revisor de segurança; essa exigência também é validada em código. "
            "A saída final deve registrar causa, arquivos alterados, verificações executadas, "
            "resultados e riscos residuais, sem segredos ou dados reais de clientes."
        ),
        default_manifest=Manifest(entries={"repo": LocalDir(src=origem_snapshot)}),
        capabilities=[Filesystem(), Shell()],
        tools=[
            revisor_independente.as_tool(
                tool_name="revisao_independente",
                tool_description=(
                    "Revise o resumo de uma alteração proposta e as evidências de validação antes "
                    "de o orquestrador concluir a tarefa."
                ),
            )
        ],
        handoffs=[handoff_seguranca],
        input_guardrails=[guardrail_entrada_manutencao],
        output_guardrails=[guardrail_saida_manutencao],
    )


def criar_cliente_docker(imagem: str) -> DockerSandboxClient:
    """Conecta ao Docker local e exige que a imagem dedicada já esteja construída."""
    try:
        cliente_sdk = docker_from_env()
        cliente_sdk.ping()
        cliente_sdk.images.get(imagem)
    except ImageNotFound as exc:
        raise RuntimeError(
            "imagem do sandbox ausente; execute: "
            f"docker build -t {imagem} -f ops/agents/Dockerfile.sandbox ."
        ) from exc
    except DockerException as exc:
        raise RuntimeError(f"Docker indisponível para o sandbox: {exc}") from exc

    return DockerSandboxClient(cliente_sdk)


async def executar_tarefa(tarefa: str, diretorio_repo: Path, modelo: str, imagem: str) -> str:
    diretorio_repo = diretorio_repo.resolve()
    if not (diretorio_repo / ".git").exists():
        raise RuntimeError(f"checkout Git do EJC não encontrado: {diretorio_repo}")

    diretorio_original = Path.cwd()
    try:
        os.chdir(diretorio_repo)
        with snapshot_rastreado(diretorio_repo) as snapshot:
            origem_snapshot = snapshot.relative_to(diretorio_repo)
            agente = construir_agente(origem_snapshot=origem_snapshot, modelo=modelo)
            cliente = criar_cliente_docker(imagem)

            try:
                resultado = await Runner.run(
                    agente,
                    tarefa,
                    run_config=RunConfig(
                        sandbox=SandboxRunConfig(
                            client=cliente,
                            options=criar_opcoes_docker(imagem),
                            cwd="repo",
                        ),
                        workflow_name=NOME_FLUXO,
                        trace_include_sensitive_data=False,
                    ),
                )

                if requer_revisao_seguranca(tarefa) and not resultado_tem_handoff_seguranca(
                    resultado.new_items
                ):
                    raise RuntimeError(
                        "tarefa sensível recusada: o handoff obrigatório para segurança não ocorreu"
                    )

                return str(resultado.final_output)
            finally:
                flush_traces()
    finally:
        os.chdir(diretorio_original)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa manutenção do EJC em snapshot isolado por Docker, sem rede."
    )
    parser.add_argument("tarefa", help="Tarefa de manutenção para o agente")
    parser.add_argument("--repo", default=".", help="Caminho do checkout Git do EJC")
    parser.add_argument(
        "--modelo",
        default=os.getenv("OPENAI_AGENTS_MODEL"),
        help="Nome do modelo ou variável OPENAI_AGENTS_MODEL",
    )
    parser.add_argument(
        "--imagem",
        default=os.getenv("EJC_AGENTS_SANDBOX_IMAGE", IMAGEM_SANDBOX_PADRAO),
        help="Imagem Docker dedicada ao sandbox",
    )
    args = parser.parse_args()

    if not args.modelo:
        parser.error("informe --modelo ou defina OPENAI_AGENTS_MODEL")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error(
            "OPENAI_API_KEY é exigida pelo processo host e não é enviada ao container sandbox"
        )

    try:
        saida = asyncio.run(
            executar_tarefa(args.tarefa, Path(args.repo), args.modelo, args.imagem)
        )
    except InputGuardrailTripwireTriggered:
        print("BLOQUEADO_GUARDRAIL_ENTRADA: tarefa solicitou ação protegida ou destrutiva")
        return 2
    except OutputGuardrailTripwireTriggered:
        print("BLOQUEADO_GUARDRAIL_SAIDA: saída candidata correspondeu a padrão de credencial")
        return 3
    except RuntimeError as exc:
        print(f"ERRO_EXECUCAO: {exc}")
        return 4

    print(saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
