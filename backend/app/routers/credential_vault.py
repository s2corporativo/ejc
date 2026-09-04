# ── app/routers/credential_vault.py ──────────────────────────────────────────
# Cofre de Credenciais — PR-3: API /cofre-credenciais (superadmin + step-up).
#
# NÃO confundir com routers/api_keys.py: o COFRE guarda segredos QUE O EJC USA
# para falar com serviços externos (DataJud, Groq, SMTP, NuvemFiscal…); api_keys.py
# emite chaves QUE O EJC FORNECE a integradores externos consumirem nossa API.
#
# Controles (decisões 5–7 do plano, docs/PLANO_COFRE_CREDENCIAIS.md):
#   * RBAC: TODAS as rotas exigem require_roles(["superadmin"]) — admin NÃO
#     opera o cofre (require_admin deixaria admin passar; aqui o piso é 9);
#   * step-up POR OPERAÇÃO mutadora: senha_atual (verify_password) + código
#     TOTP quando o usuário tem 2FA ativo — mesmo fluxo do alterar_senha e do
#     login em routers/auth.py (reusa _totp_secret_de/_recifrar_totp_legado);
#     falha → 403 com mensagem SEMPRE genérica ("Reautenticação falhou.", sem
#     revelar QUAL fator) + audit COFRE_REAUTH_FALHA com o motivo granular;
#   * o VALOR nunca volta pela API: response models só com last4 + metadados;
#   * aplicar_overlay roda NA MESMA requisição de escrita — o Settings
#     singleton reflete o cofre antes da resposta (requisito da auditoria).
#     Se o overlay falhar APÓS o commit, NÃO revertemos (estado eventualmente
#     consistente — o worker de sync reconcilia via versao_atual): sinalizamos
#     com audit COFRE_OVERLAY_FALHA + log alto e `overlay_aplicado=False` no
#     corpo (200/201), nunca uma inconsistência gravado-mas-não-aplicado
#     silenciosa (ver _aplicar_overlay_sinalizando);
#   * rate limit dirigido (app/core/rate_limit.py) nas rotas mutadoras;
#   * corrida de escrita concorrente (índice único parcial WHERE ativo)
#     → IntegrityError → 409; validação de formato/tipo → 422.
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import pyotp

from app.core.database import get_db
from app.core.log_sanitizer import safe_exception_log
from app.core.rate_limit import rate_limit
from app.core.security import require_roles, verify_password
from app.models.audit_log import criar_audit_log
from app.routers.auth import _recifrar_totp_legado, _totp_secret_de
from app.services import (
    credential_registry,
    credential_testers,
    credential_vault_service,
)
from app.services.security_service import obter_ip_real

logger = logging.getLogger("ejc.cofre")

router = APIRouter(prefix="/cofre-credenciais", tags=["Cofre de Credenciais"])

ENTIDADE_AUDIT = credential_vault_service.ENTIDADE_AUDIT

# Piso superadmin (nível 9): admin (8) recebe 403 — decisão explícita do plano.
_SUPERADMIN = require_roles(["superadmin"])


# ── Schemas de request (step-up) ─────────────────────────────────────────────

class ReauthReq(BaseModel):
    """Step-up de reautenticação por operação (padrão alterar_senha)."""
    senha_atual: str = Field(min_length=1)
    codigo_totp: str | None = Field(None, min_length=6, max_length=6)


class CadastrarCredencialReq(ReauthReq):
    valor: str = Field(min_length=1, max_length=4096)


# ── Schemas de response — SEM NENHUM campo de valor (decisão 5 do plano) ─────

class CredencialMeta(BaseModel):
    """Metadados exibíveis de uma versão. Nunca contém o segredo."""
    id: str
    provider_key: str
    field_key: str
    tipo: str
    last4: str | None = None
    versao: int
    ativo: bool
    origem: str
    expires_at: datetime | None = None
    last_test_at: datetime | None = None
    last_test_status: str | None = None
    last_test_detail: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    revoked_at: datetime | None = None
    # False = a linha foi gravada/commitada, mas o overlay no Settings singleton
    # falhou DEPOIS do commit (ver _aplicar_overlay_sinalizando). A operação NÃO
    # é revertida (estado eventualmente consistente); o worker de sync recompõe
    # via versao_atual. O cliente pode alertar/forçar reload ao ver False.
    overlay_aplicado: bool = True


