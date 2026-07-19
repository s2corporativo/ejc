#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend/src/pages/CasoDetalhe.tsx"
t = p.read_text(encoding="utf-8")


def once(old: str, new: str, label: str) -> None:
    global t
    n = t.count(old)
    if n != 1:
        raise SystemExit(f"{label}: esperado 1, encontrado {n}")
    t = t.replace(old, new, 1)


once(
    '  const [archiveModal, setArchiveModal] = useState(false);\n  const [archiveLoading, setArchiveLoading] = useState(false);\n  const [archiveReason, setArchiveReason] = useState("");\n',
    '',
    'estados duplicados',
)

start = t.index('  const arquivarCaso = async () => {')
end = t.index('  const gerarDocs = async () => {', start)
t = t[:start] + t[end:]

start = t.index('      <Modal\n        open={archiveModal}')
end = t.index('      <AreasCaso caso={caso} />', start)
t = t[:start] + t[end:]

once(
    'toast.error(\n        "Caso encerrado. Conhecimento registrado na base institucional (precedente RAG + memória + tese).",\n      );',
    'toast.success(\n        "Caso encerrado. Conhecimento registrado na base institucional (precedente + memória + tese).",\n      );',
    'toast encerramento',
)
once(
    'toast.error(\n        `${data.gerados?.length || 0} minuta(s) gerada(s): Procuração, Contrato de Honorários e Relatório Inicial. Veja na aba Documentos do caso.`,\n      );',
    'toast.success(\n        `${data.gerados?.length || 0} minuta(s) gerada(s): Procuração, Contrato de Honorários e Relatório Inicial. Veja na aba Documentos do caso.`,\n      );',
    'toast documentos',
)
once('precedente na RAG', 'precedente na base de conhecimento', 'texto RAG')
once('Alimentar a base de conhecimento (RAG)', 'Alimentar a base de conhecimento', 'checkbox RAG')

p.write_text(t, encoding='utf-8')
