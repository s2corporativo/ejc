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
    # 2h (era 8h — hardening pós-auditoria de 2026-07-12): janela de exposição
    # menor para um access token vazado/pós-revogação. Não incomoda o usuário:
    # o frontend renova automaticamente via interceptor 401 + POST /auth/refresh
    # (rotação de refresh token, sessão de até REFRESH_TOKEN_EXPIRE_DAYS). O
    # Portal do Cliente usa o MESMO fluxo (get_current_user + refresh) — nenhum
    # fluxo longo depende do access token sobreviver além de 2h. Override por
    # env var ACCESS_TOKEN_EXPIRE_HOURS (ver .env.example).
    ACCESS_TOKEN_EXPIRE_HOURS: int = 2
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 2FA (TOTP) — enforcement organizacional por papel ─────────────────
    # CSV de papéis (UserRole: superadmin, admin, socio, advogado,
    # advogado_auxiliar, financeiro, estagiario, secretaria, cliente_externo)
    # que DEVEM usar 2FA (TOTP). Default inclui a GESTÃO e os ADVOGADOS
    # (superadmin,admin,socio,advogado,advogado_auxiliar): quem pratica atos
    # jurídicos e acessa dados sensíveis de casos/clientes é obrigado a 2FA.
    # Enforcement SEM lockout (ver abaixo) — endurecer o default não tranca
    # ninguém; só passa a orientar a configuração e a impedir a auto-desproteção.
    # Quando um papel está listado (comparação case-insensitive):
    #   (a) /auth/login sinaliza `precisa_configurar_2fa=true` no payload
    #       enquanto o usuário desse papel ainda não tiver TOTP ativo — para o
    #       frontend orientar a configuração. NÃO bloqueia o login (enforcement
    #       SEM lockout: não há coluna/migration nova e não se tranca ninguém);
    #   (b) POST /auth/totp/desativar RECUSA (403) desativar o 2FA de um usuário
    #       cujo papel é obrigado — ele não pode se auto-desproteger.
    # Override por ambiente (definir no .env, NÃO versionado), ex. só gestão:
    #   REQUIRE_2FA_ROLES=superadmin,admin,socio
    REQUIRE_2FA_ROLES: str = "superadmin,admin,socio,advogado,advogado_auxiliar"
    TWO_FACTOR_SETUP_TOKEN_EXPIRE_MINUTES: int = 15

    @property
    def require_2fa_roles_list(self) -> List[str]:
        return [r.strip().lower() for r in self.REQUIRE_2FA_ROLES.split(",") if r.strip()]

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

    # ── Cofre de Credenciais (integration_credentials, migration 108) ──────
    # CSV de chaves Fernet mestras do cofre — a PRIMEIRA cifra (primária),
    # TODAS decifram (MultiFernet). Rotação de mestra = prepend da chave nova
    # na frente + re-encrypt em background (services/vault_crypto.rotacionar).
    # EXCLUSIVA do cofre: não reusar PII_ENCRYPTION_KEY/BACKUP_ENCRYPTION_KEY
    # (rotacionar uma não pode invalidar a outra) e JAMAIS derivar de
    # SECRET_KEY (trocar o SECRET_KEY desloga usuários; não pode, além disso,
    # inutilizar credenciais cifradas). Default vazio de propósito — mesmo
    # padrão do PII_ENCRYPTION_KEY: obrigatória em produção (validada
    # abaixo), efêmera em desenvolvimento.
    VAULT_MASTER_KEYS: str = ""

    @property
    def vault_master_keys_list(self) -> List[str]:
        """Chaves do cofre na ordem do CSV (primeira = primária)."""
        return [k.strip() for k in self.VAULT_MASTER_KEYS.split(",") if k.strip()]

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
    # AI-043 (auditoria 2026-07-26): llama-3.3-70b-versatile foi DEPRECIADO pela
    # Groq (anúncio 17/06/2026; deixa de ser servido em ago/2026 nos tiers
    # free/dev). Migrado ao substituto oficial recomendado (gpt-oss-120b).
    # Groq é o ÚLTIMO fallback da cadeia (opt-in); rodar regressão jurídica
    # (eval/run_eval.py) antes de promovê-lo a caminho primário em qualquer área.
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TIMEOUT: int = 60               # segundos
    # Transcrição de áudio/vídeo é uma operação EXTERNA distinta do chat:
    # nasce desligada, exige confirmação por requisição e respeita o
    # kill-switch AI_EXTERNAL_PROVIDERS_ALLOWED.
    AUDIO_TRANSCRIPTION_ENABLED: bool = False
    AUDIO_TRANSCRIPTION_MAX_MB: int = 25
    AUDIO_TRANSCRIPTION_TIMEOUT: int = 180
    # Gates organizacionais: só marcar True após habilitar Zero Data Retention
    # na conta Groq e documentar DPA/transferência internacional com o DPO.
    GROQ_ZDR_VERIFIED: bool = False
    AUDIO_TRANSCRIPTION_DPA_APPROVED: bool = False
    GROQ_TRANSCRIPTION_MODEL: str = "whisper-large-v3"
    AI_ENABLED: bool = True

    # Documento grande: leitura em blocos + síntese, sem truncamento silencioso.
    # O teto é propositalmente explícito para respeitar TPM/contexto do provedor.
    AI_LONG_DOCUMENT_MAX_CHARS: int = 120_000
    AI_LONG_DOCUMENT_CHUNK_CHARS: int = 16_000
    AI_LONG_DOCUMENT_MAX_CHUNKS: int = 12

    # ── Ficha de Triagem pré-peça (gate de qualidade) ────────────────────
    # True = POST /pecas/gerar com case_id EXIGE ficha de triagem CONFIRMADA
    # para o caso (evita "bom modelo no caso errado"). Geração AVULSA (sem
    # case_id) nunca é gateada. Desligar só com aval do responsável do fluxo.
    FICHA_TRIAGEM_OBRIGATORIA: bool = True

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
    # Prompt caching Anthropic: envia o bloco system com
    # cache_control={"type": "ephemeral"} (leituras repetidas do mesmo prefixo
    # custam ~10%). True = comportamento atual; False = system como string pura
    # (sem cache_control). Não afeta os demais providers.
    AI_PROMPT_CACHING_ENABLED: bool = True
    # Busca web (verificação ativa) via server-side tool do Anthropic.
    # Padrão de integrações externas do repo: default OFF + degradação graciosa
    # (se a API rejeitar o tool, a chamada repete sem ele). O tool só é anexado
    # no caminho que JÁ passou pela pseudonimização/sanitização do gateway.
    AI_WEB_SEARCH_ENABLED: bool = False
    # Máximo de buscas por chamada (max_uses do tool web_search).
    AI_WEB_SEARCH_MAX_USES: int = 3
    # Preço da busca web Anthropic (server tool web_search), cobrado À PARTE dos
    # tokens: US$ 10,00 por 1.000 buscas (tabela oficial Anthropic). Entra no
    # custo estimado (AILog/governança/alerta de budget) via ai_cost.
    AI_WEB_SEARCH_CUSTO_USD_POR_1000: float = 10.0

    # ── IA — Maritaca (Sabiá) — provider BRASILEIRO, OpenAI-compatible ─────
    # PLUGÁVEL: nasce DESLIGADO (MARITACA_ENABLED=false) → sistema idêntico ao
    # atual. Provider EXTERNO ao VPS → passa pela MESMA barreira LGPD
    # (pseudonimização). Chave definida APENAS no .env (nunca aqui).
    # Soberania de dados NÃO é o default e NÃO é automática: depende de DUAS
    # coisas juntas — (1) configurar MARITACA_MODEL/MARITACA_MODEL_RAPIDO nas
    # variantes "-br-sp" (ex.: "sabia-4-br-sp", "sabiazinho-4-br-sp"), que
    # processam 100% em território nacional (+30% de custo); e (2) ligar o guarda
    # MARITACA_EXIGIR_SOBERANIA=true, que passa a EXIGIR essas variantes no boot.
    # Os defaults abaixo ("sabia-4"/"sabiazinho-4") NÃO são soberanos.
    MARITACA_ENABLED: bool = False
    MARITACA_API_KEY: str = ""
    MARITACA_BASE_URL: str = "https://chat.maritaca.ai/api"
    MARITACA_MODEL: str = "sabia-4"            # qualidade/generalista (128k)
    MARITACA_MODEL_RAPIDO: str = "sabiazinho-4"  # rápido/barato
    MARITACA_TIMEOUT: int = 90
    # Guarda de soberania (opt-in, default OFF → comportamento atual inalterado).
    # True + MARITACA_ENABLED=true → o boot EXIGE que MARITACA_MODEL e
    # MARITACA_MODEL_RAPIDO terminem em "-br-sp" (processamento em território
    # nacional); caso contrário FALHA o boot. Espelha os gates conscientes
    # GROQ_ZDR_VERIFIED/AUDIO_TRANSCRIPTION_DPA_APPROVED.
    MARITACA_EXIGIR_SOBERANIA: bool = False

    # ── IA — Núcleo Único (policy central de provedores) ──────────────────
    # False = só Ollama local (soberania total): nenhum dado sai do VPS,
    # mesmo sanitizado. Anthropic/Groq ficam inelegíveis na cadeia.
    AI_EXTERNAL_PROVIDERS_ALLOWED: bool = True
    # True = todo conteúdo destinado a provider EXTERNO (Anthropic/Groq) passa
    # por sanitizar_pii + validar_sem_pii; PII residual bloqueia o envio (LGPD).
    # NUNCA desligar em produção sem parecer do encarregado de dados.
    AI_REQUIRE_SANITIZATION_FOR_EXTERNAL: bool = True
    # Exceção CONSCIENTE e AUDITÁVEL ao guarda de boot: em produção, se algum
    # provider externo for elegível E AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=false,
    # o boot FALHA — a menos que esta flag seja explicitamente True (parecer do
    # encarregado de dados registrado). Default False = comportamento seguro;
    # espelha GROQ_ZDR_VERIFIED/AUDIO_TRANSCRIPTION_DPA_APPROVED.
    AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION: bool = False
    # True = toda saída de IA é rascunho com revisão humana obrigatória (OAB).
    AI_REQUIRE_HITL: bool = True
    # Sala Jurídica: extração automática do estado jurídico consolidado após
    # cada resposta (roda no provider LOCAL via task_type "resumo" — custo
    # zero; falha degrada para o merge de fontes, nunca bloqueia a resposta).
    SALA_JURIDICA_AUTO_ESTADO: bool = True
    # Gate anti-alucinação de citações (Fase 4 — citation_gate.py):
    #   "bloquear"  → saída de IA com citação bloqueante (suspeita de alucinação,
    #                 menção genérica ou julgado sem tribunal+data) NÃO pode ser
    #                 aprovada no HITL sem override JUSTIFICADO e AUDITADO do
    #                 revisor (default — advogados já foram punidos por citar
    #                 acórdão falso; apenas SINALIZAR não basta, tem de barrar);
    #   "marcar"    → relatório de citações apenas anexado/exposto ao revisor,
    #                 SEM impedir a aprovação (modo permissivo/legado);
    #   "desligado" → verificação de citações não roda nos fluxos de IA.
    # Valor inválido/typo cai no modo SEGURO "bloquear" (ver politica_citacoes()):
    # um erro de config não pode rebaixar silenciosamente o gate antialucinação.
    CITACOES_POLITICA: str = "bloquear"
    # Modo ESTRITO do gate (opt-in, default OFF). Com False (atual), uma súmula
    # ou artigo CITADO mas AUSENTE da base curada fica só "identificada" (não
    # bloqueia) — o gate barra erro estrutural, não invenção plausível. Com True,
    # súmula/artigo citado e NÃO encontrado na base vira BLOQUEANTE (trata a
    # ausência como suspeita). Ligue SÓ quando a base de conhecimento estiver
    # abrangente (senão gera falso-positivo em citação real ainda não ingerida).
    CITACOES_MODO_ESTRITO: bool = False
    # ── Modo Duas IAs (Fase 5 — validação adversarial) ────────────────────
    # True = peças de alta complexidade geradas pelo Núcleo de IA recebem uma
    # SEGUNDA passada por uma IA Crítica/Adversarial (advogado da parte
    # contrária + magistrado), preferindo provider DIFERENTE do que gerou a
    # peça (diversidade reduz erro correlacionado). Ligado por padrão (decisão
    # de produto: qualidade padrão-ouro nas peças justifica o custo extra; para
    # reduzir custo, desligar via .env). A crítica NUNCA bloqueia a entrega:
    # falhou → anexa aviso "crítica indisponível" e o revisor HITL segue.
    DUAS_IAS_ENABLED: bool = True
    # CSV de task_types do ai_gateway que disparam a crítica automática
    # (vocabulário de TASK_ROUTING; aliases como "redacao_peca" são
    # normalizados antes da comparação).
    DUAS_IAS_TASK_TYPES: str = "elaboracao_peca,auditoria_peca"
    # Ordem de preferência entre provedores ELEGÍVEIS (csv). A policy ainda
    # filtra por habilitação/chave e prioriza Anthropic em tarefas complexas.
    # Maritaca antes do groq: para tarefa jurídica PT-BR o Sabiá rankeia acima
    # de um generalista; só entra na cadeia se elegível (ENABLED + chave).
    AI_PROVIDER_PRIORITY: str = "ollama,anthropic,maritaca,groq"
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
    # Ligado por padrão: o model_router (heurística DETERMINÍSTICA, sem IA)
    # propõe o provedor de PARTIDA da cadeia por complexidade estimada do
    # input — tarefas pesadas partem do Anthropic, leves do provedor barato.
    # O gateway AINDA aplica elegibilidade/kill-switch/barreira PII e o
    # fallback continua. False via .env = comportamento por task_type intacto.
    ROTEAMENTO_INTELIGENTE_ENABLED: bool = True
    # Provedor preferido por TIER de complexidade (o roteador só PROPÕE; se
    # inelegível, o gateway ignora e usa a cadeia normal por prioridade).
    ROTEAMENTO_PROVIDER_LEVE: str = "groq"       # rápido/barato p/ tarefas leves
    # médio = anthropic: o stack de produção não sobe ollama (compose:
    # OLLAMA_ENABLED=false) — apontar o tier médio para provider morto só gerava
    # tentativa-e-fallback a cada tarefa. O MODELO do tier médio é COMPLEXO
    # (Opus), NÃO Haiku — ver model_router._model_do_provider (anti-rebaixamento
    # P1: só o tier LEVE usa o modelo rápido).
    ROTEAMENTO_PROVIDER_MEDIO: str = "anthropic"
    ROTEAMENTO_PROVIDER_PESADO: str = "anthropic"  # modelo forte p/ raciocínio
    # Limiares (score inteiro) que separam os tiers leve|medio|pesado.
    ROTEAMENTO_LIMIAR_MEDIO: int = 3
    ROTEAMENTO_LIMIAR_PESADO: int = 6

    # ── MÓDULO AGÊNTICO DE IA (loop de tool-use, igual ao Claude Code) ────
    # DESATIVADO por default (auditoria máxima 2026-07-26, achado AI-033/AI-034):
    # o agente com write-tools (nota, prazo fatal, kit documental) só deve ser
    # habilitado por decisão EXPLÍCITA do ambiente (AI_AGENT_ENABLED=true no
    # .env), após homologação do HITL. Isso também alinha o default ao que o
    # router (ia_agente.py) sempre documentou. A IA opera como agente (decide →
    # chama ferramenta → lê resultado → decide), reusando o núcleo e TODOS os
    # guardrails (barreira LGPD, RBAC, AILog, gate de citações, HITL).
    AI_AGENT_ENABLED: bool = False
    # Teto de PASSOS do loop (nunca infinito).
    AI_AGENT_MAX_STEPS: int = 8
    # Teto de TOKENS acumulados (input+output de TODOS os turnos) por execução do
    # agente. O budget conta o input de CADA turno — que cresce a cada passo,
    # pois o histórico inteiro é reenviado — somado ao output. Um teto baixo
    # (16000 antigo) matava o agente no passo 2-3 antes de esgotar max_steps
    # (achado M3). Elevado para comportar AI_AGENT_MAX_STEPS turnos com folga
    # (piso real de saída por turno × passos + input acumulado). Ajuste fino via
    # .env; o teto DURO por chamada continua em ANTHROPIC_MAX_TOKENS.
    AI_AGENT_MAX_TOKENS: int = 120000
    # Teto de CUSTO (R$) por execução do agente (Sugestão 2). Acumula o custo
    # estimado de cada turno (ai_cost.estimar_custo_brl); ao exceder, o loop
    # encerra com aviso (igual ao teto de tokens). Default conservador.
    AI_AGENT_MAX_CUSTO_BRL: float = 2.00
    # TTL (segundos) do estado retomável de HITL no Redis (achado H1). O estado
    # contém a transcrição em ESPAÇO REAL (PII) — fica no VPS (Redis interno),
    # com TTL curto e NUNCA é logado. Curto para minimizar a janela de retenção.
    AI_AGENT_HITL_TTL_SEGUNDOS: int = 900

    # ── Calculadoras jurídicas — exportação de demonstrativo ──────────────
    # DESLIGADO por default (auditoria 2026-07-26, AI-107/AI-113): as regras das
    # calculadoras ainda não são homologadas (fonte/vigência/revisor); o
    # demonstrativo dá aparência documental a uma regra possivelmente errada.
    # Religar por ambiente SOMENTE após homologação formal das regras.
    PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED: bool = False

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
    # WhatsApp: o vendor Z-API foi REMOVIDO. Não há mais remetente automático de
    # WhatsApp (o canal fica efetivamente off — ver notification_service.
    # enviar_whatsapp). A Evolution API (webhook de ENTRADA) permanece em
    # routers/evolution_webhook.py, controlada por EVOLUTION_* próprias.
    WHATSAPP_ENABLED: bool = False

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587  # TLS (não usar 465/SSL)
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_ENABLED: bool = False

    # ── URLs ──────────────────────────────────────────────────────────────
    # URL pública do frontend — usada nos links dos e-mails
    FRONTEND_URL: str = "https://SEU_DOMINIO"

    # ── DataJud/CNJ (consulta processual — API Pública) ──────────────────
    # Integração EXTERNA é opt-in: desligada por padrão (ligar no .env).
    DATAJUD_ENABLED: bool = False
    # O CNJ divulga uma chave PÚBLICA de uso geral na wiki oficial
    # (https://datajud-wiki.cnj.jus.br/api-publica/acesso/) — copie-a para o
    # .env. Nunca commitar a chave nem registrá-la em logs/erros.
    DATAJUD_API_KEY: str = ""
    # Host oficial da API Pública (POST /{alias_tribunal}/_search).
    DATAJUD_BASE_URL: str = "https://api-publica.datajud.cnj.jus.br"
    # Timeout por requisição. O CNJ pode responder lentamente em horários de pico.
    DATAJUD_TIMEOUT_SECONDS: float = 25.0
    # Cache TTL (segundos) da consulta processual por número CNJ — evita bater
    # no CNJ a cada request repetida. Em memória (premissa de worker único).
    # 0 desliga o cache. Erro do CNJ nunca entra no cache.
    DATAJUD_CACHE_TTL_SEGUNDOS: int = 900

    # ── Infosimples — consultas PAGAS a sites públicos (TJMG, Receita…) ──
    # Agregador comercial (https://infosimples.com/consultas/): cada consulta
    # EXECUTADA é cobrada. Integração opt-in, desligada por padrão, com teto
    # diário de custo e cache do mesmo dia (ver services/infosimples_service).
    INFOSIMPLES_ENABLED: bool = False
    # Token da conta contratada — vai só no corpo da requisição; NUNCA em
    # logs, mensagens de erro ou payloads de resposta.
    INFOSIMPLES_TOKEN: str = ""
    # Timeout repassado à Infosimples (segundos) — as consultas raspam sites
    # públicos e podem demorar; o cliente HTTP usa este valor + margem.
    INFOSIMPLES_TIMEOUT: int = 300
    # TETO DE CUSTO: máximo de consultas EXECUTADAS (cobradas) por dia UTC.
    # Atingido o teto, o serviço recusa novas consultas (429) até o dia virar.
    INFOSIMPLES_MAX_CONSULTAS_DIA: int = 50
    # Base oficial (POST {base}/{caminho} form-urlencoded). Só mude p/ testes.
    INFOSIMPLES_BASE_URL: str = "https://api.infosimples.com/api/v2/consultas"

    # ── CGU Portal da Transparência — sanções (CEIS/CNEP/CEPIM) — GATED ──
    # API pública de dados do governo federal (chave GRÁTIS, cadastro no portal).
    # Só CONSULTA (GET); cache diário por (base, cnpj) com purga LGPD. Opt-in,
    # desligada por padrão. Ver services/transparencia_service.
    TRANSPARENCIA_ENABLED: bool = False
    # Chave de acesso (header `chave-api-dados`) — NUNCA em logs/erros/retornos.
    TRANSPARENCIA_API_KEY: str = ""
    # Host oficial (default fixo anti-SSRF; a URL nunca vem de input do usuário).
    TRANSPARENCIA_BASE_URL: str = "https://api.portaldatransparencia.gov.br/api-de-dados"

    # PNCP removido — licitações desativadas no EJC

    # ── NFS-e — emissão fiscal via provedor (Nuvem Fiscal) — GATED ──────
    # Nasce DESLIGADO e em HOMOLOGAÇÃO: nunca emite nota real sem ativação
    # explícita do dono. A emissão REAL ainda exige (fora do EJC): certificado
    # digital A1 no painel do provedor + confirmação das definições fiscais
    # (alíquota ISS de advocacia em Betim, item LC116, cTribNac) com o contador.
    # Ver docs/NFSE_VIABILIDADE.md.
    NFSE_ENABLED: bool = False
    NFSE_MODO: str = "homologacao"       # homologacao | producao
    NFSE_PROVEDOR: str = "nuvemfiscal"   # só "nuvemfiscal" por ora
    NFSE_NUVEMFISCAL_BASE_URL: str = "https://api.nuvemfiscal.com.br"
    NFSE_NUVEMFISCAL_AUTH_URL: str = "https://auth.nuvemfiscal.com.br"
    # Credenciais OAuth2 do provedor — só no .env da VPS; nunca em log/resposta.
    NFSE_NUVEMFISCAL_CLIENT_ID: str = ""
    NFSE_NUVEMFISCAL_CLIENT_SECRET: str = ""
    # CNPJ do escritório emitente (com ou sem máscara).
    NFSE_EMITENTE_CNPJ: str = ""
    # Município do emitente (código IBGE, 7 díg). Betim/MG = 3106200.
    NFSE_EMITENTE_MUN_IBGE: str = "3106200"
    # Definições fiscais — CONFIRMAR COM O CONTADOR antes de produção.
    NFSE_ISS_ALIQUOTA: float = 0.0       # alíquota ISS advocacia em Betim (%). A confirmar.
    NFSE_ITEM_LC116: str = "17.14"       # item da lista LC 116/03 (advocacia)
    NFSE_CTRIB_NAC: str = ""             # cTribNac (GET /nfse/cidades/3106200). A confirmar.
    NFSE_TIMEOUT: int = 60               # timeout (s) das chamadas ao provedor

    # ── DJEN / API Comunica CNJ (Res. CNJ 569/2024) — ingestão RAG ───────
    # Ingestor diário de comunicações processuais (intimações/publicações)
    # por OAB monitorada. A retenção da API é limitada — o RAG do EJC é o
    # arquivo histórico permanente. LIGADO por decisão do titular (fonte pública
    # CNJ, sem autenticação); desligue com DJEN_INGEST_ENABLED=false.
    DJEN_INGEST_ENABLED: bool = True
    # CSV "numero/UF" — ex.: "12345/MG,67890/MG". Vazio = ingestor no-op.
    # Default = OAB do sócio João Pedro Rodrigues Teixeira (OAB/MG 251.174);
    # acrescente as OABs dos demais advogados separadas por vírgula.
    DJEN_OABS_MONITORADAS: str = "251174/MG"
    # Janela incremental (dias para trás) de cada coleta diária. 2 dias dá
    # margem para atraso de disponibilização sem reprocessar demais (o upsert
    # é idempotente por chave_origem, então sobreposição é inofensiva).
    DJEN_INGEST_JANELA_DIAS: int = 2

    # ── TJMG — jurisprudência estadual MG (crawler agendado → RAG) ───────
    # O TJMG NÃO tem API aberta (≠ STJ CKAN): a jurisprudência fica atrás de
    # um formulário HTML. O ingestor varre a base de acórdãos por uma lista
    # curada de temas do escritório, em janela de datas, e ingere as ementas
    # no RAG (dedup idempotente por chave_origem). Scraping é frágil por
    # natureza — se o HTML mudar ou o TJMG bloquear, o job marca 'erro' em
    # fontes_ingestao SEM derrubar o scheduler. LIGADO por decisão do titular; o
    # scraper é frágil — acompanhe /ia-governanca/fontes (se marcar 'erro', o
    # LexML federado já cobre o TJMG). Desligue com TJMG_INGEST_ENABLED=false.
    TJMG_INGEST_ENABLED: bool = True
    # CSV de temas de busca. Vazio = usa a lista padrão (áreas do escritório,
    # ver services/ingestors/tjmg.py::TEMAS_PADRAO).
    TJMG_INGEST_TEMAS: str = ""
    # Janela (dias para trás) da coleta, aplicada como filtro de data de
    # julgamento no formulário. 0 = sem filtro (o TJMG decide a ordenação).
    # Sobreposição entre execuções é inofensiva (upsert idempotente).
    TJMG_INGEST_JANELA_DIAS: int = 30
    # Teto de acórdãos por tema/execução (controle de volume e de carga no
    # portal do TJMG — evita varredura abusiva).
    TJMG_INGEST_MAX_POR_TEMA: int = 50

    # ── Ingestão contínua de conhecimento (ANPD + Normas RFB → RAG) ──────
    # Job SEMANAL (domingo 03h00 UTC) que raspa fontes oficiais e alimenta a
    # base de conhecimento: regulamentações/guias da ANPD (LGPD) e atos
    # tributários do sijut2consulta da RFB. Idempotente por chave_origem
    # (anpd:<slug> / rfb:<tipo>:<numero>:<ano>) — reexecução não duplica.
    # Default True (ligado — autorização do dono; fontes públicas sem custo).
    # Disparo manual: POST /rag/ingest-fontes-oficiais (socio+).
    CONHECIMENTO_INGEST_ENABLED: bool = True
    # CSV de termos de busca do sijut2consulta (Normas RFB). Vazio = lista
    # padrão do ramo tributário (services/conhecimento_ingest/normas_rfb.py::
    # TERMOS_PADRAO — Solução de Consulta ISS, IRPF, Simples Nacional...).
    NORMAS_RFB_TERMOS: str = ""

    # ── LexML — federador oficial (legislação + jurisprudência) → RAG ────
    # O LexML.gov.br (Rede de Informação Legislativa e Jurídica, mantida pelo
    # Senado) federa NUMA ÚNICA FONTE: legislação federal/ESTADUAL (ALMG)/
    # MUNICIPAL (Betim) e jurisprudência de TJ/TRT/TRF/TST/STJ/STF. O ingestor
    # (services/ingestors/lexml.py) varre um catálogo de temas/autoridades do
    # escritório e usa o caminho PROVADO jurisprudencia_externa.buscar_lexml
    # (API pública, keyword-based) para tipo='legislacao' E 'jurisprudencia'.
    # É o veículo que amplia o VOLUME estadual/municipal/tribunais sem scraper
    # dedicado por portal. LIGADO por decisão do titular (fonte pública gratuita,
    # inbound de dado público, degrada graciosamente); best-effort e idempotente
    # por chave_origem (lexml:<tipo>:<urn|hash>) como os demais. Requer
    # ENABLE_SCHEDULER=true no worker. Desligue com LEXML_INGEST_ENABLED=false.
    LEXML_INGEST_ENABLED: bool = True
    # CSV de temas/autoridades de busca. Vazio = lista padrão (áreas do
    # escritório + autoridades-alvo, ver services/ingestors/lexml.py::TEMAS_PADRAO).
    LEXML_INGEST_TEMAS: str = ""
    # Teto de itens por tema/tipo/execução (controle de volume e de carga na
    # API pública do LexML). Sobreposição entre execuções é inofensiva (upsert
    # idempotente por chave_origem).
    LEXML_INGEST_MAX_POR_TEMA: int = 20

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
    # Modelo e dimensão do embedding. O default precisa constar em
    # TextEmbedding.list_supported_models() da versão PINADA do fastembed;
    # caso contrário a migration de dimensão deixa o RAG sem vetores e sem
    # possibilidade de reconstrução. multilingual-e5-large é 1024d,
    # multilíngue e suportado nativamente pelo fastembed 0.8.0.
    # A coluna knowledge_chunks.embedding é
    # vector(EMBEDDINGS_DIM); TROCAR A DIMENSÃO exige a migration 096 + REINDEX
    # (scripts.reembedar_chunks_orfaos). Revertível por env (voltar a
    # sentence-transformers/paraphrase-multilingual-mpnet-base-v2 + 768 exige a
    # migration de downgrade + reindex). ⚠️ EMBEDDINGS_DIM DEVE casar com a coluna.
    EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-large"
    EMBEDDINGS_DIM: int = 1024
    # Auto-reindex do RAG (O-2): job periódico do scheduler reembeda chunks órfãos
    # (embedding IS NULL) — assim a troca de modelo/dimensão (migration 096) se
    # AUTO-CURA sem passo manual no deploy. No-op rápido quando não há órfãos.
    # O script manual (scripts.reembedar_chunks_orfaos) segue como fallback.
    RAG_AUTO_REEMBED_ENABLED: bool = True
    RAG_AUTO_REEMBED_BATCH: int = 20

    # ── Reranking (cross-encoder) do RAG — Fase 1 auditoria IA 2026-07-17 ─
    # Reordena os candidatos do retrieval híbrido (pgvector cosine + RRF pg_trgm)
    # por relevância consulta↔trecho com um cross-encoder LOCAL (fastembed, sem
    # torch; não sai do VPS). Recupera um POOL maior (RAG_RERANK_POOL_*) e devolve
    # só os melhores após rerank — maior ganho de precisão de contexto do RAG.
    # Fail-safe (ver reranker.py): fastembed/modelo ausente ou qualquer erro →
    # mantém a ordem RRF, sem exceção. O único cross-encoder multilíngue listado
    # pelo fastembed pinado tem licença CC-BY-NC-4.0, incompatível com uso
    # empresarial. Por isso o rerank fica DESLIGADO por padrão até existir um
    # modelo multilíngue com licença comercialmente compatível e eval em pt-BR.
    # BAAI/bge-reranker-base permanece como opção técnica suportada (MIT), mas
    # não deve ser ativado sem medir qualidade no corpus jurídico em português.
    RAG_RERANK_ENABLED: bool = False
    RAG_RERANK_MODEL: str = "BAAI/bge-reranker-base"
    RAG_RERANK_POOL_MULT: int = 5     # pool de candidatos = limite × MULT
    RAG_RERANK_POOL_MIN: int = 20     # piso de candidatos antes do rerank

    # ── Ajuste fino do retrieval RAG (auditoria IA 2026-07-17) ───────────────
    # Limiar de similaridade de cosseno da busca vetorial (pgvector): chunks com
    # similaridade < RAG_MIN_SIM são descartados (dist > 1-RAG_MIN_SIM). Antes era
    # hardcoded (0.55); agora é calibrável por um eval set sem tocar código.
    RAG_MIN_SIM: float = 0.55
    # HyDE (Hypothetical Document Embeddings): gera uma "resposta hipotética"
    # curta e barata e a EMBUTE na busca vetorial — melhora o recall quando o
    # vocabulário do caso novo difere do registrado. Fail-safe: erro/timeout →
    # usa a consulta original. Default OFF (liga após medir; +1 chamada barata/busca).
    RAG_HYDE_ENABLED: bool = False
    # Perna lexical FULL-TEXT (tsvector 'portuguese', BM25-like) no híbrido RRF,
    # além do pg_trgm — melhor para termos raros/citações exatas (art./súmula/nº
    # CNJ). Usa o índice GIN pré-existente ix_knowledge_chunks_conteudo_fts
    # (migration 001) — não requer migration nova. Fail-safe: erro → só
    # semântico+trigram. Default OFF até validar em produção.
    RAG_FTS_ENABLED: bool = False
    # Grounding de citações (auditoria IA 2026-07-17, O-5): além do citation_check
    # contra a base interna, o validador confere as citações com o verificador
    # rigoroso. As checagens são LOCAIS (dígito verificador do nº CNJ, faixa de
    # súmula, formato → detecta citação alucinada) e não fazem rede — por isso o
    # grounding vem LIGADO por default (valor imediato, zero latência). Aditivo e
    # fail-safe (erro → alerta, nunca derruba).
    AI_LIVE_GROUNDING_ENABLED: bool = True
    # Confirmação de nº CNJ no DataJud (CNJ) — a ÚNICA parte que faz REDE externa
    # (latência/rate limit). Separada e OFF por default: ligue após validar a
    # conectividade DataJud no ambiente. O grounding local acima independe disto.
    AI_GROUNDING_DATAJUD_ENABLED: bool = False

    # ── RAG de MODELOS na geração de peças (Bíblia de Conhecimento) ───────
    # Recupera os modelos de peça (categoria "modelo_documento_juridico") como
    # REFERÊNCIA de estrutura/tese na montagem final (Etapa 7). Gated e fail-safe:
    # OFF ou qualquer falha/vazio degrada para o comportamento atual (peça gerada
    # sem modelos), NUNCA propaga erro. Query dedicada com filtro por categoria
    # para os modelos não serem afogados por legislação/jurisprudência no top-k.
    PECAS_RAG_MODELOS_ENABLED: bool = True
    PECAS_RAG_MODELOS_TOPK: int = 3

    # ── Laço de AUTO-CRÍTICA na geração de peças (P2 — auditoria IA) ──────
    # True = após a redação final do pipeline de peças (Etapa 7), a IA
    # Crítica/Adversarial (Modo Duas IAs) avalia a minuta e, havendo
    # apontamentos ACIONÁVEIS, UMA rodada extra de revisão devolve a crítica
    # ao modelo redator (task_type="elaboracao_peca", base anti-alucinação;
    # a crítica entra DELIMITADA como DADO — nunca instrução de sistema).
    # A versão revisada também passa pelo gate de citações e permanece
    # rascunho HITL. Opt-in e fail-safe: default False = pipeline IDÊNTICO ao
    # atual; qualquer falha na crítica/revisão entrega a versão original.
    PECAS_AUTOCRITICA_ENABLED: bool = False

    # ── Pesquisa jurisprudencial DECOMPOSTA no pipeline de peças (FASE 3) ─
    # True = quando o caso tem Matriz de Teses montada (migração 102), a etapa
    # de jurisprudência do peca_service recebe ADICIONALMENTE o bloco
    # estruturado por questão (precedentes VERIFICADOS favoráveis/contrários,
    # ver matriz_teses_service.bloco_pesquisa_estruturada) em vez de só o blob
    # único do RAG. Aditivo e fail-safe: default False = pipeline BYTE-IDÊNTICO
    # ao atual; qualquer falha/matriz ausente degrada para o comportamento atual.
    PECAS_PESQUISA_QUESTOES_ENABLED: bool = False

    # ── Governança/curadoria na RECUPERAÇÃO RAG (gate fail-closed) ───────
    # Auditoria RAG: os campos de curadoria (confidence_level/rag_status) vivem
    # em knowledge_docs.extra (JSONB) mas NÃO eram usados no WHERE das buscas.
    # O gate exclui SEMPRE docs explicitamente bloqueados/recusados/pendentes
    # e, por padrão seguro, exige rag_status='aprovado' em TODA recuperação.
    # Acervo legado sem decisão de curadoria fica em quarentena até reconciliação;
    # disponibilidade nunca prevalece sobre fundamentação jurídica não validada.
    RAG_EXIGIR_APROVADO: bool = True
    # Quarentena das súmulas: mesmo após a reconstrução do seed (cada verbete
    # reconferido individualmente contra fonte oficial — ver DATA_CONFERENCIA
    # em sumulas_ingestion.py), este filtro continua ligado por padrão como
    # rede de segurança: só deixa passar doc de súmula com extra.conferido=true
    # (gravado pelo próprio seed corrigido). Protege contra reintrodução de
    # conteúdo não conferido por outra via (ingestão manual futura, por ex.).
    RAG_SUMULAS_QUARENTENA: bool = True
    # Situação JURÍDICA na recuperação (Issue #636). `rag_status` (curadoria) e
    # vigência da norma são campos DISTINTOS: um documento pode estar aprovado
    # para o RAG e, ao mesmo tempo, estar revogado ou com vigência nunca
    # conferida. A exclusão do que está REVOGADO é incondicional (não tem
    # flag). Esta flag governa o caso duvidoso: com true (default), documento de
    # LEGISLAÇÃO cuja vigência a fonte não declarou — o que
    # knowledge_governance.inferir_situacao_juridica classifica como
    # 'vigencia_nao_verificada' — também fica FORA da recuperação.
    # Default true porque o lado seguro é não servir como fundamentação atual
    # uma norma que ninguém conferiu; disponibilidade não prevalece sobre
    # fundamentação jurídica não validada (mesma escolha de RAG_EXIGIR_APROVADO
    # e RAG_SUMULAS_QUARENTENA). O filtro é recortado por categoria de
    # legislação: súmulas, jurisprudência, doutrina, modelos e peças internas
    # (para os quais a inferência devolve 'nao_aplicavel') seguem recuperáveis,
    # assim como as versões históricas (a inferência devolve 'historica').
    # `proposicao_legislativa` cai no recorte e não grava vigência: fica fora de
    # forma PERMANENTE e intencional — projeto em tramitação não é lei vigente.
    # Desligue (false) apenas como medida temporária, enquanto os ingestores não
    # tiverem propagado `extra.legal_status` para o acervo já existente.
    RAG_EXIGIR_VIGENCIA_VERIFICADA: bool = True
    # Ingestão do seed de súmulas (sumulas_ingestion.py) — RECONSTRUÍDO na
    # auditoria RAG: os 27 verbetes foram reconferidos individualmente contra
    # fonte oficial (STF/STJ/TST). Súmulas cancelada/suspensa são marcadas e
    # NÃO entram no RAG buscável (só ficam em `teses` como histórico). Padrão
    # True — desligue (False) só se precisar suspender a ingestão rapidamente
    # sem reverter código (o endpoint responde 423 quando False).
    RAG_SUMULAS_SEED_ENABLED: bool = True

    # ── Web Push (alertas no celular via PWA) ────────────────────────────
    # Gerar chaves: python scripts/gen_vapid.py (uma vez no deploy)
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = "mailto:admin@depaulateixeira.adv.br"
    PUSH_ENABLED: bool = False

    # ── Groq — modelo de contexto longo (fallback para dossiês grandes) ──
    # Usado quando prompt > 20 000 chars. AI-043: llama-3.3-70b-versatile foi
    # depreciado pela Groq (fim ago/2026) — migrado ao substituto oficial
    # recomendado, mesmo modelo do GROQ_MODEL (contexto 128k).
    GROQ_MODEL_LARGE: str = "openai/gpt-oss-120b"

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
    SENTRY_ENVIRONMENT: str = "production"   # tag de ambiente nos eventos
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0   # 0.0 = performance tracing off

    # ── Governança de custo de IA ─────────────────────────────────────────
    # Alerta de gasto no painel de Governança da IA: se o custo estimado de IA
    # no período exceder este valor (R$), o painel sinaliza. 0 = sem alerta.
    AI_BUDGET_ALERTA_BRL: float = 0.0

    # ── Backup ────────────────────────────────────────────────────────────
    # (a) Legado: pg_dump local + rclone (scheduler._backup_banco, 02h00).
    BACKUP_REMOTE: str = ""         # ex: "b2:ejc-backups" (rclone remote)
    BACKUP_DIR: str = "/app/backups"  # diretório local de dumps dentro do container postgres
    BACKUP_RETENTION_DAYS: int = 7  # dumps locais mais antigos que isto são apagados na rotação
    # (b) Backup diário cifrado → Google Drive (services/backup_service.py).
    # Prefere identidade exclusiva BACKUP_GOOGLE_DRIVE_* com escrita. O modo
    # herdado GOOGLE_DRIVE_* existe apenas para compatibilidade explícita.
    # Opt-in: default False mantém tudo desligado.
    BACKUP_ENABLED: bool = False
    # Chave Fernet EXCLUSIVA do backup (não reusar PII_ENCRYPTION_KEY — a
    # rotação de uma não pode invalidar a outra). Default vazio de propósito:
    # com BACKUP_ENABLED=true em produção a chave é OBRIGATÓRIA (validada
    # abaixo). AVISO: perder esta chave = perder TODOS os backups cifrados.
    BACKUP_ENCRYPTION_KEY: str = ""
    # ID da pasta do Google Drive que recebe os artefatos (a rotação só apaga
    # arquivos com prefixo ejc_backup_ dentro dela).
    BACKUP_DRIVE_FOLDER_ID: str = ""
    # Horário DIÁRIO do job, em UTC ("HH:MM"). 05:00 UTC = 02:00 BRT.
    BACKUP_HORA_UTC: str = "05:00"
    # Retenção no Drive: mantém N dias de backups diários; mais antigos são
    # apagados na rotação (somente arquivos com o prefixo do EJC).
    BACKUP_RETENCAO_DIAS: int = 14
    # Teto do tar.gz de uploads (a criptografia Fernet é em memória): acima
    # disto o backup segue SÓ com o banco e marca status "parcial".
    BACKUP_UPLOADS_MAX_MB: int = 512
    # Teto do dump do banco (mesma razão: Fernet cifra em memória): acima
    # disto o backup FALHA com erro claro (alerta dispara) sem ler o arquivo.
    BACKUP_DB_MAX_MB: int = 2048
    # Timeout (segundos) do pg_dump — bancos maiores podem precisar de mais.
    BACKUP_PG_DUMP_TIMEOUT: int = 600
    # Destino OFFSITE dos artefatos cifrados: "gdrive" (Google Drive, fluxo
    # original) ou "rclone" (qualquer remote rclone — ex.: OneDrive). O ciclo
    # local (pg_dump + tar + Fernet) é idêntico nos dois modos.
    BACKUP_DESTINO: str = "gdrive"
    # Remote rclone de destino quando BACKUP_DESTINO=rclone, no formato
    # "<remote>:<pasta>" (ex.: "onedrive:EJC-Backups"). Requer `rclone config`
    # feito na VPS e o binário rclone no PATH — ver runbook do backup.
    BACKUP_RCLONE_REMOTE: str = ""
    # Timeout (segundos) de CADA `rclone copyto` — links lentos podem exigir mais.
    BACKUP_RCLONE_TIMEOUT: int = 300
    # true = falha no envio OFFSITE derruba o backup inteiro (ok=False) e
    # bloqueia o deploy (fail-closed). false (default) = a prova LOCAL cifrada
    # sustenta o gate; offsite falho vira status "parcial" com aviso grave.
    BACKUP_OFFSITE_OBRIGATORIO: bool = False

    # ── Automações voltadas ao CLIENTE (jobs opt-in — default False) ──────
    # Sync diário DataJud + notificação de andamentos novos ao cliente
    # (services/datajud_sync_service.py). Exige DATAJUD_ENABLED + API key.
    DATAJUD_SYNC_ENABLED: bool = False
    # Horário DIÁRIO do sync, em UTC ("HH:MM") — mesmo padrão de BACKUP_HORA_UTC.
    # 09:30 UTC = 06:30 BRT (antes do expediente; DataJud atualiza de madrugada).
    DATAJUD_SYNC_HORA_UTC: str = "09:30"
    # Relatório semanal do dono (segunda-feira, e-mail aos sócios/admins) —
    # services/relatorio_dono_service.py.
    RELATORIO_DONO_ENABLED: bool = False
    # Régua de cobrança de honorários voltada ao CLIENTE (d-3/d+1/d+7/d+15 +
    # escalada interna) — services/cobranca_cliente_service.py. NÃO confundir
    # com a régua interna do advogado (scheduler._regua_cobranca).
    COBRANCA_ENABLED: bool = False
    # Expurgo LGPD de rascunhos abandonados da Entrada Única (Issue #647):
    # remove DocumentIntakeBatch (e Documents órfãos do lote) nunca convertidos
    # em caso (case_id IS NULL) após ENTRADA_EXPURGO_DIAS — services/
    # entrada_expurgo_service.py. Opt-in (hard delete é irreversível; decisão
    # do titular ligar em produção). Default False mantém tudo desligado.
    ENTRADA_EXPURGO_ENABLED: bool = False
    # Janela de retenção do rascunho não convertido, em dias (LGPD art. 15-16:
    # dado deixa de ser necessário à finalidade após esse prazo sem uso).
    ENTRADA_EXPURGO_DIAS: int = 30

    # ── Índices oficiais BCB (SGS + Olinda) — services/indices_service.py ─
    # API pública do Banco Central, gratuita e sem chave: correção monetária,
    # Taxa Legal (Lei 14.905/2024), Selic EC 113, taxas de juros por
    # instituição (revisional) e PTAX. LIGADO por padrão (autorizado pelo
    # dono — não há custo). Cache persistente em indices_bcb_cache.
    INDICES_BCB_ENABLED: bool = True
    # Timeout (segundos) das chamadas ao BCB (SGS e Olinda).
    INDICES_BCB_TIMEOUT: int = 20

    # ── Feriados nacionais via BrasilAPI — services/feriados_service.py ───
    # Sync automático (job semanal) dos feriados nacionais do ano corrente e
    # do próximo para a tabela `feriados` (merge aditivo: municipais/
    # estaduais cadastrados à mão nunca são alterados). Gratuito, sem chave —
    # ligado por padrão.
    FERIADOS_BRASILAPI_ENABLED: bool = True

    # ── Radar Legislativo (Câmara + Senado + ALMG) ────────────────────────
    # Job diário (07h00 UTC) que monitora proposições por termos derivados
    # dos ramos ativos do escritório e alimenta o Radar Regulatório
    # (services/radar_legislativo.py). APIs públicas gratuitas, sem chave —
    # LIGADO por padrão (autorizado pelo dono). Dedup persistente na tabela
    # radar_legislativo_visto (criada automaticamente — sem migration).
    RADAR_LEGISLATIVO_ENABLED: bool = True
    # Termos customizados por ramo (JSON): {"ramo": ["termo", ...]} —
    # SOBREPÕE os termos default do ramo; ramos extras são aditivos.
    # Ex.: {"tributario": ["CBS IBS", "split payment"], "agrario": ["MP solo"]}
    RADAR_LEGISLATIVO_TERMOS: str = ""

    # ── Scheduler ────────────────────────────────────────────────────────
    ENABLE_SCHEDULER: bool = True   # desligar em workers extras (uvicorn --workers)

    # ── Central Eletrônica de Diagnóstico (routers/diagnostico.py) ────────
    # Endpoint SOCIO+ que agrega a saúde de todos os subsistemas. Somente
    # leitura; sem integração externa nova. False → GET /diagnostico/central 503.
    DIAGNOSTICO_ENABLED: bool = True

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
    # FONTE ÚNICA DE VERDADE dos dados FIXOS do escritório, consumida por todos
    # os geradores de documento (documental.py, templates_documentos.py,
    # pdf_service.py, docx_service.py). OAB/ENDERECO trazem o DADO INSTITUCIONAL
    # do escritório como default (sobreponível pelo .env de cada instalação);
    # CEP nasce VAZIO de propósito.
    #
    # Campo vazio → os helpers devolvem STRING VAZIA e o consumidor DESCARTA o
    # segmento inteiro do timbre (rótulo incluído). O comportamento anterior
    # imprimia "[CEP - preencher em .env]" no papel timbrado da procuração e do
    # contrato — pendência interna vazando para o documento que o cliente assina
    # (Onda 1 da refatoração). A pendência não fica silenciosa: aparece em
    # `escritorio_pendencias()`, que o boot loga e o diagnóstico expõe.
    ESCRITORIO_NOME: str = "De Paula Teixeira Sociedade de Advogados"
    # CNPJ nasce VAZIO de propósito (mesmo padrão do CEP): a auditoria de
    # julho/2026 apontou que o CNPJ antes hardcoded aqui resolvia para OUTRA
    # razão social na Receita. Confirmar o CNPJ da sociedade na Receita e
    # preencher ESCRITORIO_CNPJ no .env; vazio, o segmento some do timbre e a
    # pendência aparece em escritorio_pendencias() (log de boot + diagnóstico).
    ESCRITORIO_CNPJ: str = ""
    ESCRITORIO_CIDADE: str = "Betim"
    ESCRITORIO_ESTADO: str = "MG"
    ESCRITORIO_EMAIL: str = "contato@depaulateixeira.adv.br"
    ESCRITORIO_OAB: str = "251174"   # só o número; o rótulo "OAB/MG " já é aposto pelos consumidores (timbre PDF/DOCX)
    ESCRITORIO_ENDERECO: str = "Av. Gov. Valadares nº 851, sala 405, Centro, Betim"
    ESCRITORIO_CEP: str = ""

    def escritorio_oab(self) -> str:
        return (self.ESCRITORIO_OAB or "").strip()

    def escritorio_endereco(self) -> str:
        return (self.ESCRITORIO_ENDERECO or "").strip()

    def escritorio_cep(self) -> str:
        return (self.ESCRITORIO_CEP or "").strip()

    def escritorio_cnpj(self) -> str:
        return (self.ESCRITORIO_CNPJ or "").strip()

    def escritorio_pendencias(self) -> list[str]:
        """Settings institucionais do timbre ainda não preenchidas no .env.

        É o substituto do placeholder no documento: a pendência continua
        VISÍVEL, mas para o operador (log de boot + Central de Diagnóstico), não
        para o cliente que recebe a peça.
        """
        return [
            nome
            for nome, valor in (
                ("ESCRITORIO_OAB", self.escritorio_oab()),
                ("ESCRITORIO_ENDERECO", self.escritorio_endereco()),
                ("ESCRITORIO_CEP", self.escritorio_cep()),
                # Auditoria jul/2026: confirmar CNPJ da sociedade na Receita e
                # preencher ESCRITORIO_CNPJ no .env (o antigo default resolvia
                # para outra razão social).
                ("ESCRITORIO_CNPJ", self.escritorio_cnpj()),
            )
            if not valor
        ]

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
            # Item 3 (auditoria pré-produção): chave curta = espaço de busca
            # brute-forçável para forjar JWTs (HS256). 32 chars é o piso.
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    f"SECRET_KEY muito curta para produção "
                    f"({len(self.SECRET_KEY)} caracteres; mínimo 32). Uma chave "
                    "curta permite forjar tokens JWT por força bruta. Gere uma "
                    "nova: python3 -c \"import secrets; "
                    "print(secrets.token_urlsafe(64))\" e defina no .env "
                    "(atenção: trocar a chave desloga todos os usuários)."
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
            # Backup → Google Drive: com o backup LIGADO em produção, a chave
            # de criptografia é OBRIGATÓRIA e validada no BOOT (mesma promessa
            # do SECRET_KEY/PII: falha no deploy, não na primeira execução às
            # 05h UTC). O dump carrega PII — jamais sobe ao Drive em claro.
            if self.BACKUP_ENABLED:
                if not self.BACKUP_ENCRYPTION_KEY or self.BACKUP_ENCRYPTION_KEY.startswith("TROCAR"):
                    raise ValueError(
                        "BACKUP_ENABLED=true exige BACKUP_ENCRYPTION_KEY em "
                        "produção (o backup nunca sai do VPS sem cifrar). Gere "
                        "com \"python3 -c 'from cryptography.fernet import "
                        "Fernet; print(Fernet.generate_key().decode())'\" e "
                        "guarde uma cópia FORA do servidor — perder a chave = "
                        "perder os backups."
                    )
                try:
                    Fernet(self.BACKUP_ENCRYPTION_KEY.encode())
                except Exception as e:
                    raise ValueError(
                        "BACKUP_ENCRYPTION_KEY inválida: precisa ser uma chave "
                        "Fernet (32 bytes url-safe base64)."
                    ) from e
            # Cofre de Credenciais: mesma promessa do PII/BACKUP — falha no
            # DEPLOY, não no primeiro uso. Sem chave estável, credenciais
            # cifradas viram lixo a cada restart (jamais autogerar em
            # produção). Valida o FORMATO de TODAS as chaves do CSV: uma
            # secundária malformada só estouraria meses depois, na primeira
            # decifragem de um registro antigo durante uma rotação.
            if not self.VAULT_MASTER_KEYS or self.VAULT_MASTER_KEYS.startswith("TROCAR"):
                raise ValueError(
                    "VAULT_MASTER_KEYS ausente ou placeholder em produção. "
                    "Gere com \"python3 -c 'from cryptography.fernet import "
                    "Fernet; print(Fernet.generate_key().decode())'\" e defina "
                    "no .env (CSV; a primeira chave cifra, todas decifram). "
                    "NUNCA derive do SECRET_KEY e nunca descarte uma chave que "
                    "ainda decifra credenciais existentes."
                )
            for chave in self.vault_master_keys_list:
                try:
                    Fernet(chave.encode())
                except Exception as e:
                    raise ValueError(
                        "VAULT_MASTER_KEYS contém chave inválida: cada item do "
                        "CSV precisa ser uma chave Fernet (32 bytes url-safe "
                        "base64)."
                    ) from e
            # ── LGPD — sanitização OBRIGATÓRIA se há provider externo elegível ──
            # Se QUALQUER provider externo (Anthropic/Groq/Maritaca) estiver
            # elegível (chave + habilitação + kill-switch AI_EXTERNAL_PROVIDERS_
            # ALLOWED) e a sanitização final estiver DESLIGADA, dados pessoais
            # poderiam seguir em claro ao provedor fora do VPS (art. 33/46). Falha
            # no BOOT, a menos que haja override consciente e auditável.
            externo_elegivel = bool(self.AI_EXTERNAL_PROVIDERS_ALLOWED and (
                (self.ANTHROPIC_ENABLED and self.ANTHROPIC_API_KEY)
                or self.GROQ_API_KEY
                or (self.MARITACA_ENABLED and self.MARITACA_API_KEY)
            ))
            if (externo_elegivel
                    and not self.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL
                    and not self.AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION):
                raise ValueError(
                    "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=false com provider "
                    "externo elegível (Anthropic/Groq/Maritaca) em produção: "
                    "dados pessoais poderiam ir em claro a provedor fora do VPS "
                    "(LGPD art. 33/46). Mantenha "
                    "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true; se houver parecer "
                    "do encarregado de dados para a exceção, defina explicitamente "
                    "AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION=true no .env."
                )
            # ── Soberania Maritaca (opt-in) — exige modelos "-br-sp" ──────────
            # Só valida quando o modo soberania está LIGADO e o provider ativo.
            if self.MARITACA_EXIGIR_SOBERANIA and self.MARITACA_ENABLED:
                nao_soberanos = [
                    nome for nome, valor in (
                        ("MARITACA_MODEL", self.MARITACA_MODEL),
                        ("MARITACA_MODEL_RAPIDO", self.MARITACA_MODEL_RAPIDO),
                    )
                    if not (valor or "").strip().endswith("-br-sp")
                ]
                if nao_soberanos:
                    raise ValueError(
                        "MARITACA_EXIGIR_SOBERANIA=true exige processamento em "
                        "território nacional: "
                        f"{' e '.join(nao_soberanos)} deve(m) usar as variantes "
                        "'-br-sp' (ex.: sabia-4-br-sp, sabiazinho-4-br-sp). "
                        "Ajuste os modelos no .env ou desligue "
                        "MARITACA_EXIGIR_SOBERANIA."
                    )
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
        if self.APP_ENV != "production" and not self.VAULT_MASTER_KEYS:
            # Só em desenvolvimento: chave efêmera do cofre para não travar o
            # ambiente local — com AVISO, porque credenciais cifradas com ela
            # se perdem no próximo restart (comportamento aceitável em dev).
            from cryptography.fernet import Fernet
            import warnings
            self.VAULT_MASTER_KEYS = Fernet.generate_key().decode()
            warnings.warn(
                "VAULT_MASTER_KEYS ausente — gerada chave Fernet EFÊMERA de "
                "desenvolvimento para o Cofre de Credenciais. Credenciais "
                "cifradas com ela serão perdidas no próximo restart; defina "
                "uma chave estável no .env para persistir.",
                stacklevel=2,
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
