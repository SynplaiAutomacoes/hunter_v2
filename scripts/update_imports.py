"""Update all import paths — Phase 2: documents migration."""
from __future__ import annotations

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(PROJECT_ROOT, "apps")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

REPLACEMENTS: list[tuple[str, str]] = [
    # --- documents/contract → domain/contracts/documents ---
    (r"from apps\.core\.documents\.contract import", "from apps.core.domain.contracts.documents import"),

    # --- documents/http → presentation/pdf/http ---
    (r"from apps\.core\.documents\.http import", "from apps.core.presentation.pdf.http import"),

    # --- documents/renderer → infrastructure/pdf/renderer ---
    (r"from apps\.core\.documents\.renderer import", "from apps.core.infrastructure.pdf.renderer import"),

    # --- documents/services → infrastructure/services/signature ---
    (r"from apps\.core\.documents\.services import", "from apps.core.infrastructure.services.signature import"),

    # --- documents/signature → split: normalize_phone + token types → domain,
    #     token ops → infra, URL builders → presentation ---
    #     This is handled by specific replacements below:
    (r"from apps\.core\.documents\.signature import build_absolute_app_url", "from apps.core.presentation.signature import build_absolute_app_url"),
    (r"from apps\.core\.documents\.signature import build_document_signature_url", "from apps.core.presentation.signature import build_document_signature_url"),
    (r"from apps\.core\.documents\.signature import normalize_signature_phone_number", "from apps.core.domain.contracts.documents import normalize_signature_phone_number"),
    (r"from apps\.core\.documents\.signature import SignatureTokenError", "from apps.core.domain.contracts.documents import SignatureTokenError"),
    (r"from apps\.core\.documents\.signature import SignatureTokenPayload", "from apps.core.domain.contracts.documents import SignatureTokenPayload"),
    (r"from apps\.core\.documents\.signature import SIGNATURE_POSITION", "from apps.core.domain.contracts.documents import SIGNATURE_POSITION"),
    (r"from apps\.core\.documents\.signature import parse_document_signature_token", "from apps.core.infrastructure.services.signature import parse_document_signature_token"),
    (r"from apps\.core\.documents\.signature import build_document_signature_payload", "from apps.core.infrastructure.services.signature import build_document_signature_payload"),
    (r"from apps\.core\.documents\.signature import build_document_signature_token", "from apps.core.infrastructure.services.signature import build_document_signature_token"),
    (r"from apps\.core\.documents\.signature import build_signature_signatory_and_observers", "from apps.core.infrastructure.services.signature import build_signature_signatory_and_observers"),
    (r"from apps\.core\.documents\.signature import build_signature_fields", "from apps.core.infrastructure.services.signature import build_signature_fields"),

    # --- catch remaining multi-import lines from documents.signature ---
    # These handle combined imports like:
    #   from apps.core.documents.signature import (SignatureTokenError, parse_document_signature_token, ...)
    # We transform them to import from infrastructure (where most functions live),
    # and the domain-only items (SignatureTokenError, normalize_signature_phone_number, etc.)
    # will need a second pass. Let's handle the common patterns:
    (r"from apps\.core\.documents\.signature import \(", "from apps.core.infrastructure.services.signature import ("),
    # Single-line multi-imports
    (r"from apps\.core\.documents\.signature import (?!build_absolute_app_url|build_document_signature_url|normalize_signature_phone_number|SignatureTokenError|SignatureTokenPayload|SIGNATURE_POSITION)",
     "from apps.core.infrastructure.services.signature import "),

    # --- documents/webhook → presentation/webhooks/supersign ---
    (r"from apps\.core\.documents\.webhook import", "from apps.core.presentation.webhooks.supersign import"),

    # --- documents/gateways → infrastructure/gateways (internal imports within documents/) ---
    (r"from apps\.core\.documents\.gateways\.supersign import", "from apps.core.infrastructure.gateways.supersign import"),
]

EXCLUDE_DIRS = {"__pycache__", ".venv", ".git", "node_modules", "scripts"}
EXCLUDE_FILE_PATTERNS = (".pyc", ".pyo")


def should_process_file(filepath: str) -> bool:
    _, ext = os.path.splitext(filepath)
    if ext not in (".py",):
        return False
    for pattern in EXCLUDE_FILE_PATTERNS:
        if filepath.endswith(pattern):
            return False
    return True


def process_directory(root_dir: str, label: str) -> None:
    updated_files = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if not should_process_file(filepath):
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            original = content
            for pattern, replacement in REPLACEMENTS:
                content = re.sub(pattern, replacement, content)

            if content != original:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                rel = os.path.relpath(filepath, PROJECT_ROOT)
                updated_files.append(rel)

    if updated_files:
        print(f"\n=== {label} ({len(updated_files)} files) ===")
        for f in sorted(updated_files):
            print(f"  {f}")
    else:
        print(f"\n=== {label}: no changes ===")


def main() -> None:
    print("Updating import paths — documents migration...")
    process_directory(APPS_DIR, "apps/")
    process_directory(CONFIG_DIR, "config/")
    print("\nDone.")


if __name__ == "__main__":
    main()
