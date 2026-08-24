# Caminho do .env (ajuste se necessário)
$envPath = ".\.env"

if (-Not (Test-Path $envPath)) {
    Write-Error ".env não encontrado em $envPath"
    return
}

Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()

    # Ignorar linhas vazias e comentários
    if ($line -and -not $line.StartsWith("#")) {

        # Separar apenas na primeira ocorrência de "="
        $key, $value = $line -split "=", 2

        # Remover possíveis aspas
        $value = $value.Trim('"').Trim("'")

        # Definir variável de ambiente na sessão atual
        Set-Item -Path "Env:$key" -Value $value
    }
}

Write-Host "Variáveis do .env carregadas com sucesso."