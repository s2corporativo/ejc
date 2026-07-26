# Runbook — Deploy da Sala Jurídica Conversacional (V1)

**Branch:** `feat/sala-juridica-v1` · **Migration:** `121_sala_juridica_chat` · **Data:** 2026-07-26

## O que este deploy entrega

1. Remove `sala_de_guerra`, `sala_de_guerra_v3` e `/sala-analise` (com redirects — nenhuma URL salva vira 404).
2. Cria o módulo **Sala Jurídica** (`/sala-juridica`): chat jurídico persistido com área de trabalho livre, estado probatório versionado, anexos com OCR, conversão controlada em caso e extração automática de estado.
3. Rehospeda o Dossiê de Pressão (`diplomacia_v3`) na Calculadora de Acordo do caso (aba Liquidez).

## Pré-requisitos

- Backup do banco **antes** da migration: `./scripts/backup/backup.sh` (ou rotina equivalente da VPS).
- Ollama ativo (`OLLAMA_BASE_URL`) — a extração automática de estado usa o provider local (task_type `resumo`). Sem Ollama, a extração degrada silenciosamente para o merge de fontes (fail-soft, não bloqueia nada).

## Passos (VPS)

```bash
cd /caminho/do/ejc
git fetch origin && git checkout feat/sala-juridica-v1   # ou main, após merge do PR

# 1. Migration (cria 4 tabelas legal_chat_*; zero DROP — reversível)
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current   # deve exibir 121_sala_juridica_chat

# 2. Rebuild e subida
docker compose build backend frontend
docker compose up -d

# 3. Smoke test
curl -sf localhost:8000/api/health || echo "FALHA health"
# autenticado: GET /api/sala-juridica deve retornar []
```

## Verificação funcional (checklist)

- [ ] Menu lateral: "Sala Jurídica" entre os essenciais; "Triagem e Raio-X" no grupo Pesquisar & IA.
- [ ] `/sala-analise` redireciona para `/raio-x`; `/casos/{id}/sala-de-guerra` redireciona para `/casos/{id}?tab=teses`.
- [ ] Nova análise → mensagem em "Conversa livre" responde via Ollama (custo R$ 0 no AILog).
- [ ] Anexo PDF → extração aparece no painel de documentos.
- [ ] Resposta gera nova versão de estado (`origem=ia_extracao` com Ollama ativo; `origem=ia` sem).
- [ ] Conversão em caso exige as 2 confirmações e congela a sessão (PATCH posterior → 409).
- [ ] Aba Liquidez do caso: "Gerar dossiê" produz argumentação com aviso de rascunho.

## Rollback

```bash
docker compose exec backend alembic downgrade 120_chunk_pagina   # remove as 4 tabelas
git checkout main && docker compose build backend frontend && docker compose up -d
```

Perda no downgrade: apenas dados criados nas tabelas `legal_chat_*` após o deploy. Nenhuma tabela pré-existente é tocada.

## Flags relevantes (`.env`)

| Variável | Default | Efeito |
|---|---|---|
| `SALA_JURIDICA_AUTO_ESTADO` | `true` | Extração automática do estado jurídico pós-resposta (provider local) |
| `AI_PROVIDER_PRIORITY` | `ollama,anthropic,maritaca,groq` | Mantém o roteamento econômico |
| `AI_REQUIRE_HITL` | `true` | Não alterar: toda saída é rascunho revisável |

## Pendências conhecidas (V2/V3)

- Ditado por voz (Web Speech API) e transcrição Whisper — gates `AUDIO_TRANSCRIPTION_*` seguem desligados por padrão (LGPD/DPA).
- Pesquisa externa com segregação fonte oficial ≠ prova do caso.
- Superfície de edição de `cases.tese_principal/pontos_fortes/pontos_fracos` (a antiga tela de escrita era a Sala de Guerra; hoje a Jornada só lê).
- Normalização do estado JSONB em tabelas dedicadas, se surgir consulta relacional entre sessões.
