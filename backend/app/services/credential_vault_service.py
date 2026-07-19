# ── app/services/credential_vault_service.py ─────────────────────────────────
# Cofre de Credenciais — PR-2: serviço de escrita/leitura + overlay de runtime.
#
# Modelo de dados: ver models/integration_credential.py (migration 108).
# Catálogo: services/credential_registry.py — `field_key` é o nome EXATO do
# atributo em Settings; provider/field fora do catálogo é rejeitado aqui
# (ValueError), nunca vira setattr arbitrário no singleton.
#
# Overlay (aplicar_overlay):
#   * MUTAÇÃO IN-PLACE do singleton get_settings() (lru_cache) — os ~68
#     módulos que guardaram a referência enxergam o valor novo na hora.
#     NUNCA usar get_settings.cache_clear(): criaria um SEGUNDO objeto
#     Settings e split-brain entre módulos (risco nº 2 do plano).
#   * Precedência: linha ATIVA no cofre sobrepõe o .env; campo do catálogo
#     SEM linha ativa mas que JÁ teve linha (revogada/substituída sem
#     sucessora) vira "" explícito — revogação não pode cair de volta no
#     .env; campo nunca cadastrado não é tocado (o .env continua valendo).
#
# Segurança (decisões 3–7 do plano):
#   * o valor NUNCA sai por listar()/importar_do_env() — só last4 + metadados;
#   * substituição/revogação ZERA o valor_encrypted antigo (minimização LGPD);
#   * auditoria COFRE_* via criar_audit_log sem segredo nos detalhes.
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.integration_credential import IntegrationCredential
from app.services import credential_registry, vault_crypto

logger = logging.getLogger("ejc.cofre")

ENTIDADE_AUDIT = "integration_credentials"

# Tamanhos do domínio de valores — validação BÁSICA de formato por tipo
# (a validação real é o teste da integração, PR-4).
_LEN_MAX = 4096
_LEN_MIN_POR_TIPO = {
    "api_key": 8, "token": 8, "oauth_client": 8, "login": 1, "senha": 1,
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _validar_formato(valor: str, tipo: str) -> str:
    """Validação básica por tipo. Retorna o valor normalizado (strip).

    Levanta ValueError com mensagem SEM ecoar o valor (nada de segredo em
    mensagem de erro/log)."""
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("Valor da credencial vazio.")
    v = valor.strip()
    if len(v) > _LEN_MAX:
        raise ValueError(f"Valor da credencial excede {_LEN_MAX} caracteres.")
    if any(c in v for c in "\r\n\t\x00"):
        raise ValueError("Valor da credencial contém caracteres de controle.")
    # Chaves/tokens/logins não têm espaço interno; senha pode ter.
    if tipo != "senha" and " " in v:
        raise ValueError(f"Credencial do tipo '{tipo}' não pode conter espaços.")
    if len(v) < _LEN_MIN_POR_TIPO.get(tipo, 1):
        raise ValueError(
            f"Credencial do tipo '{tipo}' curta demais "
            f"(mínimo {_LEN_MIN_POR_TIPO[tipo]} caracteres)."
        )
    return v


def _campo_do_catalogo(provider_key: str, field_key: str):
    campo = credential_registry.buscar_campo(provider_key, field_key)
    if campo is None:
        raise ValueError(
            f"Campo '{provider_key}/{field_key}' não existe no catálogo de "
            "credenciais (credential_registry) — escrita rejeitada."
        )
    return campo


async def _linha_ativa(db, provider_key: str, field_key: str) -> IntegrationCredential | None:
    res = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.provider_key == provider_key,
            IntegrationCredential.field_key == field_key,
            IntegrationCredential.ativo.is_(True),
        )
    )
    return res.scalars().first()


def _meta(c: IntegrationCredential) -> dict[str, Any]:
    """Metadados exibíveis de uma linha — NUNCA inclui valor_encrypted."""
    return {
        "id": c.id,
        "provider_key": c.provider_key,
        "field_key": c.field_key,
        "tipo": c.tipo,
        "last4": c.last4,
        "versao": c.versao,
        "ativo": c.ativo,
        "origem": c.origem,
        "expires_at": c.expires_at,
        "last_test_at": c.last_test_at,
        "last_test_status": c.last_test_status,
        "last_test_detail": c.last_test_detail,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "revoked_at": c.revoked_at,
    }


