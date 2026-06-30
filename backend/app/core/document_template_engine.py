"""
Document Template Engine — renderiza documentos a partir dos modelos do Victory
Vault (tabela modelos_documentos) usando Jinja2.

Reescrito na auditoria 28/06/2026: antes os métodos eram síncronos mas chamavam
o VictoryVault (async) sem await — nunca funcionavam — e referenciavam um campo
`m.nome` inexistente no schema ModeloDocumento. Agora são async e usam os campos
corretos (id, tipo_documento, area_juridica, descricao).
"""
from typing import Dict, Any, List, Optional
from jinja2.sandbox import SandboxedEnvironment

from app.core.victory_vault import vault, ModeloDocumento

# Ambiente Jinja2 EM SANDBOX (corrige SSTI/RCE — auditoria 2026-06-30).
# O conteúdo do template vem do banco (Victory Vault, editável por usuário) e os
# dados são arbitrários; o `Template` padrão permitia acesso a __class__/__globals__
# → execução de código. O SandboxedEnvironment bloqueia atributos/chamadas inseguros.
_SANDBOX = SandboxedEnvironment(autoescape=False)


class DocumentTemplateEngine:
    async def render_document(self, template_id: str, data: Dict[str, Any]) -> str:
        modelo: Optional[ModeloDocumento] = await vault.get_modelo_por_id(template_id)
        if not modelo:
            raise ValueError(f"Modelo de documento com ID {template_id} não encontrado.")
        return _SANDBOX.from_string(modelo.conteudo_template).render(**(data or {}))

    async def list_available_templates(self, area_juridica: Optional[str] = None) -> List[Dict[str, str]]:
        modelos = await vault.get_modelos_documentos(area_juridica=area_juridica)
        return [{
            "id": m.id,
            "tipo_documento": m.tipo_documento,
            "area_juridica": m.area_juridica,
            "descricao": m.descricao or "",
        } for m in modelos]
