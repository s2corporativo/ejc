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
- `POST /api/rag/google-drive/sync`
- `POST /api/rag/google-drive/reindex/{file_id}`

As rotas de escrita exigem perfil `superadmin`, `admin` ou `socio`.

## Autenticação recomendada quando a organização bloqueia chave de Service Account

Se o Google Cloud mostrar a política `iam.managed.disableServiceAccountKeyCreation`, não tente forçar a criação da chave. Use OAuth de usuário.

Configure no `.env` do backend:

```env
GOOGLE_DRIVE_ENABLED=true
GOOGLE_DRIVE_AUTH_MODE=oauth
GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID=1fEQJsQRZzRNCK9uVCTpe1ka9i2UBhiLT
GOOGLE_DRIVE_OAUTH_USER_FILE=/app/secrets/google-drive-authorized-user.json
GOOGLE_DRIVE_SHARED_DRIVE_ID=
GOOGLE_DRIVE_DEFAULT_CATEGORIA=doutrina
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
- alterações geram nova versão pelo `upsert_documento()` existente;
- conteúdo inalterado retorna `inalterado` e não duplica chunks.

## Estado de sincronização

O serviço cria automaticamente a tabela `google_drive_sync_state`, caso ela ainda não exista, com dados de última execução, status, erro e totais processados.

## Observações operacionais

- Não versionar credenciais do Google.
- Documentos sigilosos devem ter política clara de categoria, escopo e retenção.
- A fonte soberana para respostas da IA continua sendo o RAG interno, não a leitura direta do Drive.
