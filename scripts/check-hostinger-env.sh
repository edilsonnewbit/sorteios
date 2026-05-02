#!/bin/bash
# Script de validação de variáveis de ambiente para deploy no Hostinger
# Executado no GitHub Actions antes de fazer deploy

set -e

echo "🔍 Validando variáveis de ambiente para Sorteios..."

REQUIRED_SECRETS=(
  "POSTGRES_PASSWORD"
  "SESSION_SECRET"
  "ADMIN_API_KEY"
)

REQUIRED_VARS=(
  "POSTGRES_USER"
  "HOSTINGER_API_KEY"
  "HOSTINGER_VM_ID"
)

OPTIONAL_VARS=(
  "LOG_LEVEL"
  "ENVIRONMENT"
)

# Verificar Secrets (obrigatórios)
echo ""
echo "📋 Verificando Secrets obrigatórios..."
for secret in "${REQUIRED_SECRETS[@]}"; do
  eval "value=\${$secret}"
  if [ -z "$value" ]; then
    echo "❌ ERRO: Secret '$secret' não está definido no GitHub"
    exit 1
  fi
  echo "✅ $secret: OK (${#value} chars)"
done

# Verificar Vars obrigatórias
echo ""
echo "📋 Verificando Variáveis obrigatórias..."
for var in "${REQUIRED_VARS[@]}"; do
  eval "value=\${$var}"
  if [ -z "$value" ]; then
    echo "❌ ERRO: Variável '$var' não está definida"
    exit 1
  fi
  echo "✅ $var: OK"
done

# Verificar Vars opcionais
echo ""
echo "📋 Verificando Variáveis opcionais..."
for var in "${OPTIONAL_VARS[@]}"; do
  eval "value=\${$var:-<not set>}"
  echo "ℹ️  $var: $value"
done

# Validações adicionais
echo ""
echo "🔍 Validações adicionais..."

# Verificar que PASSWORD tem comprimento mínimo
PW_LENGTH=${#POSTGRES_PASSWORD}
if [ "$PW_LENGTH" -lt 16 ]; then
  echo "⚠️  AVISO: POSTGRES_PASSWORD tem apenas $PW_LENGTH chars (recomendado: 24+)"
fi

# Verificar que ADMIN_API_KEY é hexadecimal
if ! [[ "$ADMIN_API_KEY" =~ ^[0-9a-f]{32}$ ]]; then
  echo "⚠️  AVISO: ADMIN_API_KEY não parece ser hexadecimal de 32 chars"
fi

# Verificar que SESSION_SECRET é hexadecimal
if ! [[ "$SESSION_SECRET" =~ ^[0-9a-f]{32}$ ]]; then
  echo "⚠️  AVISO: SESSION_SECRET não parece ser hexadecimal de 32 chars"
fi

echo ""
echo "✨ Todas as validações passaram!"
echo ""
echo "📊 Resumo de Deploy:"
echo "   - POSTGRES_USER: $POSTGRES_USER"
echo "   - PASSWORD length: $PW_LENGTH chars"
echo "   - ADMIN_API_KEY: ${ADMIN_API_KEY:0:8}... (${#ADMIN_API_KEY} chars)"
echo "   - SESSION_SECRET: ${SESSION_SECRET:0:8}... (${#SESSION_SECRET} chars)"
echo "   - HOSTINGER_VM_ID: $HOSTINGER_VM_ID"
echo "   - Environment: ${ENVIRONMENT:-production}"
echo "   - Log Level: ${LOG_LEVEL:-info}"
