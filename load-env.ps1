# Carrega variáveis do arquivo .env na sessão atual do PowerShell.
# Uso: . .\load-env.ps1

$envPath = Join-Path -Path (Get-Location) -ChildPath ".env"

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    Write-Error ".env não encontrado em $envPath"
    exit 1
}

Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()

    # Ignora linhas vazias e comentários
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
        return
    }

    # Ignora linhas sem "="
    $eqIndex = $line.IndexOf("=")
    if ($eqIndex -lt 1) {
        return
    }

    $key = $line.Substring(0, $eqIndex).Trim()
    $value = $line.Substring($eqIndex + 1).Trim()

    if ([string]::IsNullOrWhiteSpace($key)) {
        return
    }

    # Remove aspas simples ou duplas externas
    if (
        ($value.Length -ge 2) -and (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        )
    ) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    Set-Item -Path "Env:$key" -Value $value
}

Write-Host "Variáveis do .env carregadas com sucesso."
