"""Enforcement de oab_restricted em executar_skill (IA-04 Fase 1b).

Antes, oab_restricted era coluna descritiva sem gate em runtime. Agora skills
restritas só executam para roles com credencial OAB; o gate roda ANTES de
qualquer chamada ao provedor (sem custo/vazamento para perfil não autorizado).
"""
import pytest

from app.models.ai_skill import EjcSkill
from app.services import ai_skill_service


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """Sessão fake: devolve sempre a mesma skill em execute()."""

    def __init__(self, skill):
        self._skill = skill

    async def execute(self, *a, **k):
        return _Res(self._skill)


def _skill(oab_restricted: bool) -> EjcSkill:
    return EjcSkill(
        id="s1", name="parecer_restrito", display_name="Parecer",
        system_prompt="Redija o parecer.", engine="groq", area="juridico",
        active=True, oab_restricted=oab_restricted,
    )


async def test_role_sem_credencial_e_bloqueado_antes_do_provedor():
    db = _FakeDB(_skill(oab_restricted=True))
    with pytest.raises(PermissionError):
        await ai_skill_service.executar_skill(
            db=db, skill_name="parecer_restrito", query="analise isto",
            user_id="u1", user_role="estagiario",
        )


async def test_role_ausente_e_bloqueado_em_skill_restrita():
    db = _FakeDB(_skill(oab_restricted=True))
    with pytest.raises(PermissionError):
        await ai_skill_service.executar_skill(
            db=db, skill_name="parecer_restrito", query="analise isto",
            user_id="u1", user_role=None,
        )


async def test_skill_nao_restrita_nao_exige_credencial():
    # Não deve levantar PermissionError; falha adiante (sem provedor real) é OK —
    # o que importa é passar do gate. Garantimos que NÃO é PermissionError.
    db = _FakeDB(_skill(oab_restricted=False))
    try:
        await ai_skill_service.executar_skill(
            db=db, skill_name="parecer_restrito", query="analise isto",
            user_id="u1", user_role="estagiario",
        )
    except PermissionError:
        pytest.fail("skill não restrita não deveria bloquear por role")
    except Exception:
        pass  # qualquer outra falha (provedor/gateway) é aceitável neste teste
