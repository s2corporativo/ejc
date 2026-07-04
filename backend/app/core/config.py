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

    # ── Criptografia de PII em repouso (LGPD, achado C6 / Bloco 6a) ────────
    # Chave Fernet (32 bytes url-safe base64) para cpf/cnpj cifrados. Default
    # vazio de propósito — mesmo padrão do SECRET_KEY: obrigatória em produção
    # (validada abaixo), efêmera em desenvolvimento. TROCAR A CHAVE DEPOIS DE
    # GERADA INUTILIZA todo dado já cifrado com a anterior — nunca regenerar
    # em produção sem plano de re-criptografia.
    PII_ENCRYPTION_KEY: str = ""
    # Chave HMAC para o índice cego (hash determinístico de cpf/cnpj — permite
    # busca exata/dedup/conflito de interesses sem expor o valor em texto
    # puro). Pode ser a mesma PII_ENCRYPTION_KEY, mas mantida separada por
    # higiene de chaves (rotacionar uma não invalida a outra).
    PII_HASH_KEY: str = ""

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

    # ── IA — Anthropic (Claude) — módulo IA profissional por tarefa ───────
    # Chave OBRIGATÓRIA para usar Claude (router.py/anthropic_provider.py).
    # NUNCA hardcodar aqui: definir o valor real APENAS no .env. Vazio = Claude
    # indisponível e o gateway faz fallback para Groq.
    ANTHROPIC_API_KEY: str = ""
    # Modelos configuráveis sem deploy (via .env).
    # RAPIDO  = tarefas factuais/médias (Haiku — barato: $1/$5 por 1M tokens).
    # COMPLEXO = análise estratégica, dossiês, minutas, pesquisa (Opus 4.8 —
    #            máxima qualidade jurídica: $5/$25 por 1M tokens). Para reduzir
    #            custo, definir no .env: claude-sonnet-5 ($3/$15, quase Opus)
    #            ou claude-haiku-4-5-20251001.
    ANTHROPIC_MODEL_RAPIDO: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_MODEL_COMPLEXO: str = "claude-opus-4-8"
    # Profundidade de raciocínio nos modelos modernos (Opus 4.7+/Sonnet 5):
    # low | medium | high. "high" = mais rigor em tarefas jurídicas sensíveis.
    ANTHROPIC_EFFORT: str = "high"
    # Liga/desliga o provider Anthropic sem remover a chave do .env.
    ANTHROPIC_ENABLED: bool = True
    # Timeout do client Anthropic (segundos) — tarefas complexas podem demorar.
    ANTHROPIC_TIMEOUT_SECONDS: int = 120
    # Teto DURO de tokens de saída por chamada (controle de custo).
    # Qualquer max_tokens acima disto é rebaixado no provider.
    ANTHROPIC_MAX_TOKENS: int = 8000

    # ── IA — Núcleo Único (policy central de provedores) ──────────────────
    # False = só Ollama local (soberania total): nenhum dado sai do VPS,
    # mesmo sanitizado. Anthropic/Groq ficam inelegíveis na cadeia.
    AI_EXTERNAL_PROVIDERS_ALLOWED: bool = True
    # True = todo conteúdo destinado a provider EXTERNO (Anthropic/Groq) passa
    # por sanitizar_pii + validar_sem_pii; PII residual bloqueia o envio (LGPD).
    # NUNCA desligar em produção sem parecer do encarregado de dados.
    AI_REQUIRE_SANITIZATION_FOR_EXTERNAL: bool = True
    # True = toda saída de IA é rascunho com revisão humana obrigatória (OAB).
    AI_REQUIRE_HITL: bool = True
    # Ordem de preferência entre provedores ELEGÍVEIS (csv). A policy ainda
    # filtra por habilitação/chave e prioriza Anthropic em tarefas complexas.
    AI_PROVIDER_PRIORITY: str = "ollama,anthropic,groq"

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

    # ── Embeddings locais/remotos (busca semântica RAG) ─────────────────
    # local = fastembed (ONNX, sem torch) no mesmo processo; http = serviço interno separado.
    # Default True: fastembed é dependência pinada (requirements.txt) e o
    # fallback é gracioso — falha/erro/import ausente → gerar_embeddings()
    # retorna None e o RAG cai para busca textual (ver embedding_service.py
    # e ai_service.buscar_contexto_rag), sem exceção ao chamador.
    EMBEDDINGS_ENABLED: bool = True
    EMBEDDINGS_PROVIDER: str = "local"  # local | http
    EMBEDDINGS_API_URL: str = "http://embeddings:8010/embed"
    EMBEDDINGS_TIMEOUT: int = 120

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
    # Default True: cadeia de fallback do ai_gateway (_resolver_cadeia/chat)
    # já trata Ollama indisponível/sem host de forma graciosa — connection
    # refused/DNS falha rápido, ollama_provider.chat() levanta RuntimeError
    # que o loop de `chat()` captura e segue para o próximo provedor
    # (Anthropic/Groq) sem quebrar a requisição do usuário. Sem um serviço
    # "ollama" no docker-compose, isso só passa a valer quando um for
    # provisionado — até lá, cai direto para o próximo provedor.
    OLLAMA_ENABLED: bool = True
    # Modelos disponíveis por categoria (ajuste ao hardware disponível)
    OLLAMA_MODEL_ANALISE: str = "deepseek-r1:8b"     # análise jurídica profunda
    OLLAMA_MODEL_PETICAO:  str = "qwen2.5:14b"       # elaboração de peças
    OLLAMA_MODEL_RESUMO:   str = "gemma3:9b"          # resumos rápidos
    OLLAMA_MODEL_CHAT:     str = "gemma3:9b"          # chat e perguntas simples
    OLLAMA_MODEL_CONTRATO: str = "deepseek-r1:8b"    # análise contratual
    OLLAMA_TIMEOUT: int = 180                         # modelos locais = mais lentos

    # ── AI Provider — seleção automática ──────────────────────────────────
    # "auto"      = Ollama (se habilitado) → Anthropic (se houver chave) → Groq
    # "groq"      = força Groq (nuvem, grátis)
    # "ollama"    = força Ollama (local) — falha se indisponível
    # "anthropic" = força Claude — sem chave, cai na cadeia automática
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
            # PII_ENCRYPTION_KEY/PII_HASH_KEY: NÃO geradas em produção mesmo se
            # ausentes — ao contrário do SECRET_KEY, uma chave efêmera aqui
            # corromperia dados cifrados silenciosamente a cada restart (perde
            # a chave, perde o dado). services/pii_crypto.py falha alto na
            # primeira tentativa real de cifrar/decifrar sem a chave definida.
            # Não travamos o BOOT do app para não quebrar produção que ainda
            # não migrou para o Bloco 6a (feature é opt-in até o backfill).
        elif not self.SECRET_KEY:
            # Desenvolvimento: gera chave efêmera para não travar o ambiente local.
            self.SECRET_KEY = secrets.token_urlsafe(64)
        if self.APP_ENV != "production" and (not self.PII_ENCRYPTION_KEY or not self.PII_HASH_KEY):
            # Só em desenvolvimento: chave efêmera para não travar o ambiente local.
            from cryptography.fernet import Fernet
            if not self.PII_ENCRYPTION_KEY:
                self.PII_ENCRYPTION_KEY = Fernet.generate_key().decode()
            if not self.PII_HASH_KEY:
                self.PII_HASH_KEY = secrets.token_urlsafe(32)
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
