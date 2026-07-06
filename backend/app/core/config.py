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
    # Gate anti-alucinação de citações (Fase 4 — citation_gate.py):
    #   "bloquear"  → saída de IA com citação bloqueante (suspeita de alucinação,
    #                 menção genérica ou julgado sem tribunal+data) NÃO pode ser
    #                 aprovada no HITL sem override justificado do revisor;
    #   "marcar"    → relatório de citações anexado/exposto ao revisor (default);
    #   "desligado" → verificação de citações não roda nos fluxos de IA.
    CITACOES_POLITICA: str = "marcar"
    # ── Modo Duas IAs (Fase 5 — validação adversarial) ────────────────────
    # True = peças de alta complexidade geradas pelo Núcleo de IA recebem uma
    # SEGUNDA passada por uma IA Crítica/Adversarial (advogado da parte
    # contrária + magistrado), preferindo provider DIFERENTE do que gerou a
    # peça (diversidade reduz erro correlacionado). Default OFF — dobra o
    # custo por peça. A crítica NUNCA bloqueia a entrega: falhou → anexa
    # aviso "crítica indisponível" e o revisor HITL segue normalmente.
    DUAS_IAS_ENABLED: bool = False
    # CSV de task_types do ai_gateway que disparam a crítica automática
    # (vocabulário de TASK_ROUTING; aliases como "redacao_peca" são
    # normalizados antes da comparação).
    DUAS_IAS_TASK_TYPES: str = "elaboracao_peca,auditoria_peca"
    # Ordem de preferência entre provedores ELEGÍVEIS (csv). A policy ainda
    # filtra por habilitação/chave e prioriza Anthropic em tarefas complexas.
    AI_PROVIDER_PRIORITY: str = "ollama,anthropic,groq"
    # ── Níveis de sanitização de PII por tipo de tarefa (LGPD art. 33/46) ─────
    # JSON OPCIONAL (string) mapeando task_type → modo de sanitização, que
    # SOBREPÕE o default de app/services/ai/sanitization_policy.py. Modos:
    # "local_completo" (só Ollama local; nunca externo), "externo_pseudonimizado"
    # (pseudonimiza reversível → externo → reidrata), "extracao_local" (extração
    # estruturada local) e "mascaramento" (irreversível — legado). Vazio = usa o
    # default (revisável por Dr. Clovis). Ex.: {"familia":"local_completo"}.
    # Fail-safe: JSON inválido ou modo desconhecido é ignorado (cai no default).
    AI_SANITIZATION_MODE_MAP: str = ""
    # ── Intake de documentos (importação inteligente) ─────────────────────
    # True (default) = a interpretação do documento importado usa a cadeia
    # automática do gateway (ollama→anthropic→groq): se o Ollama local cair,
    # o texto — JÁ SANITIZADO (sanitizar_pii + barreira final do gateway) —
    # pode ir a provedor EXTERNO (EUA → transferência internacional, art. 33
    # LGPD; o dado pessoal exato NUNCA sai, é extraído localmente por regex).
    # False = fail-closed: intake só usa Ollama local; indisponível → a
    # importação degrada com erro claro citando esta flag.
    INTAKE_EXTERNAL_FALLBACK: bool = True

    # ── Fase 6 — Roteamento inteligente por complexidade/custo ────────────
    # False (default) = comportamento atual por task_type intacto. Quando True,
    # o model_router (heurística DETERMINÍSTICA, sem IA) propõe o provedor de
    # PARTIDA da cadeia por complexidade estimada do input; o gateway AINDA
    # aplica elegibilidade/kill-switch/barreira PII e o fallback continua.
    ROTEAMENTO_INTELIGENTE_ENABLED: bool = False
    # Provedor preferido por TIER de complexidade (o roteador só PROPÕE; se
    # inelegível, o gateway ignora e usa a cadeia normal por prioridade).
    ROTEAMENTO_PROVIDER_LEVE: str = "groq"       # rápido/barato p/ tarefas leves
    ROTEAMENTO_PROVIDER_MEDIO: str = "ollama"    # local, custo zero
    ROTEAMENTO_PROVIDER_PESADO: str = "anthropic"  # modelo forte p/ raciocínio
    # Limiares (score inteiro) que separam os tiers leve|medio|pesado.
    ROTEAMENTO_LIMIAR_MEDIO: int = 3
    ROTEAMENTO_LIMIAR_PESADO: int = 6

    # ── Fase 6 — Observabilidade de IA (Langfuse SELF-HOSTED) ─────────────
    # Langfuse é SELF-HOSTED (docker-compose, perfil "observability"): dados
    # jurídicos NÃO saem do ambiente. NUNCA apontar para cloud.langfuse.com.
    # Default OFF: quando desligado, o wrapper é NO-OP total (não importa o SDK,
    # não abre conexão) e o fluxo de IA nunca quebra por causa do tracing.
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_HOST: str = "http://langfuse:3000"  # serviço self-hosted no compose
    LANGFUSE_PUBLIC_KEY: str = ""                # secret — só no .env
    LANGFUSE_SECRET_KEY: str = ""                # secret — só no .env
    # LGPD: por padrão o Langfuse recebe SÓ metadados (task_type, provider,
    # modelo, tokens, latência, custo, sucesso/erro) — NUNCA prompt/resposta
    # crus (podem conter PII). Ligar True só envia conteúdo APÓS passar pela
    # MESMA sanitização PII do gateway. Não ligar sem parecer do DPO.
    LANGFUSE_CAPTURE_CONTENT: bool = False

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

    # ── DJEN / API Comunica CNJ (Res. CNJ 569/2024) — ingestão RAG ───────
    # Ingestor diário de comunicações processuais (intimações/publicações)
    # por OAB monitorada. A retenção da API é limitada — o RAG do EJC é o
    # arquivo histórico permanente. Desligado por padrão (opt-in no .env).
    DJEN_INGEST_ENABLED: bool = False
    # CSV "numero/UF" — ex.: "12345/MG,67890/MG". Vazio = ingestor no-op.
    DJEN_OABS_MONITORADAS: str = ""
    # Janela incremental (dias para trás) de cada coleta diária. 2 dias dá
    # margem para atraso de disponibilização sem reprocessar demais (o upsert
    # é idempotente por chave_origem, então sobreposição é inofensiva).
    DJEN_INGEST_JANELA_DIAS: int = 2

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

    # ── Parâmetros jurídicos atualizáveis por decreto (via .env) ──────────
    # Salário mínimo nacional VIGENTE — usado nas calculadoras (alimentos,
    # dano moral etc.). ATUALIZAR anualmente pelo decreto; valor default é o
    # último decreto conhecido (2025: R$ 1.518,00).
    SALARIO_MINIMO_BRL: float = 1518.00

    # ── Sentry — rastreamento de erros em produção ────────────────────────
    SENTRY_DSN: str = ""            # deixar vazio para desabilitar

    # ── Governança de custo de IA ─────────────────────────────────────────
    # Alerta de gasto no painel de Governança da IA: se o custo estimado de IA
    # no período exceder este valor (R$), o painel sinaliza. 0 = sem alerta.
    AI_BUDGET_ALERTA_BRL: float = 0.0

    # ── Backup offsite (pg_dump via rclone no HOST) ───────────────────────
    BACKUP_REMOTE: str = ""         # ex: "b2:ejc-backups" (rclone remote)
    BACKUP_DIR: str = "/app/backups"  # diretório local de dumps dentro do container postgres
    BACKUP_RETENTION_DAYS: int = 7  # dumps locais mais antigos que isto são apagados na rotação

    # ── Scheduler ────────────────────────────────────────────────────────
    ENABLE_SCHEDULER: bool = True   # desligar em workers extras (uvicorn --workers)

    # ── Fila assíncrona (Celery + Redis — Fase 3A) ────────────────────────
    # CELERY_ENABLED=False (default) preserva o comportamento atual: tarefas
    # de indexação rodam em BackgroundTasks no próprio processo da API.
    # True (definido no docker-compose quando o serviço `worker` existe)
    # despacha para o worker Celery via Redis; se o Redis estiver fora do ar,
    # o dispatcher (app/tasks/dispatcher.py) cai de volta para BackgroundTasks
    # — fallback gracioso, mesmo espírito de embeddings/IA.
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_ENABLED: bool = False

    # Cache de resposta da IA (opt-in): evita refazer a chamada ao provedor —
    # e o custo em tokens — quando a MESMA requisição (task_type + messages +
    # parâmetros) se repete numa janela curta (ex.: reenvio após falha de rede,
    # ou dois membros pedindo a mesma análise). Default DESLIGADO: comportamento
    # idêntico ao atual. Requer Redis; se indisponível, cai para "sem cache"
    # (fallback gracioso, mesmo espírito do dispatcher/embeddings). Só armazena
    # respostas bem-sucedidas; TTL curto para não servir análise obsoleta.
    AI_RESPONSE_CACHE_ENABLED: bool = False
    AI_RESPONSE_CACHE_TTL: int = 300  # segundos

    # Rate limit distribuído (multi-worker): False (default) usa contador
    # fixed-window em memória — correto só com uvicorn --workers 1. True passa
    # a contar no Redis (compartilhado entre processos), habilitando >1 worker.
    # Redis fora do ar → fallback gracioso para o contador em memória (nunca
    # bloqueia a request por indisponibilidade de infra).
    RATE_LIMIT_REDIS_ENABLED: bool = False

    # Observabilidade — logging. LOG_JSON=False (default) mantém o formato
    # texto atual; True emite uma linha JSON por log (ts/level/logger/msg +
    # excecao), pronto para agregadores (Loki/ELK/CloudWatch). LOG_LEVEL
    # controla o nivel raiz.
    LOG_JSON: bool = False
    LOG_LEVEL: str = "INFO"

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
        # Canoniza casing/espaços antes de qualquer gate. Sem isto, "Production"
        # ou " production " escapavam do ramo de produção e caíam no de dev, que
        # AUTOGERA chave PII efêmera — corrompendo CPF/CNPJ cifrados a cada
        # restart. Persiste o valor normalizado para todo `== "production"` a
        # jusante ver o mesmo canônico.
        self.APP_ENV = (self.APP_ENV or "").strip().lower()
        if self.APP_ENV == "production":
            if not self.SECRET_KEY or self.SECRET_KEY.startswith("TROCAR"):
                raise ValueError(
                    "SECRET_KEY ausente ou placeholder em produção. "
                    "Gere uma chave: python3 -c \"import secrets; "
                    "print(secrets.token_urlsafe(64))\" e defina no .env."
                )
            if "SEU_DOMINIO" in getattr(self, 'FRONTEND_URL', ''):
                raise ValueError("FRONTEND_URL não configurada para produção.")
            # CORS wildcard em produção é proibido: o app usa
            # allow_credentials=True (cookies/Authorization), e "*" com
            # credenciais permitiria qualquer origem ler respostas
            # autenticadas. Falha explícita no boot em vez de expor em runtime.
            if "*" in self.cors_origins_list:
                raise ValueError(
                    "CORS_ORIGINS não pode conter '*' em produção "
                    "(allow_credentials=True). Liste os domínios exatos do "
                    "frontend, ex.: CORS_ORIGINS=https://app.seu-dominio.adv.br"
                )
            # PII_ENCRYPTION_KEY/PII_HASH_KEY: EXIGIDAS no boot em produção. O
            # cadastro/edição de cliente faz dual-write incondicional de CPF/CNPJ
            # cifrado + hash cego (routers/clients.py, migration 061) — sem as
            # chaves, o PRIMEIRO cadastro com documento estoura em runtime, não
            # no deploy. Falhar aqui é estritamente mais seguro e NÃO gera chave
            # efêmera: continuamos jamais autogerando em produção (uma chave
            # volátil corromperia dados cifrados a cada restart). Exigimos apenas
            # que o operador defina uma chave estável antes de subir.
            faltantes = [
                nome for nome, valor in (
                    ("PII_ENCRYPTION_KEY", self.PII_ENCRYPTION_KEY),
                    ("PII_HASH_KEY", self.PII_HASH_KEY),
                )
                if not valor or valor.startswith("TROCAR")
            ]
            if faltantes:
                raise ValueError(
                    f"{' e '.join(faltantes)} ausente(s) ou placeholder em "
                    "produção. Gere PII_ENCRYPTION_KEY com \"python3 -c 'from "
                    "cryptography.fernet import Fernet; print(Fernet.generate_key()"
                    ".decode())'\" e PII_HASH_KEY com \"python3 -c 'import secrets; "
                    "print(secrets.token_urlsafe(32))'\", e defina no .env. "
                    "Nunca troque uma chave já em uso — descriptografaria dados "
                    "cifrados existentes."
                )
            # Valida o FORMATO da chave Fernet no boot. Sem isto, uma chave não-
            # placeholder porém malformada (base64 inválido, whitespace colado,
            # tamanho errado) passa aqui e só estoura no primeiro encrypt() em
            # runtime (pii_crypto._fernet) — quebrando a promessa "falha no
            # deploy, não no primeiro cadastro". PII_HASH_KEY serve para HMAC com
            # qualquer bytes, então não tem formato a validar.
            from cryptography.fernet import Fernet
            try:
                Fernet(self.PII_ENCRYPTION_KEY.encode())
            except Exception as e:
                raise ValueError(
                    "PII_ENCRYPTION_KEY inválida: precisa ser uma chave Fernet "
                    "(32 bytes url-safe base64). Gere com \"python3 -c 'from "
                    "cryptography.fernet import Fernet; print(Fernet.generate_key()"
                    ".decode())'\"."
                ) from e
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