class CampoStatus(BaseModel):
    """Campo esperado pelo catálogo + estado da credencial vigente (se houver)."""
    field_key: str
    tipo: str
    rotulo: str
    obrigatorio: bool
    estado: str  # configurada | ausente
    last4: str | None = None
    versao: int | None = None
    origem: str | None = None
    expires_at: datetime | None = None
    last_test_at: datetime | None = None
    last_test_status: str | None = None
    last_test_detail: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProviderStatus(BaseModel):
    provider_key: str
    campos: list[CampoStatus]


class ImportItem(BaseModel):
    provider: str
    field: str
    last4: str


class ImportResumo(BaseModel):
    total: int
    importados: list[ImportItem]
    overlay_aplicado: bool = True  # ver CredencialMeta.overlay_aplicado


class TesteResultado(BaseModel):
    """Resultado do teste de conexão — SEM valor (só o estado + metadados)."""
    provider_key: str
    estado: str  # configurada | ausente | invalida | expirada | sem_permissao | indisponivel
    detalhe: str
    last_test_at: datetime | None = None
    campos_atualizados: int = 0


# ── Step-up (reautenticação por operação) ────────────────────────────────────

async def _reautenticar(
    db: AsyncSession, cu, request: Request,
    senha_atual: str, codigo_totp: str | None, contexto: str,
) -> None:
    """Confirma a identidade do superadmin ANTES de qualquer mutação do cofre.

    Mesmo fluxo do alterar_senha/login (routers/auth.py): verify_password na
    senha atual e, se o usuário tem TOTP ativo, código de 6 dígitos validado
    com valid_window=1.

    Anti-oráculo (achado da auditoria): a resposta HTTP é SEMPRE a MESMA
    mensagem genérica ("Reautenticação falhou.") para senha errada, TOTP
    ausente, TOTP ilegível ou TOTP inválido — a resposta não pode revelar QUAL
    fator falhou (nem se a senha estava certa e só o TOTP faltou). O `motivo`
    granular (senha/totp_ausente/totp_ilegivel/totp) fica SÓ no audit
    COFRE_REAUTH_FALHA, nunca no corpo — sempre 403.
    """
    _DETALHE_GENERICO = "Reautenticação falhou."

    async def _falha(motivo: str) -> None:
        await criar_audit_log(
            db, cu.id, cu.role.value, "COFRE_REAUTH_FALHA", ENTIDADE_AUDIT,
            None, detalhes=f"{contexto} motivo={motivo}",
            ip=obter_ip_real(request),
        )
        await db.commit()
        raise HTTPException(status_code=403, detail=_DETALHE_GENERICO)

    if not verify_password(senha_atual, cu.hashed_password):
        await _falha("senha")

    if getattr(cu, "totp_enabled", False):
        if not codigo_totp:
            await _falha("totp_ausente")
        secret, legado = _totp_secret_de(cu)
        if secret is None:
            await _falha("totp_ilegivel")
        if not pyotp.TOTP(secret).verify(codigo_totp, valid_window=1):
            await _falha("totp")
        # Segredo legado em claro → re-cifra oportunisticamente (commit da
        # própria operação do cofre, mesmo padrão do login).
        _recifrar_totp_legado(cu, secret, legado)


def _campo_ou_404(provider_key: str, field_key: str):
    campo = credential_registry.buscar_campo(provider_key, field_key)
    if campo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Campo '{provider_key}/{field_key}' não existe no catálogo "
                   "de credenciais.",
        )
    return campo


