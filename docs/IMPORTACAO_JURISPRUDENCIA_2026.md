# Runbook — Importação em massa de jurisprudência 2026 (VPS)

Objetivo: carregar o máximo de julgados de **2026** (TJMG, Turmas Recursais/JEC,
TRT, STF/STJ/TST) na base RAG + base de citações validadas do EJC, usando o
importador on-demand (`POST /conhecimento/importar-jurisprudencia`) com o
filtro `ano=2026`.

> **Governança (obrigatório saber):** TUDO que entra por aqui passa pela
> curadoria/governança do RAG — confiança por fonte, quarentena/aprovação
> (`extra.rag_status`, painel de IA/governança) — antes de virar contexto de
> IA ou citação em peça (gate anti-alucinação `_fonte_juris_validada`).
> Importar ≠ liberar.
>
> **Nota:** petições reais do escritório entram pelo upload/GED, **não** por
> importador externo; modelos didáticos já existem na Bíblia (269).

## 1. Pré-requisitos na VPS

- Backend no ar; usuário com papel `advogado`+ (gate do endpoint).
- Fontes habilitadas (default já inclui as três): `JURIS_IMPORT_FONTES=lexml,stj,tjmg`.
- Rate limit do endpoint: **3 POST/min** — o loop abaixo respeita com `sleep 25`.
- Limites de paginação existentes (não alterar sem revisão):
  - `limite` por requisição: 1–100 (default 20).
  - LexML SRU: 5 páginas × 50 registros por busca (`MAX_PAGINAS`).
  - TJMG: 5 páginas × 50 por busca; janela de datas 01/01–31/12 do ano vai ao
    formulário e o filtro client-side garante o ano.
  - STJ Dados Abertos: apenas o lote mensal mais recente por órgão — filtro
    `ano=2026` funciona bem para o ano corrente.

```bash
# Token (uma vez por sessão de carga)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<advogado>@...","password":"<senha>"}' | jq -r .access_token)
```

## 2. Comando base (uma consulta, uma fonte)

```bash
importar() {  # $1=fonte  $2=consulta  $3=tribunal(ou vazio)  $4=limite
  curl -s -X POST http://localhost:8000/conhecimento/importar-jurisprudencia \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"fonte\":\"$1\",\"consulta\":\"$2\",\
$( [ -n "$3" ] && echo "\"tribunal\":\"$3\"," )\"limite\":${4:-100},\"ano\":2026}"
  sleep 25   # respeita o rate limit de 3/min
}
# Status do job: GET /conhecimento/importar-jurisprudencia/status/<job_id>
# Frescor por fonte: GET /conhecimento/importar-jurisprudencia/fontes
```

## 3. Execução por fonte

```bash
# LexML — tribunais superiores (refinamento server-side por URN):
for T in STF STJ TST; do importar lexml "$CONSULTA" "$T" 100; done

# LexML — TJMG / TRT / Turmas Recursais (filtro CLIENT-SIDE: a consulta vai
# sem refinamento de URN e a sigla é inferida do registro — correto, porém
# menos eficiente; espere menos resultados por varredura de 250 registros):
for T in TJMG TRT JEC; do importar lexml "$CONSULTA" "$T" 100; done
# TRT de MG especificamente: tribunal "TRT-3".

# STJ Dados Abertos (espelhos de acórdãos — lote mensal mais recente):
importar stj "$CONSULTA" "" 100

# TJMG — conector direto (formulário oficial de acórdãos; scraping tolerante,
# fail-safe: se o HTML do TJMG mudar, degrada para 0 resultados e o painel de
# fontes marca erro/parcial — nunca derruba o worker):
importar tjmg "$CONSULTA" TJMG 100
```

## 4. Varredura temática sugerida (~10 consultas, áreas do escritório)

```bash
CONSULTAS=(
  "dano moral consumidor"
  "negativação indevida cadastro inadimplentes"
  "plano de saúde negativa de cobertura"
  "revisional contrato bancário juros"
  "rescisão indireta"
  "horas extras"
  "vínculo empregatício reconhecimento"
  "alimentos guarda"
  "usucapião"
  "acidente de trânsito indenização"
  "responsabilidade civil prestador de serviço"
  "execução fiscal prescrição"
)
for C in "${CONSULTAS[@]}"; do
  importar tjmg "$C" TJMG 100
  importar stj  "$C" ""   100
  for T in STF STJ TST TJMG TRT JEC; do importar lexml "$C" "$T" 100; done
done
```

Dedup é automático (chave por tribunal+número; TJMG compartilha o keyspace
`tjmg:<registro>` com o crawler agendado; STJ compartilha `stj:<registro>` com
o job diário) — rodar de novo não duplica; o resumo reporta `duplicados` e,
com `ano`, `fora_do_ano`.

## 5. Volume adicional TJMG (crawler agendado)

Para carga contínua do TJMG além do on-demand, habilitar o crawler agendado
(`.env`): `TJMG_INGEST_ENABLED=true`, `TJMG_INGEST_TEMAS` (CSV, default = temas
do escritório), `TJMG_INGEST_JANELA_DIAS` (ex.: 365 para cobrir 2026 ao longo
do ano), `TJMG_INGEST_MAX_POR_TEMA` (default 50).

## 6. Depois da carga

1. Painel de governança de IA: revisar quarentena/aprovação dos docs novos
   (categoria `jurisprudencia`).
2. `GET /conhecimento/importar-jurisprudencia/fontes` — conferir
   `ultimo_status`/`registros_novos` por fonte.
3. Trilha completa em `audit_logs` (ação `IMPORTACAO_JURISPRUDENCIA`, inclui
   `ano`) e `fontes_ingestao`.
