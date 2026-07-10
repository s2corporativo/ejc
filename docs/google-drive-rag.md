# Google Drive para a Base de Conhecimento RAG do EJC

Este módulo permite usar uma pasta do Google Drive como fonte documental para a Base de Conhecimento da IA do EJC.

A integração não substitui o RAG interno. O Drive funciona apenas como origem dos arquivos. O EJC baixa, extrai texto/OCR, deduplica, versiona e grava o conteúdo em `knowledge_docs` e `knowledge_chunks`, usando o pipeline existente de embeddings e pgvector.

## Pasta definida para o EJC

Pasta informada pelo Dr. Clóvis para alimentar a Base de Conhecimento:

- URL: `https://drive.google.com/drive/folders/1fEQJsQRZzRNCK9uVCTpe1ka9i2UBhiLT`
- ID: `1fEQJsQRZzRNCK9uVCTpe1ka9i2UBhiLT`

Use este ID em `GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID`.

## Rotas disponíveis

As rotas foram registradas sob o router RAG existente:

- `GET /api/rag/google-drive/status`
- `GET /api/rag/google-drive/files?limit=100`
- `GET /api/rag/google-drive/audit?limit=500`
- `POST /api/rag/google-drive/curadoria/preview`
- `POST /api/rag/google-drive/curadoria/apply`
- `POST /api/rag/google-drive/sync`
- `POST /api/rag/google-drive/reindex/{file_id}`

As rotas de escrita exigem perfil `superadmin`, `admin` ou `socio`.

## Auditoria e ranqueamento antes da sincronização

Use primeiro:

```http
GET /api/rag/google-drive/audit?limit=500
```

A auditoria não altera o banco. Ela lista os arquivos recursivamente, classifica por nome/caminho/MIME e devolve:

- `ranking`, ordenado por indexabilidade e prioridade;
- `por_categoria_sugerida`;
- `por_area_juridica`;
- `por_tipo_fonte`;
- arquivos ignorados por teste, rascunho, backup, MIME não permitido ou baixa qualidade operacional.

## Classificação automática

O sincronizador agora trabalha com `GOOGLE_DRIVE_AUTO_CATEGORIZAR=true` por padrão.

Categorias sugeridas automaticamente:

| Sinal encontrado | Categoria RAG sugerida | Prioridade |
|---|---:|---:|
| Lei, decreto, código, portaria, resolução | `legislacao_*` | 100 |
| Súmula STF/STJ/TST/TJMG | `sumula_*` | 95 |
| Julgado, acórdão, ementa, precedente | `jurisprudencia_*` | 90 |
| Peça prática, minuta, modelo, petição, agravo | `modelo_documento_juridico` | 70 |
| Manual, apostila, guia, doutrina | `doutrina` | 60 |
| Sem sinal forte | `doutrina` com confiança baixa | 40 |
| Teste, rascunho, backup, não indexar | `nao_indexar` | 0 |

A classificação fica gravada em `knowledge_docs.extra.taxonomy`, junto com o caminho original do Drive em `knowledge_docs.extra.drive.full_path`.

## Sincronização recomendada

Fluxo seguro:

1. Auditar:

```http
GET /api/rag/google-drive/audit?limit=500
```

2. Corrigir nomes/pastas no Drive, se necessário.

3. Sincronizar com classificação automática:

```json
{
  "limit": 500,
  "categorizar_automaticamente": true,
  "confianca": "media"
}
```

4. Conferir o RAG:

```http
GET /api/rag/stats
GET /api/rag/status
GET /api/rag/docs?page_size=100
```

Para forçar uma categoria única em uma sincronização excepcional:

```json
{
  "categoria": "modelo_documento_juridico",
  "categorizar_automaticamente": false,
  "confianca": "media"
}
```

Use esse modo com cuidado. Ele volta ao comportamento manual e pode gerar erro de curadoria se misturar leis, jurisprudência, doutrina e modelos na mesma pasta.

## Reclassificação de documentos antigos já ingeridos

Se documentos do Google Drive foram sincronizados antes da taxonomia automática, alguns podem ter entrado como `doutrina` mesmo sendo peças, minutas ou material de teste.

Use o script abaixo sempre em duas etapas.

### 1. Simular sem alterar banco

```bash
docker compose exec backend python scripts/reclassificar_rag_drive.py --dry-run --only-changes --output /tmp/rag-drive-reclassificacao-dry-run.json
```

Revise o JSON gerado e confira principalmente:

- `categoria_atual`;
- `categoria_final`;
- `vigente_atual`;
- `vigente_final`;
- `motivo`;
- `sinais`.

