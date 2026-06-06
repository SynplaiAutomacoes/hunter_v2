"""Update all import paths to bypass shims and point directly to new locations."""
from __future__ import annotations

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIR = os.path.join(PROJECT_ROOT, "apps")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

REPLACEMENTS: list[tuple[str, str]] = [
    # --- Presentation layer ---
    (r"from apps\.core\.views import", "from apps.core.presentation.views import"),
    (r"from apps\.core\.forms import", "from apps.core.presentation.forms import"),
    (r"from apps\.core\.widgets import", "from apps.core.presentation.widgets import"),
    (r"from apps\.core\.navigation import", "from apps.core.presentation.navigation import"),
    (r"from apps\.core\.favorites import", "from apps.core.presentation.favorites import"),
    (r"from apps\.core\.context_processors import", "from apps.core.presentation.context_processors import"),
    (r"from apps\.core\.tables import", "from apps.core.presentation.tables import"),
    (r"from apps\.core\.middlewares import", "from apps.core.presentation.middlewares import"),

    # --- Infrastructure layer ---
    (r"from apps\.core\.models import", "from apps.core.infrastructure.models import"),
    (r"from apps\.core\.fields import", "from apps.core.infrastructure.fields import"),
    (r"from apps\.core\.search import", "from apps.core.infrastructure.search import"),
    (r"from apps\.core\.query_filters import", "from apps.core.infrastructure.query_filters import"),
    (r"from apps\.core\.pdf_playwright import", "from apps.core.infrastructure.pdf import"),
    (r"from apps\.core\.services\.", "from apps.core.infrastructure.services."),

    # --- Special: alert_confirm_layout moved to presentation.utils ---
    (r"from apps\.core\.utils import alert_confirm_layout", "from apps.core.presentation.utils import alert_confirm_layout"),
]

EXCLUDE_DIRS = {"__pycache__", ".venv", ".git", "node_modules"}
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
    print("Updating import paths to bypass shims...")
    process_directory(APPS_DIR, "apps/")
    process_directory(CONFIG_DIR, "config/")
    print("\nDone.")


if __name__ == "__main__":
    main()
