#!/usr/bin/env zsh

env_path="./.env"

if [[ ! -f "$env_path" ]]; then
  print -u2 ".env não encontrado em $env_path"
  return 1 2>/dev/null || exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  # Remove espaços no início e no fim
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"

  # Ignora linhas vazias e comentários
  [[ -z "$line" || "$line" == \#* ]] && continue

  # Ignora linhas sem "="
  [[ "$line" != *"="* ]] && continue

  # Separa apenas na primeira ocorrência de "="
  key="${line%%=*}"
  value="${line#*=}"

  # Remove espaços ao redor da chave
  key="${key#"${key%%[![:space:]]*}"}"
  key="${key%"${key##*[![:space:]]}"}"

  # Remove espaços ao redor do valor
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"

  # Remove aspas simples ou duplas externas
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:-1}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:-1}"
  fi

  export "$key=$value"
done < "$env_path"

print "Variáveis do .env carregadas com sucesso."