### 2. Aplicar somente após revisar o dry-run

```bash
docker compose exec backend python scripts/reclassificar_rag_drive.py --apply --only-changes --output /tmp/rag-drive-reclassificacao-apply.json
```

O script não apaga documentos fisicamente. Quando a taxonomia identificar arquivo de teste, rascunho, backup ou `não indexar`, o documento é marcado como:

- `categoria = nao_indexar`;
- `vigente = false`.

A alteração preserva histórico em `knowledge_docs.extra.reclassification_history`, permitindo auditoria e rollback manual controlado.

## Curadoria por API

A mesma rotina pode ser usada pelo frontend sem acesso ao terminal da VPS.

### Pré-visualização

```http
POST /api/rag/google-drive/curadoria/preview
Content-Type: application/json
```

```json
{
  "limit": 500,
  "only_changes": true
}
```

Essa rota é somente leitura e executa o serviço em `dry_run`.

### Aplicação protegida

```http
POST /api/rag/google-drive/curadoria/apply
Content-Type: application/json
```

```json
{
  "limit": 500,
  "only_changes": true,
  "confirmacao": "RECLASSIFICAR_RAG_DRIVE"
}
```

Controles obrigatórios:

- autenticação ativa;
- perfil `superadmin`, `admin` ou `socio`;
- confirmação textual exata;
- nenhuma exclusão física;
- histórico preservado em `extra.reclassification_history`;
- rollback por restauração dos valores anteriores gravados no histórico.

A aplicação deve ser executada apenas depois de comparar o resultado de `preview` com os documentos esperados.

## Autenticação recomendada quando a organização bloqueia chave de Service Account

Se o Google Cloud mostrar a política `iam.managed.disableServiceAccountKeyCreation`, não tente forçar a criação da chave. Use OAuth de usuário.

Configure no `.env` do backend:

```env
GOOGLE_DRIVE_ENABLED=true
GOOGLE_DRIVE_AUTH_MODE=oauth
GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID=1fEQJsQRZzRNCK9uVCTpe1ka9i2UBhiLT
GOOGLE_DRIVE_OAUTH_USER_FILE=/app/secrets/google-drive-authorized-user.json
GOOGLE_DRIVE_SHARED_DRIVE_ID=
GOOGLE_DRIVE_DEFAULT_CATEGORIA=auto
GOOGLE_DRIVE_AUTO_CATEGORIZAR=true
GOOGLE_DRIVE_MAX_FILE_MB=50
GOOGLE_DRIVE_ALLOWED_MIME_TYPES=
```

O arquivo `google-drive-authorized-user.json` deve ser um arquivo OAuth do tipo `authorized_user`, gerado fora do Git e montado na VPS em `/app/secrets`.

## Alternativa com Service Account

Se a política da organização permitir chave de Service Account, também é aceito:

```env
GOOGLE_DRIVE_ENABLED=true
GOOGLE_DRIVE_AUTH_MODE=service_account
GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID=1fEQJsQRZzRNCK9uVCTpe1ka9i2UBhiLT
GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE=/app/secrets/google-drive-service-account.json
GOOGLE_DRIVE_DEFAULT_CATEGORIA=auto
GOOGLE_DRIVE_AUTO_CATEGORIZAR=true
```

A credencial deve ficar fora do Git; o `.gitignore` já bloqueia arquivos com padrão `*-service-account*.json`.

## Tipos indexáveis por padrão

- PDF;
- DOCX;
- XLSX;
- TXT/CSV;
- JPG/PNG, quando OCR estiver disponível;
- Google Docs exportado como texto;
- Google Sheets exportado como CSV.

## Rastreabilidade

Para cada arquivo ingerido:

- `chave_origem = gdrive:{file_id}`;
- o link original fica em `fonte`;
- metadados do Drive ficam em `knowledge_docs.extra.drive`;
- classificação sugerida fica em `knowledge_docs.extra.taxonomy`;
- alterações geram nova versão pelo `upsert_documento()` existente;
- conteúdo inalterado retorna `inalterado` e não duplica chunks.

## Estado de sincronização

O serviço cria automaticamente a tabela `google_drive_sync_state`, caso ela ainda não exista, com dados de última execução, status, erro e totais processados.

## Observações operacionais

- Não versionar credenciais do Google.
- Documentos sigilosos devem ter política clara de categoria, escopo e retenção.
- A fonte soberana para respostas da IA continua sendo o RAG interno, não a leitura direta do Drive.
- Peças e minutas internas devem entrar como apoio redacional/estratégico, não como fonte normativa.