async def _aplicar_overlay_sinalizando(
    db: AsyncSession, cu, request: Request, contexto: str,
) -> bool:
    """Aplica o overlay no Settings singleton APÓS o commit da escrita.

    A escrita (cadastrar/revogar/importar_do_env) já commitou a linha; o
    overlay é o passo de propagação para o processo em memória. Se ELE falhar
    NÃO revertemos a operação — o estado é eventualmente consistente e o worker
    de sync recompõe via versao_atual. Só SINALIZAMOS: audit COFRE_OVERLAY_FALHA
    (sem segredo) + log alto com safe_exception_log, e devolvemos False para o
    handler marcar overlay_aplicado=False na resposta (nunca uma inconsistência
    silenciosa gravada-mas-não-aplicada). Retorna True em caso normal.
    """
    try:
        await credential_vault_service.aplicar_overlay(db)
        return True
    except Exception as e:  # noqa: BLE001 — overlay não pode derrubar a operação já commitada
        logger.error(
            "[cofre] overlay FALHOU após commit (%s) — linha gravada mas não "
            "propagada ao Settings; worker de sync deve reconciliar via "
            "versao_atual", contexto, extra=safe_exception_log(e),
        )
        # Estado consultável + reconciliação na API: enquanto não vingar, o
        # processo está com o `.env`, que não conhece revogação. O job
        # `cofre_overlay_retry` (scheduler) reaplica em minutos.
        credential_vault_service.marcar_overlay_falho(type(e).__name__)
        try:
            await criar_audit_log(
                db, cu.id, cu.role.value, "COFRE_OVERLAY_FALHA", ENTIDADE_AUDIT,
                None, detalhes=f"{contexto} — overlay não aplicado; reconciliar",
                ip=obter_ip_real(request),
            )
            await db.commit()
        except Exception:  # noqa: BLE001 — auditoria best-effort; o log alto acima já sinaliza
            logger.error("[cofre] falha ao auditar COFRE_OVERLAY_FALHA (%s)",
                         contexto, exc_info=True)
        return False


# ── Rotas ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProviderStatus],
            summary="Estado do cofre agrupado por provider (só metadados)")
async def listar_cofre(
    db: AsyncSession = Depends(get_db),
    cu=Depends(_SUPERADMIN),
):
    """Campos esperados pelo catálogo + estado (configurada/ausente) e
    metadados da versão vigente. O valor NUNCA aparece (só last4)."""
    linhas = await credential_vault_service.listar(db)
    ativas = {
        (m["provider_key"], m["field_key"]): m for m in linhas if m["ativo"]
    }
    resultado: list[ProviderStatus] = []
    for provider_key, campos in credential_registry.REGISTRY.items():
        status_campos = []
        for campo in campos:
            m = ativas.get((provider_key, campo.field_key))
            extras = {
                k: m[k] for k in (
                    "last4", "versao", "origem", "expires_at", "last_test_at",
                    "last_test_status", "last_test_detail", "created_at",
                    "updated_at",
                )
            } if m else {}
            status_campos.append(CampoStatus(
                field_key=campo.field_key,
                tipo=campo.tipo,
                rotulo=campo.rotulo,
                obrigatorio=campo.obrigatorio,
                estado="configurada" if m else "ausente",
                **extras,
            ))
        resultado.append(ProviderStatus(provider_key=provider_key,
                                        campos=status_campos))
    return resultado


@router.get("/{provider_key}/{field_key}/historico",
            response_model=list[CredencialMeta],
            summary="Histórico de versões de um campo (só metadados)")
async def historico_campo(
    provider_key: str, field_key: str,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_SUPERADMIN),
):
    _campo_ou_404(provider_key, field_key)
    linhas = await credential_vault_service.listar(db)
    return [
        m for m in linhas
        if m["provider_key"] == provider_key and m["field_key"] == field_key
    ]


@router.post("/importar-env", response_model=ImportResumo,
             dependencies=[Depends(rate_limit("cofre-credenciais", 5))],
             summary="Importa para o cofre os segredos presentes no .env")
async def importar_env(
    req: ReauthReq, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_SUPERADMIN),
):
    """Import assistido (idempotente): campos do catálogo com valor no .env e
    sem linha ativa viram registros origem=env_import. Resumo sem valores.

    Se o overlay pós-import falhar, `overlay_aplicado=False` sinaliza a
    inconsistência gravado-mas-não-aplicado (a operação NÃO é revertida — ver
    _aplicar_overlay_sinalizando)."""
    await _reautenticar(db, cu, request, req.senha_atual, req.codigo_totp,
                        "importar-env")
    importados = await credential_vault_service.importar_do_env(db, cu.id)
    overlay_ok = await _aplicar_overlay_sinalizando(
        db, cu, request, "importar-env")
    return {"total": len(importados), "importados": importados,
            "overlay_aplicado": overlay_ok}


