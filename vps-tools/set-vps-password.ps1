# set-vps-password.ps1
# Grava a senha root da VPS em vps-tools/.env de forma segura.
# - Pede a senha com entrada OCULTA (nao aparece na tela nem no historico).
# - Preserva as demais linhas do .env.
# - Grava em UTF-8 SEM BOM (para nao corromper a leitura das outras chaves).
# - Confirma so o tamanho, nunca o valor.

$ErrorActionPreference = "Stop"
$path = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path $path)) {
    Write-Host "ERRO: arquivo nao encontrado: $path" -ForegroundColor Red
    exit 1
}

$sec = Read-Host "Cole a senha root da VPS e tecle Enter" -AsSecureString
$pw  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
           [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))

if ([string]::IsNullOrWhiteSpace($pw)) {
    Write-Host "ERRO: nada foi digitado. Nada alterado." -ForegroundColor Red
    exit 1
}

$out = @()
$found = $false
foreach ($line in (Get-Content $path)) {
    if ($line -match '^\s*VPS_PASSWORD\s*=') {
        $out += "VPS_PASSWORD=$pw"
        $found = $true
    } else {
        $out += $line
    }
}
if (-not $found) { $out += "VPS_PASSWORD=$pw" }

[IO.File]::WriteAllLines($path, $out, (New-Object System.Text.UTF8Encoding $false))

Write-Host ""
Write-Host "OK - VPS_PASSWORD gravada com $($pw.Length) caracteres." -ForegroundColor Green
Write-Host "Agora rode:  node vps-tools/run.js `"docker ps`""
