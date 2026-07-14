from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

from config.settings import *  # noqa: F403
from config.settings import DATABASES as BASE_DATABASES


BENCHMARK_DATABASE_PREFIX = "hunter_v2_perf_"
BENCHMARK_DB_NAME = os.getenv("BENCHMARK_DB_NAME", "").strip()

if not BENCHMARK_DB_NAME.startswith(BENCHMARK_DATABASE_PREFIX):
    raise ImproperlyConfigured(
        f"BENCHMARK_DB_NAME deve começar com {BENCHMARK_DATABASE_PREFIX!r}; "
        "o banco padrão nunca pode ser usado pelas configurações de benchmark."
    )

if BENCHMARK_DB_NAME == "meu_crm":
    raise ImproperlyConfigured("O banco meu_crm é proibido no ambiente de benchmark.")

DATABASES = {
    **BASE_DATABASES,
    "default": {
        **BASE_DATABASES["default"],
        "NAME": BENCHMARK_DB_NAME,
        "CONN_MAX_AGE": 0,
    },
}

BENCHMARK_ENVIRONMENT = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PERF_LOGGING_ENABLED = True
PERF_LOG_QUERIES = True
PERF_LOG_MIN_MS = 0
