# ── app/core/config.py ────────────────────────────────────────────────────────
# Configurações do EJC via variáveis de ambiente (.env).
# NUNCA hardcodar segredos neste arquivo.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from functools import lru_cache
from typing import List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import secrets


class Settings(BaseSettings):
    # ── Aplicação ─────────────────────────────────────────────────────────
    APP_NAME: str = "EJC — Ecossistema Jurídico Clovis"
    APP_VERSION: str = "3.0.0"
    APP_ENV: str = "development"          # development | production
    DEBUG: bool = False

    # ── Segurança / JWT ───────────────────────────────────────────────────
    # Default vazio de propósito: em produção a chave é OBRIGATÓRIA (validada
    # abaixo); em desenvolvimento, uma chave efêmera é gerada automaticamente.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Banco de dados (asyncpg) ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://ejc_user:ejc_pass@db:5432/ejc_db"
    # Versão sync para Alembic (mesmo host, driver diferente)
    DATABASE_URL_SYNC: str = "postgresql://ejc_user:ejc_pass@db:5432/ejc_db"

    # ── CORS ─────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── Upload de arquivos ────────────────────────────────────────────────
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_MB: int = 50

    # ── IA — Groq (dados sanitizados antes de envio — LGPD) ──────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"   # 128k (llama3-70b-8192 descomissionado pelo Groq)
    GROQ_TIMEOUT: int = 60               # segundos
    AI_ENABLED: bool = True

    # ── Notificações ──────────────────────────────────────────────────────
    ZAPI_INSTANCE_ID: str = ""
    ZAPI_TOKEN: str = ""
    ZAPI_CLIENT_TOKEN: str = ""
    WHATSAPP_ENABLED: bool = False

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587  # TLS (não usar 465/SSL)
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_ENABLED: bool = False

    # ── URLs ──────────────────────────────────────────────────────────────
    # URL pública do frontend — usada nos links dos e-mails
    FRONTEND_URL: str = "https://SEU_DOMINIO"

    # ── DataJud/CNJ (consulta processual) ────────────────────────────────
    # Chave pública divulgada pelo CNJ — pode ser sobrescrita via .env
    DATAJUD_ENABLED: bool = True
    DATAJUD_API_KEY: str = ""  # Configurar via .env

    # ── Embeddings locais (busca semântica RAG) ───────────────────────────
    # Requer: pip install -r requirements-ml.txt (sentence-transformers)
    EMBEDDINGS_ENABLED: bool = False

    # ── Web Push (alertas no celular via PWA) ────────────────────────────
    # Gerar chaves: python scripts/gen_vapid.py (uma vez no deploy)
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = "mailto:admin@depaulateixeira.adv.br"
    PUSH_ENABLED: bool = False

    # ── Groq — modelo de contexto longo (fallback para dossiês grandes) ──
    # llama-3.3-70b-versatile = 128k tokens; usado quando prompt > 20 000 chars.
    # (llama-3.1-70b-versatile foi DESCOMISSIONADO pelo Groq — não usar.)
    GROQ_MODEL_LARGE: str = "llama-3.3-70b-versatile"

    # ── Custo estimado Groq (R$ por 1.000.000 de tokens) — auditoria de gasto ──
    # Valores padrão 0; ajuste via .env conforme a fatura/câmbio.
    # Ollama (local) = custo zero por token.
    GROQ_PRECO_INPUT_BRL_POR_MILHAO:  float = 0.0
    GROQ_PRECO_OUTPUT_BRL_POR_MILHAO: float = 0.0

    # ── Ollama — modelos locais (soberania total, sem custo por token) ────
    # Instalar: ollama pull qwen2.5:14b && ollama pull deepseek-r1:8b etc.
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_ENABLED: bool = False   # habilitar apenas quando modelos estiverem instalados
    # Modelos disponíveis por categoria (ajuste ao hardware disponível)
    OLLAMA_MODEL_ANALISE: str = "deepseek-r1:8b"     # análise jurídica profunda
    OLLAMA_MODEL_PETICAO:  str = "qwen2.5:14b"       # elaboração de peças
    OLLAMA_MODEL_RESUMO:   str = "gemma3:9b"          # resumos rápidos
    OLLAMA_MODEL_CHAT:     str = "gemma3:9b"          # chat e perguntas simples
    OLLAMA_MODEL_CONTRATO: str = "deepseek-r1:8b"    # análise contratual
    OLLAMA_TIMEOUT: int = 180                         # modelos locais = mais lentos

    # ── AI Provider — seleção automática ──────────────────────────────────
    # "auto" = prefere Ollama se disponível, cai para Groq
    # "groq"  = força Groq (nuvem)
    # "ollama" = força Ollama (local) — falha se indisponível
    AI_PROVIDER: str = "auto"

    # ── Sentry — rastreamento de erros em produção ────────────────────────
    SENTRY_DSN: str = ""            # deixar vazio para desabilitar

    # ── Backup offsite (pg_dump via rclone no HOST) ───────────────────────
    BACKUP_REMOTE: str = ""         # ex: "b2:ejc-backups" (rclone remote)
    BACKUP_DIR: str = "/app/backups"  # diretório local de dumps dentro do container postgres
    BACKUP_RETENTION_DAYS: int = 7  # dumps locais mais antigos que isto são apagados na rotação

    # ── Scheduler ────────────────────────────────────────────────────────
    ENABLE_SCHEDULER: bool = True   # desligar em workers extras (uvicorn --workers)

    # ── Escritório (LGPD — identificação do controlador de dados) ─────────
    ESCRITORIO_NOME: str = "De Paula Teixeira Sociedade de Advogados"
    ESCRITORIO_CNPJ: str = "32.491.468/0001-12"
    ESCRITORIO_CIDADE: str = "Betim"
    ESCRITORIO_ESTADO: str = "MG"
    ESCRITORIO_EMAIL: str = "contato@depaulateixeira.adv.br"

    @model_validator(mode="after")
    def _validar_seguranca_producao(self):
        """
        Em produção, falha de forma explícita se o SECRET_KEY estiver ausente ou
        ainda for o placeholder do .env.example. Evita o cenário silencioso em que
        a chave aleatória de fallback muda a cada reinício e desloga todos os
        usuários (e impede rejeição de tokens entre eventuais réplicas).
        """
        if self.APP_ENV == "production":
            if not self.SECRET_KEY or self.SECRET_KEY.startswith("TROCAR"):
                raise ValueError(
                    "SECRET_KEY ausente ou placeholder em produção. "
                    "Gere uma chave: python3 -c \"import secrets; "
                    "print(secrets.token_urlsafe(64))\" e defina no .env."
                )
            if "SEU_DOMINIO" in getattr(self, 'FRONTEND_URL', ''):
                raise ValueError("FRONTEND_URL não configurada para produção.")
        elif not self.SECRET_KEY:
            # Desenvolvimento: gera chave efêmera para não travar o ambiente local.
            self.SECRET_KEY = secrets.token_urlsafe(64)
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
