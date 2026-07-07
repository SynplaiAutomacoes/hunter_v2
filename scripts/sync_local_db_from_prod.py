from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


REQUIRED_BINARIES = ("pg_dump", "dropdb", "createdb", "pg_restore")


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    name: str
    user: str
    password: str
    host: str
    port: str
    sslmode: str | None = None

    @classmethod
    def from_env(cls, *, prefix: str, fallback_prefixes: tuple[str, ...] = ()) -> "DatabaseConfig":
        parsed_url = cls._load_database_url(prefix=prefix, fallback_prefixes=fallback_prefixes)
        if parsed_url is not None:
            return parsed_url

        def resolve(key: str, default: str | None = None) -> str:
            candidate_keys = [f"{prefix}{key}", *(f"{fallback}{key}" for fallback in fallback_prefixes)]
            for candidate in candidate_keys:
                value = os.getenv(candidate)
                if value:
                    return value
            if default is not None:
                return default
            joined_keys = ", ".join(candidate_keys)
            raise SyncError(f"Variavel obrigatoria ausente: {joined_keys}")

        return cls(
            name=resolve("DB_NAME"),
            user=resolve("DB_USER"),
            password=resolve("DB_PASSWORD"),
            host=resolve("DB_HOST", "localhost"),
            port=resolve("DB_PORT", "5432"),
            sslmode=os.getenv(f"{prefix}DB_SSLMODE") or next((os.getenv(f"{fallback}DB_SSLMODE") for fallback in fallback_prefixes if os.getenv(f"{fallback}DB_SSLMODE")), None),
        )

    @classmethod
    def _load_database_url(cls, *, prefix: str, fallback_prefixes: tuple[str, ...]) -> "DatabaseConfig | None":
        candidate_keys = [f"{prefix}DATABASE_URL", *(f"{fallback}DATABASE_URL" for fallback in fallback_prefixes)]
        for candidate in candidate_keys:
            raw_url = os.getenv(candidate)
            if raw_url:
                return cls.from_database_url(raw_url)
        return None

    @classmethod
    def from_database_url(cls, raw_url: str) -> "DatabaseConfig":
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise SyncError("DATABASE_URL precisa usar esquema postgres/postgresql")
        if not parsed.path or parsed.path == "/":
            raise SyncError("DATABASE_URL precisa incluir o nome do banco")

        query = parse_qs(parsed.query)
        sslmode_values = query.get("sslmode")

        return cls(
            name=unquote(parsed.path.lstrip("/")),
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname or "localhost",
            port=str(parsed.port or 5432),
            sslmode=sslmode_values[0] if sslmode_values else None,
        )

    def environment(self, *, maintenance_db: str | None = None, force_read_only: bool = False) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PGHOST": self.host,
                "PGPORT": self.port,
                "PGUSER": self.user,
                "PGPASSWORD": self.password,
                "PGDATABASE": maintenance_db or self.name,
            }
        )
        if self.sslmode:
            env["PGSSLMODE"] = self.sslmode
        if force_read_only:
            env["PGOPTIONS"] = "-c default_transaction_read_only=on"
        return env

    def safe_label(self) -> str:
        return f"{self.host}:{self.port}/{self.name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Faz dump da producao e recria o banco local com esse dump.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Arquivo .env carregado antes de ler variaveis locais. Default: .env",
    )
    parser.add_argument(
        "--prod-env-file",
        help="Arquivo .env opcional com as variaveis PROD_DB_* ou PROD_DATABASE_URL.",
    )
    parser.add_argument(
        "--dump-file",
        help="Caminho do dump .dump. Se omitido, usa um arquivo temporario.",
    )
    parser.add_argument(
        "--keep-dump",
        action="store_true",
        help="Mantem o arquivo dump ao final da execucao.",
    )
    parser.add_argument(
        "--local-maintenance-db",
        default=os.getenv("LOCAL_DB_MAINTENANCE_DB", "postgres"),
        help="Banco usado para dropar/recriar o banco local. Default: postgres",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma que o banco local pode ser apagado e recriado.",
    )
    return parser.parse_args()


def load_env_file(env_path: str | None) -> None:
    if not env_path:
        return

    path = Path(env_path)
    if not path.exists():
        raise SyncError(f"Arquivo de ambiente nao encontrado: {path}")

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def ensure_binaries() -> None:
    missing = [binary for binary in REQUIRED_BINARIES if shutil.which(binary) is None]
    if missing:
        raise SyncError("Comandos do PostgreSQL nao encontrados no PATH: " + ", ".join(missing))


def ensure_safe_targets(prod_config: DatabaseConfig, local_config: DatabaseConfig) -> None:
    if prod_config.safe_label() == local_config.safe_label():
        raise SyncError("Banco de producao e banco local apontam para o mesmo destino")


def run_command(command: list[str], *, env: dict[str, str], step: str) -> None:
    printable = shlex.join(command)
    print(f"\n[{step}] {printable}")
    try:
        subprocess.run(command, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        raise SyncError(f"Falha no passo '{step}' com codigo {exc.returncode}") from exc


def create_dump(prod_config: DatabaseConfig, dump_path: Path) -> None:
    run_command(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={dump_path}",
            prod_config.name,
        ],
        env=prod_config.environment(force_read_only=True),
        step="dump-producao",
    )


def recreate_local_database(local_config: DatabaseConfig, maintenance_db: str) -> None:
    admin_env = local_config.environment(maintenance_db=maintenance_db)
    run_command(
        ["dropdb", "--if-exists", "--force", local_config.name],
        env=admin_env,
        step="drop-local",
    )
    run_command(
        ["createdb", local_config.name],
        env=admin_env,
        step="create-local",
    )


def restore_dump(local_config: DatabaseConfig, dump_path: Path) -> None:
    run_command(
        [
            "pg_restore",
            "--no-owner",
            "--no-privileges",
            f"--dbname={local_config.name}",
            str(dump_path),
        ],
        env=local_config.environment(),
        step="restore-local",
    )


def build_dump_path(raw_path: str | None, keep_dump: bool) -> tuple[Path, bool]:
    if raw_path:
        return Path(raw_path).resolve(), True

    temp_file = tempfile.NamedTemporaryFile(prefix="prod-sync-", suffix=".dump", delete=False)
    temp_file.close()
    return Path(temp_file.name), keep_dump


def main() -> int:
    args = parse_args()

    if not args.yes:
        print("Abortado: use --yes para confirmar a recriacao destrutiva do banco local.", file=sys.stderr)
        return 2

    try:
        load_env_file(args.env_file)
        if args.prod_env_file:
            load_env_file(args.prod_env_file)

        ensure_binaries()

        prod_config = DatabaseConfig.from_env(prefix="PROD_")
        local_config = DatabaseConfig.from_env(prefix="LOCAL_", fallback_prefixes=("",))
        ensure_safe_targets(prod_config, local_config)

        dump_path, keep_dump = build_dump_path(args.dump_file, args.keep_dump)

        print(f"Origem (somente leitura): {prod_config.safe_label()}")
        print(f"Destino local: {local_config.safe_label()}")
        print(f"Arquivo dump: {dump_path}")

        create_dump(prod_config, dump_path)
        recreate_local_database(local_config, args.local_maintenance_db)
        restore_dump(local_config, dump_path)
        print("\nSincronizacao concluida com sucesso.")

        if keep_dump:
            print(f"Dump preservado em: {dump_path}")
        else:
            dump_path.unlink(missing_ok=True)
    except SyncError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