# ── Escrita ───────────────────────────────────────────────────────────────────

async def cadastrar(
    db, provider_key: str, field_key: str, valor: str, tipo: str,
    user_id: str | None, origem: str = "manual",
) -> dict[str, Any]:
    """Grava (ou substitui) a credencial vigente de um campo do catálogo.

    * provider/field/tipo validados contra o credential_registry (ValueError);
    * valor cifrado com vault_crypto (MultiFernet); só last4 fica exibível;
    * se já existe versão ativa: desativa e ZERA o valor_encrypted antigo
      (histórico só de metadados) e cria a nova linha com versao = n+1.

    Retorna os metadados da nova linha (nunca o valor)."""
    campo = _campo_do_catalogo(provider_key, field_key)
    if tipo != campo.tipo:
        raise ValueError(
            f"Tipo '{tipo}' não confere com o catálogo para "
            f"'{provider_key}/{field_key}' (esperado '{campo.tipo}')."
        )
    v = _validar_formato(valor, tipo)

    anterior = await _linha_ativa(db, provider_key, field_key)
    # versao continua do MAIOR histórico do campo (inclui revogadas): um
    # re-cadastro após revogação não pode reiniciar em v1.
    res = await db.execute(
        select(func.max(IntegrationCredential.versao)).where(
            IntegrationCredential.provider_key == provider_key,
            IntegrationCredential.field_key == field_key,
        )
    )
    versao = int(res.scalar() or 0) + 1
    if anterior is not None:
        anterior.ativo = False
        anterior.valor_encrypted = None      # segredo antigo NÃO fica de histórico
        anterior.updated_at = _agora()
        # Libera o índice único parcial (WHERE ativo) antes do INSERT novo.
        await db.flush()

    nova = IntegrationCredential(
        id=str(uuid4()),
        provider_key=provider_key,
        field_key=field_key,
        tipo=tipo,
        valor_encrypted=vault_crypto.cifrar(v),
        last4=v[-4:],                        # máx. 4 chars — nunca o valor
        versao=versao,
        ativo=True,
        origem=origem,
        created_by=user_id,
    )
    db.add(nova)

    acao = "COFRE_ROTATE" if anterior is not None else (
        "COFRE_IMPORT_ENV" if origem == "env_import" else "COFRE_CREATE"
    )
    await criar_audit_log(
        db, user_id, None, acao=acao, entidade=ENTIDADE_AUDIT,
        registro_id=nova.id,
        detalhes=(
            f"{provider_key}/{field_key} v{versao} last4={nova.last4}"
        ),
    )
    await db.commit()
    return _meta(nova)


async def revogar(db, provider_key: str, field_key: str, user_id: str | None) -> dict[str, Any]:
    """Revoga a credencial vigente SEM substituta: desativa, ZERA o
    valor_encrypted e marca revoked_at/revoked_by. Após o próximo
    aplicar_overlay o atributo correspondente em Settings vira "" (sem
    fallback ao .env — revogação tem que revogar de verdade)."""
    _campo_do_catalogo(provider_key, field_key)
    linha = await _linha_ativa(db, provider_key, field_key)
    if linha is None:
        raise ValueError(
            f"Não há credencial ativa para '{provider_key}/{field_key}'."
        )
    linha.ativo = False
    linha.valor_encrypted = None
    linha.revoked_at = _agora()
    linha.revoked_by = user_id
    linha.updated_at = _agora()

    await criar_audit_log(
        db, user_id, None, acao="COFRE_REVOKE", entidade=ENTIDADE_AUDIT,
        registro_id=linha.id,
        detalhes=(
            f"{provider_key}/{field_key} v{linha.versao} last4={linha.last4}"
        ),
    )
    await db.commit()
    return _meta(linha)


# ── Leitura (metadados) ───────────────────────────────────────────────────────

async def listar(db) -> list[dict[str, Any]]:
    """Todas as linhas do cofre — SOMENTE metadados (o valor nunca sai)."""
    res = await db.execute(
        select(IntegrationCredential).order_by(
            IntegrationCredential.provider_key,
            IntegrationCredential.field_key,
            IntegrationCredential.versao.desc(),
        )
    )
    return [_meta(c) for c in res.scalars().all()]


