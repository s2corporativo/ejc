# ── app/services/ai/agent/tools/registry.py ──────────────────────────────────
# Registro central de ferramentas do agente. Cada tool declara seu SCHEMA
# Anthropic (name/description/input_schema), se REQUER CONFIRMAÇÃO humana (HITL —
# escritas) e quais PAPÉIS podem vê-la. O loop consulta `schemas(role)` para
# expor só as tools permitidas ao modelo e `executar(...)` para rodar o handler.
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.services.ai.agent.tools.context import AgentContext

logger = logging.getLogger("ejc.ai.agent.registry")

# handler(args, ctx) -> dict (resultado serializável para o tool_result).
Handler = Callable[[dict, AgentContext], Awaitable[dict]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Handler
    requer_confirmacao: bool
    roles: tuple[str, ...] | None  # None = qualquer papel interno

    def schema_anthropic(self) -> dict:
        """Schema no formato que o provider Anthropic espera em `tools=`."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class _ToolArgError(ValueError):
    """Argumentos da tool inválidos contra o `input_schema` declarado."""


def _validar_args(spec: ToolSpec, args: dict) -> None:
    """Valida os argumentos do modelo contra o `input_schema` da tool.

    O `input_schema` é enviado ao provedor, mas o LLM pode devolver argumentos
    fora do contrato (campo faltando, tipo errado). Para tools de escrita isso é
    um efeito colateral real. Esta validação é a fronteira: falha ANTES do
    handler, sem tocar no banco. Cobre o subconjunto de JSON Schema usado pelas
    tools (`type`, `required`, `enum`) — suficiente para a superfície atual.
    """
    schema = spec.input_schema or {}
    props = schema.get("properties") or {}

    for campo in schema.get("required") or ():
        if campo not in args or args[campo] in (None, ""):
            raise _ToolArgError(
                f"Ferramenta '{spec.name}': campo obrigatório ausente: '{campo}'"
            )

    tipos = {"string": str, "integer": int, "number": (int, float),
             "boolean": bool, "array": list, "object": dict}
    for campo, valor in args.items():
        if campo not in props or valor is None:
            continue
        esperado = props[campo].get("type")
        py_tipo = tipos.get(esperado) if isinstance(esperado, str) else None
        if py_tipo is not None and not isinstance(valor, py_tipo):
            raise _ToolArgError(
                f"Ferramenta '{spec.name}': campo '{campo}' deve ser "
                f"{esperado}, recebido {type(valor).__name__}"
            )
        opcoes = props[campo].get("enum")
        if opcoes and valor not in opcoes:
            raise _ToolArgError(
                f"Ferramenta '{spec.name}': campo '{campo}' fora das opções "
                f"permitidas: {opcoes}"
            )


class _Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def registrar(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            # Idempotente contra reimport do módulo (ex.: reload em dev): mantém
            # a primeira definição e apenas avisa, sem derrubar o import.
            logger.warning("Tool '%s' já registrada — ignorando redefinição", spec.name)
            return
        self._tools[spec.name] = spec

    def _pode_ver(self, spec: ToolSpec, role: str) -> bool:
        return spec.roles is None or role in spec.roles

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def requer_confirmacao(self, name: str) -> bool:
        spec = self._tools.get(name)
        return bool(spec and spec.requer_confirmacao)

    def schemas(self, role: str, apenas_leitura: bool = False) -> list[dict]:
        """Schemas Anthropic das tools VISÍVEIS para `role`.

        `apenas_leitura=True` → exclui as tools de ESCRITA (requer_confirmacao),
        expondo ao modelo SOMENTE ferramentas de leitura. Usado por fluxos de
        raciocínio puro (ex.: análise "advogado sênior" do Raio-X) que jamais
        devem pausar em HITL; o default (False) preserva o comportamento atual."""
        return [s.schema_anthropic() for s in self._tools.values()
                if self._pode_ver(s, role)
                and not (apenas_leitura and s.requer_confirmacao)]

    def nomes_visiveis(self, role: str) -> set[str]:
        return {s.name for s in self._tools.values() if self._pode_ver(s, role)}

    async def executar(self, name: str, args: dict, ctx: AgentContext) -> dict:
        spec = self._tools.get(name)
        if spec is None:
            raise ValueError(f"Ferramenta desconhecida: {name}")
        # Defense-in-depth: mesmo que o modelo invente uma tool fora do papel,
        # a execução é barrada aqui (o schema já não é exposto por schemas()).
        if not self._pode_ver(spec, ctx.role):
            raise PermissionError(f"Papel '{ctx.role}' não pode usar a ferramenta '{name}'")
        _validar_args(spec, args or {})
        return await spec.handler(args or {}, ctx)


# Singleton do processo.
REGISTRY = _Registry()


def registrar_tool(
    name: str,
    description: str,
    input_schema: dict,
    requer_confirmacao: bool = False,
    roles: list[str] | tuple[str, ...] | None = None,
):
    """Decorator: registra `fn` como ferramenta do agente.

    - `requer_confirmacao=True` → tool de ESCRITA (HITL): o loop PAUSA e exige
      aprovação humana antes de executar.
    - `roles=None` → visível a qualquer papel interno; senão, só aos listados.
    """
    def _dec(fn: Handler) -> Handler:
        REGISTRY.registrar(ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=fn,
            requer_confirmacao=requer_confirmacao,
            roles=tuple(roles) if roles else None,
        ))
        return fn
    return _dec
