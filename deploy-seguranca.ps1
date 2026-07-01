# deploy-seguranca.ps1
# Sobe os 11 arquivos da camada de segurança (branch seguranca/reaplicacao-fases-3-4)
# da base canônica para a VPS (/opt/ejc). Roda de C:\Users\User\EJC (tem vps-tools/.env).
# NÃO reinicia nada — só envia os arquivos. O rebuild/migração é feito depois, à mão.

$ErrorActionPreference = "Stop"
$origem = "C:\Users\User\ejc-canonical\backend"
$destBase = "/opt/ejc/backend"

$arquivos = @(
    "alembic/versions/055_rag_isolation.py",
    "app/models/rag.py",
    "app/routers/cases.py",
    "app/routers/documents.py",
    "app/routers/legal_docs.py",
    "app/routers/rag.py",
    "app/routers/ramos.py",
    "app/services/ai_service.py",
    "app/services/analise_estrategica.py",
    "app/services/case_intel.py",
    "app/services/ingestion_service.py"
)

Write-Host "Enviando $($arquivos.Count) arquivos da camada de seguranca para a VPS..." -ForegroundColor Cyan
$ok = 0
foreach ($rel in $arquivos) {
    $local = Join-Path $origem ($rel -replace '/', '\')
    $remoto = "$destBase/$rel"
    if (-not (Test-Path $local)) {
        Write-Host "  FALTA (local): $local" -ForegroundColor Red
        continue
    }
    Write-Host "  -> $rel" -ForegroundColor Gray
    node vps-tools/upload.js $remoto $local
    if ($LASTEXITCODE -eq 0) { $ok++ }
}
Write-Host ""
Write-Host "Concluido: $ok/$($arquivos.Count) arquivos enviados." -ForegroundColor Green