async def versao_atual(db) -> tuple[int, str | None]:
    """Token barato de versão do cofre para o sync do worker Celery:
    (nº de linhas, MAX(updated_at) iso). Qualquer escrita muda o token."""
    res = await db.execute(
        select(
            func.count(IntegrationCredential.id),
            func.max(IntegrationCredential.updated_at),
        )
    )
    total, max_updated = res.one()
    return (
        int(total or 0),
        max_updated.isoformat() if isinstance(max_updated, datetime)
        else (str(max_updated) if max_updated else None),
    )


# ── Overlay de runtime ────────────────────────────────────────────────────────

async def resolver_overlay(db) -> dict[str, str]:
    """{field_key: valor decifrado} das credenciais ATIVAS do cofre."""
    conhecidos = set(credential_registry.todos_field_keys())
    res = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.ativo.is_(True),
            IntegrationCredential.valor_encrypted.is_not(None),
        )
    )
    overlay: dict[str, str] = {}
    for c in res.scalars().all():
        if c.field_key not in conhecidos:
            # Linha órfã (campo saiu do catálogo) — nunca vira setattr.
            logger.warning("[cofre] linha ativa fora do catálogo ignorada: %s/%s",
                           c.provider_key, c.field_key)
            continue
        overlay[c.field_key] = vault_crypto.decifrar(c.valor_encrypted)
    return overlay


async def aplicar_overlay(db) -> list[str]:
    """Aplica o cofre sobre o SINGLETON get_settings() (mutação in-place).

    Precedência por campo do catálogo:
      * linha ATIVA no cofre  → setattr(valor decifrado)  (sobrepõe o .env);
      * SEM ativa, mas JÁ teve linha (revogada/substituída sem sucessora)
        → setattr("") explícito — revogação NÃO cai de volta no .env;
      * nunca cadastrado → não toca (o .env continua valendo).

    NUNCA usar get_settings.cache_clear() — criaria um segundo Settings e
    split-brain entre os módulos que guardaram a referência antiga.

    Retorna a lista de field_keys efetivamente escritos (para log — sem valores)."""
    settings = get_settings()
    ativos = await resolver_overlay(db)

    # Campos do catálogo que já tiveram QUALQUER linha (histórico) — os que
    # estão sem ativa entre eles foram revogados/zerados → "" explícito.
    res = await db.execute(
        select(IntegrationCredential.field_key).distinct()
    )
    com_historico = {row[0] for row in res.all()}

    aplicados: list[str] = []
    for field_key in credential_registry.todos_field_keys():
        if field_key in ativos:
            setattr(settings, field_key, ativos[field_key])
            aplicados.append(field_key)
        elif field_key in com_historico:
            setattr(settings, field_key, "")   # revogada — sem fallback ao .env
            aplicados.append(field_key)
        # else: nunca cadastrado — vale o .env, não toca.
    return aplicados


# ── Import assistido do .env (base do PR-6) ──────────────────────────────────

async def importar_do_env(db, user_id: str | None) -> list[dict[str, str]]:
    """Importa para o cofre os campos do catálogo que têm valor não-vazio no
    Settings e AINDA não têm linha ativa (origem="env_import"). Idempotente:
    na segunda chamada os campos já têm linha ativa e são pulados.

    Retorna [{provider, field, last4}] — nunca os valores."""
    settings = get_settings()
    importados: list[dict[str, str]] = []
    for provider_key, campos in credential_registry.REGISTRY.items():
        for campo in campos:
            valor = getattr(settings, campo.field_key, "") or ""
            if not str(valor).strip():
                continue
            if await _linha_ativa(db, provider_key, campo.field_key) is not None:
                continue
            try:
                meta = await cadastrar(
                    db, provider_key, campo.field_key, str(valor), campo.tipo,
                    user_id, origem="env_import",
                )
            except ValueError as e:
                # Valor do .env fora do formato básico — pula sem abortar o
                # import dos demais (mensagem nunca ecoa o valor).
                logger.warning("[cofre] import do .env pulou %s/%s: %s",
                               provider_key, campo.field_key, e)
                continue
            importados.append({
                "provider": provider_key,
                "field": campo.field_key,
                "last4": meta["last4"],
            })
    return importados