@router.post("/{provider_key}/testar", response_model=TesteResultado,
             dependencies=[Depends(rate_limit("cofre-credenciais-teste", 10))],
             summary="Testa a conexão da integração e persiste o resultado")
async def testar_credencial(
    provider_key: str, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_SUPERADMIN),
):
    """Roda o testador de conexão do provider e persiste last_test_* nas linhas
    ativas (credential_vault_service.registrar_teste). Devolve APENAS o estado
    (configurada/ausente/invalida/expirada/sem_permissao/indisponivel) + o
    detalhe SEM segredo — o valor da credencial nunca aparece.

    NB: rota declarada ANTES de POST /{provider_key}/{field_key} para que
    /{provider_key}/testar não seja capturado como field_key='testar'. Não exige
    step-up: não expõe nem altera o segredo, só grava metadados do teste."""
    if not credential_registry.campos_do_provider(provider_key):
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_key}' não existe no catálogo de credenciais.",
        )
    estado, detalhe = await credential_testers.testar_provider(provider_key)
    return await credential_vault_service.registrar_teste(
        db, provider_key, estado, detalhe, user_id=cu.id,
    )


@router.post("/{provider_key}/{field_key}", response_model=CredencialMeta,
             status_code=201,
             dependencies=[Depends(rate_limit("cofre-credenciais", 5))],
             summary="Cadastra/substitui a credencial vigente de um campo")
async def cadastrar_credencial(
    provider_key: str, field_key: str,
    req: CadastrarCredencialReq, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_SUPERADMIN),
):
    """Grava a credencial (cifrada) e aplica o overlay NA MESMA requisição —
    a resposta traz APENAS os metadados da nova versão (nunca o valor).

    Se o overlay pós-commit falhar, a resposta segue 201 com
    `overlay_aplicado=False` (a linha JÁ está gravada; não revertemos — o
    worker de sync reconcilia via versao_atual). Ver
    _aplicar_overlay_sinalizando."""
    campo = _campo_ou_404(provider_key, field_key)
    await _reautenticar(db, cu, request, req.senha_atual, req.codigo_totp,
                        f"cadastrar {provider_key}/{field_key}")
    try:
        meta = await credential_vault_service.cadastrar(
            db, provider_key, field_key, req.valor, campo.tipo, cu.id,
        )
    except IntegrityError:
        # Corrida cadastrar × cadastrar no índice único parcial WHERE ativo:
        # outra requisição gravou a vigente entre o SELECT e o INSERT.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Escrita concorrente detectada para este campo. "
                   "Recarregue e tente novamente.",
        )
    except ValueError as e:
        # Validação de formato/tipo do service — a mensagem nunca ecoa o valor.
        raise HTTPException(status_code=422, detail=str(e))
    meta["overlay_aplicado"] = await _aplicar_overlay_sinalizando(
        db, cu, request, f"cadastrar {provider_key}/{field_key}")
    return meta


@router.delete("/{provider_key}/{field_key}", response_model=CredencialMeta,
               dependencies=[Depends(rate_limit("cofre-credenciais", 5))],
               summary="Revoga a credencial vigente de um campo")
async def revogar_credencial(
    provider_key: str, field_key: str,
    req: ReauthReq, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_SUPERADMIN),
):
    """Revoga (zera o ciphertext) e aplica o overlay na mesma requisição: o
    atributo em Settings vira \"\" — sem fallback ao .env.

    Se o overlay pós-commit falhar, a resposta segue 200 com
    `overlay_aplicado=False` (a revogação JÁ está gravada; não revertemos — o
    worker de sync reconcilia via versao_atual). Ver
    _aplicar_overlay_sinalizando."""
    _campo_ou_404(provider_key, field_key)
    await _reautenticar(db, cu, request, req.senha_atual, req.codigo_totp,
                        f"revogar {provider_key}/{field_key}")
    try:
        meta = await credential_vault_service.revogar(
            db, provider_key, field_key, cu.id,
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Não há credencial ativa para '{provider_key}/{field_key}'.",
        )
    meta["overlay_aplicado"] = await _aplicar_overlay_sinalizando(
        db, cu, request, f"revogar {provider_key}/{field_key}")
    return meta
