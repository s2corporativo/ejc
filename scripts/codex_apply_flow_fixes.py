#!/usr/bin/env python3
"""Aplica ajustes pontuais de fluxo em arquivos extensos do frontend.

Temporário e idempotente: cada substituição exige o padrão original ou aceita o
estado já corrigido. Não acessa rede, banco, credenciais ou arquivos de ambiente.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Revisão 2: novo push intencional para acionar o workflow já registrado.


def replace_once(path: str, old: str, new: str) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        raise RuntimeError(f"Padrão não encontrado em {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def replace_all(path: str, old: str, new: str) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        return False
    target.write_text(text.replace(old, new), encoding="utf-8")
    return True


def main() -> None:
    changed: list[str] = []

    def once(path: str, old: str, new: str) -> None:
        if replace_once(path, old, new):
            changed.append(path)

    def all_(path: str, old: str, new: str) -> None:
        if replace_all(path, old, new):
            changed.append(path)

    # Dashboard: a Central unificada é a porta oficial de prazos.
    all_(
        "frontend/src/pages/DashboardModern.tsx",
        'to: "/prazos",',
        'to: "/atividades?tipo=prazo",',
    )

    # Cadastro documental/manual: continuar diretamente na jornada criada.
    once(
        "frontend/src/pages/Casos.tsx",
        'setModal(false);\n      nav("/casos", { replace: true });\n      setForm({ area: "civil", prioridade: "media", case_type: "judicial" });',
        'setModal(false);\n      nav(`/casos/${novo.id}/jornada`, { replace: true });\n      setForm({ area: "civil", prioridade: "media", case_type: "judicial" });',
    )
    once(
        "frontend/src/pages/Casos.tsx",
        'setPendencia(null);\n      setRascunhoSalvo(null);\n      setModal(false);\n      nav("/casos", { replace: true });',
        'setPendencia(null);\n      setRascunhoSalvo(null);\n      setModal(false);\n      nav(`/casos/${pendencia.caseId}/jornada`, { replace: true });',
    )

    # Caso: taxonomia única; remove lista local incompleta de áreas.
    once(
        "frontend/src/pages/CasoDetalhe.tsx",
        'import { RAMOS } from "./ramos/ramosConfig";\n',
        'import { RAMOS } from "./ramos/ramosConfig";\nimport { useAreas } from "../lib/areas";\n',
    )
    once(
        "frontend/src/pages/CasoDetalhe.tsx",
        '''  const TODAS = [
    "civil",
    "trabalhista",
    "consumidor",
    "familia",
    "ambiental",
    "criminal",
    "previdenciario",
    "empresarial",
    "tributario",
    "administrativo",
    "bancario",
    "imobiliario",
    "digital_lgpd",
  ];''',
        '  const TODAS = useAreas().map((area) => area.slug);',
    )

    # Clientes: cabeçalho passa a refletir a célula de ações existente.
    once(
        "frontend/src/pages/Clientes.tsx",
        '                <th className="px-4 py-3">Contato</th>\n                <th className="px-4 py-3">Status</th>',
        '                <th className="px-4 py-3 text-right">Ações</th>\n                <th className="px-4 py-3">Contato</th>\n                <th className="px-4 py-3">Status</th>',
    )

    # Portal: pluralização correta e legível.
    once(
        "frontend/src/pages/portal/PortalDashboard.tsx",
        'texto: `${mensagensNaoLidas} mensagem${mensagensNaoLidas > 1 ? "ns" : ""} nova${mensagensNaoLidas > 1 ? "s" : ""} do escritório`,',
        'texto: `${mensagensNaoLidas} ${mensagensNaoLidas > 1 ? "mensagens novas" : "mensagem nova"} do escritório`,',
    )

    # Central: deep-link de tipo e vínculo automático ao caso contextual.
    once(
        "frontend/src/pages/CentralAtividades.tsx",
        '  const [items, setItems] = useState<Activity[]>([]);',
        '  const tipoQuery = searchParams.get("tipo");\n  const casoQuery = searchParams.get("caso") || "";\n\n  const [items, setItems] = useState<Activity[]>([]);',
    )
    once(
        "frontend/src/pages/CentralAtividades.tsx",
        '  const [filterTipo, setFilterTipo] = useState<ItemType | "todos">("todos");',
        '  const [filterTipo, setFilterTipo] = useState<ItemType | "todos">(\n    tipoQuery && Object.prototype.hasOwnProperty.call(TIPO_CONFIG, tipoQuery)\n      ? (tipoQuery as ItemType)\n      : "todos",\n  );',
    )
    once(
        "frontend/src/pages/CentralAtividades.tsx",
        '      data: "",\n    });\n    setModal(true);',
        '      data: "",\n      case_id: casoQuery || undefined,\n    });\n    setModal(true);',
    )
    once(
        "frontend/src/pages/CentralAtividades.tsx",
        '          responsavel_id: form.responsavel_id || undefined,\n        });\n        toast.success("Prazo criado");',
        '          responsavel_id: form.responsavel_id || undefined,\n          case_id: form.case_id || casoQuery || undefined,\n        });\n        toast.success("Prazo criado");',
    )
    once(
        "frontend/src/pages/CentralAtividades.tsx",
        '          responsavel_id: form.responsavel_id || undefined,\n        });\n        toast.success("Tarefa criada");',
        '          responsavel_id: form.responsavel_id || undefined,\n          case_id: form.case_id || casoQuery || undefined,\n        });\n        toast.success("Tarefa criada");',
    )
    once(
        "frontend/src/pages/CentralAtividades.tsx",
        '          descricao: form.descricao || undefined,\n        });\n        const conf = extrairConflitos(data);',
        '          descricao: form.descricao || undefined,\n          case_id: form.case_id || casoQuery || undefined,\n        });\n        const conf = extrairConflitos(data);',
    )

    # Linguagem leiga nas telas centrais.
    all_(
        "frontend/src/pages/KnowledgeHub.tsx",
        'desc: "Leis, súmulas e doutrina indexadas para RAG",',
        'desc: "Leis, súmulas e referências indexadas para pesquisa",',
    )
    all_(
        "frontend/src/pages/KnowledgeHub.tsx",
        'label: "Base RAG",',
        'label: "Base de conhecimento",',
    )
    all_(
        "frontend/src/pages/Pecas.tsx",
        'Log HITL:',
        'Registro da revisão:',
    )
    all_(
        "frontend/src/pages/Configuracoes.tsx",
        'description: "Curadoria RAG, prompts sistêmicos e guardrails.",',
        'description: "Base de conhecimento, instruções da IA e regras de segurança.",',
    )

    unique = sorted(set(changed))
    print(f"Arquivos alterados: {len(unique)}")
    for path in unique:
        print(f"- {path}")


if __name__ == "__main__":
    main()
