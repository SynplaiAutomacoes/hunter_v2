import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import logging
import time
from django.conf import settings

print("=" * 60)
print("TESTE LOKI HANDLER")
print("=" * 60)

print("\n[1] Configuração:")
print(f"  LOKI_ENABLED: {settings.LOKI_ENABLED}")
print(f"  LOKI_ENDPOINT: {settings.LOKI_ENDPOINT}")
print(f"  ENVIRONMENT: {settings.ENVIRONMENT}")

print("\n[2] Handlers do root logger:")
for handler in logging.getLogger().handlers:
    print(f"  - {handler.__class__.__name__}")

print("\n[3] Enviando log de teste...")
logger = logging.getLogger("test.loki")
logger.error("Teste de log para Loki - %s", time.strftime("%H:%M:%S"))

print("\n[4] Aguardando 6 segundos para flush...")
time.sleep(6)

print("\n[5] Verifique no Grafana Cloud:")
print("  Explore -> Loki -> Query:")
print(f'  {{service="{settings.ENVIRONMENT}"}} |= "Teste de log para Loki"')
print("=" * 60)
