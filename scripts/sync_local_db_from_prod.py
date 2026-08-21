from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, unquote, urlparse


REQUIRED_BINARIES = ("pg_dump", "dropdb", "createdb", "pg_restore")
FORWARDED_PG_ENV_VARS = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGSSLMODE", "PGOPTIONS")
LOCAL_DOCKER_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "postgres", "host.docker.internal"}
REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
POSTGRES_READY_ATTEMPTS = 30


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

    def for_docker_local(self) -> "DatabaseConfig":
        if self.host not in LOCAL_DOCKER_HOSTS:
            return self
        return DatabaseConfig(
            name=self.name,
            user=self.user,
            password=self.password,
            host="localhost",
            port="5432",
            sslmode=None,
        )


@dataclass(frozen=True, slots=True)
class PostgresCli:
    mode: Literal["docker", "host"]
    compose_command: tuple[str, ...] = ()
    service: str = "postgres"
    compose_cwd: Path | None = None

    def build_command(self, command: list[str], *, env: dict[str, str]) -> list[str]:
        if self.mode == "host":
            return command

        wrapped = [*self.compose_command, "exec", "-T"]
        for key in FORWARDED_PG_ENV_VARS:
            if env.get(key):
                wrapped.extend(["-e", key])
        wrapped.append(self.service)
        wrapped.extend(command)
        return wrapped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Faz dump da producao e recria o banco local com esse dump. Por padrao usa o cliente PostgreSQL do container Docker Compose, sem exigir Postgres instalado na maquina.",
        epilog="Exemplo: uv run python scripts/sync_local_db_from_prod.py --yes",
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
        "--docker",
        action="store_true",
        help="Forca o uso do cliente PostgreSQL do servico Docker Compose.",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Forca o uso dos binarios PostgreSQL instalados na maquina.",
    )
    parser.add_argument(
        "--docker-service",
        default=os.getenv("SYNC_DOCKER_POSTGRES_SERVICE", "postgres"),
        help="Nome do servico Postgres no docker compose. Default: postgres",
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


def missing_host_binaries() -> list[str]:
    return [binary for binary in REQUIRED_BINARIES if shutil.which(binary) is None]


def ensure_host_binaries() -> None:
    missing = missing_host_binaries()
    if missing:
        raise SyncError("Comandos do PostgreSQL nao encontrados no PATH: " + ", ".join(missing))


def detect_compose_command() -> tuple[str, ...]:
    docker = shutil.which("docker")
    if docker:
        probe = subprocess.run([docker, "compose", "version"], capture_output=True, text=True, timeout=20, check=False)
        if probe.returncode == 0:
            return (docker, "compose")

    compose_v1 = shutil.which("docker-compose")
    if compose_v1:
        return (compose_v1,)

    raise SyncError("Docker Compose nao encontrado no PATH. Instale o Docker Desktop ou o plugin compose.")


def compose_running_services(compose_command: tuple[str, ...], *, cwd: Path) -> set[str]:
    result = subprocess.run(
        [*compose_command, "ps", "--services", "--status", "running"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"codigo {result.returncode}"
        raise SyncError(f"Falha ao consultar o Docker Compose: {detail}")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def start_postgres_service(cli: PostgresCli) -> None:
    run_command(
        [*cli.compose_command, "up", "-d", cli.service],
        env=os.environ.copy(),
        step="docker-up-postgres",
        cwd=cli.compose_cwd,
    )


def wait_for_postgres(cli: PostgresCli) -> None:
    command = [*cli.compose_command, "exec", "-T", cli.service, "pg_isready", "-q"]
    for attempt in range(1, POSTGRES_READY_ATTEMPTS + 1):
        result = subprocess.run(command, cwd=cli.compose_cwd, capture_output=True, timeout=20, check=False)
        if result.returncode == 0:
            print("Postgres no Docker pronto.")
            return
        print(f"Aguardando Postgres no Docker ({attempt}/{POSTGRES_READY_ATTEMPTS})...")
        time.sleep(1)
    raise SyncError("Postgres no Docker nao ficou pronto. Verifique com: docker compose up -d postgres && docker compose ps")


def activate_docker_cli(*, service: str) -> PostgresCli:
    if not COMPOSE_FILE.exists():
        raise SyncError(f"docker-compose.yml nao encontrado em {COMPOSE_FILE}")

    compose_command = detect_compose_command()
    cli = PostgresCli(mode="docker", compose_command=compose_command, service=service, compose_cwd=REPO_ROOT)
    running = compose_running_services(compose_command, cwd=REPO_ROOT)
    if service not in running:
        print(f"Servico Docker '{service}' parado. Subindo com docker compose up -d {service}...")
        start_postgres_service(cli)
    wait_for_postgres(cli)
    return cli


def resolve_postgres_cli(*, use_docker: bool, use_host: bool, service: str) -> PostgresCli:
    if use_docker and use_host:
        raise SyncError("Use apenas --docker ou --no-docker, nao os dois.")

    if use_host:
        ensure_host_binaries()
        print("Usando cliente PostgreSQL instalado na maquina.")
        return PostgresCli(mode="host")

    docker_error: str | None = None
    try:
        cli = activate_docker_cli(service=service)
        print(f"Usando cliente PostgreSQL do Docker Compose (servico {service}).")
        return cli
    except SyncError as exc:
        docker_error = str(exc)
        if use_docker:
            raise

    missing = missing_host_binaries()
    if not missing:
        print(f"Docker indisponivel ({docker_error}); usando cliente PostgreSQL local.")
        return PostgresCli(mode="host")

    hints = [
        docker_error or "Docker indisponivel.",
        "Suba o Postgres do projeto com: docker compose up -d postgres",
        "Ou instale o cliente PostgreSQL local (pg_dump, dropdb, createdb, pg_restore) e use --no-docker.",
    ]
    raise SyncError(" ".join(hints))


def ensure_safe_targets(prod_config: DatabaseConfig, local_config: DatabaseConfig) -> None:
    if prod_config.safe_label() == local_config.safe_label():
        raise SyncError("Banco de producao e banco local apontam para o mesmo destino")


def run_command(
    command: list[str],
    *,
    env: dict[str, str],
    step: str,
    cwd: Path | None = None,
    stdin_path: Path | None = None,
    stdout_path: Path | None = None,
) -> None:
    printable = shlex.join(command)
    print(f"\n[{step}] {printable}")
    if stdin_path is not None:
        print(f"[{step}] stdin <- {stdin_path}")
    if stdout_path is not None:
        print(f"[{step}] stdout -> {stdout_path}")

    stdin_file = None
    stdout_file = None
    try:
        if stdin_path is not None:
            stdin_file = stdin_path.open("rb")
        if stdout_path is not None:
            stdout_file = stdout_path.open("wb")
        subprocess.run(
            command,
            env=env,
            check=True,
            cwd=cwd,
            stdin=stdin_file,
            stdout=stdout_file,
        )
    except subprocess.CalledProcessError as exc:
        raise SyncError(f"Falha no passo '{step}' com codigo {exc.returncode}") from exc
    finally:
        if stdin_file is not None:
            stdin_file.close()
        if stdout_file is not None:
            stdout_file.close()


def build_dump_invocation(cli: PostgresCli, prod_config: DatabaseConfig, dump_path: Path) -> tuple[list[str], dict[str, str], Path | None]:
    command = ["pg_dump", "--format=custom", "--no-owner", "--no-privileges"]
    stdout_path: Path | None = None
    if cli.mode == "docker":
        command.append("--file=-")
        stdout_path = dump_path
    else:
        command.append(f"--file={dump_path}")
    command.append(prod_config.name)
    env = prod_config.environment(force_read_only=True)
    return cli.build_command(command, env=env), env, stdout_path


def build_restore_invocation(cli: PostgresCli, local_config: DatabaseConfig, dump_path: Path) -> tuple[list[str], dict[str, str], Path | None]:
    command = ["pg_restore", "--no-owner", "--no-privileges", f"--dbname={local_config.name}"]
    stdin_path: Path | None = None
    if cli.mode == "docker":
        command.append("-")
        stdin_path = dump_path
    else:
        command.append(str(dump_path))
    env = local_config.environment()
    return cli.build_command(command, env=env), env, stdin_path


def create_dump(cli: PostgresCli, prod_config: DatabaseConfig, dump_path: Path) -> None:
    command, env, stdout_path = build_dump_invocation(cli, prod_config, dump_path)
    run_command(command, env=env, step="dump-producao", cwd=cli.compose_cwd, stdout_path=stdout_path)


def recreate_local_database(cli: PostgresCli, local_config: DatabaseConfig, maintenance_db: str) -> None:
    admin_env = local_config.environment(maintenance_db=maintenance_db)
    run_command(
        cli.build_command(["dropdb", "--if-exists", "--force", local_config.name], env=admin_env),
        env=admin_env,
        step="drop-local",
        cwd=cli.compose_cwd,
    )
    run_command(
        cli.build_command(["createdb", local_config.name], env=admin_env),
        env=admin_env,
        step="create-local",
        cwd=cli.compose_cwd,
    )


def restore_dump(cli: PostgresCli, local_config: DatabaseConfig, dump_path: Path) -> None:
    command, env, stdin_path = build_restore_invocation(cli, local_config, dump_path)
    run_command(command, env=env, step="restore-local", cwd=cli.compose_cwd, stdin_path=stdin_path)


def build_dump_path(raw_path: str | None, keep_dump: bool) -> tuple[Path, bool]:
    if raw_path:
        return Path(raw_path).resolve(), True

    temp_file = tempfile.NamedTemporaryFile(prefix="prod-sync-", suffix=".dump", delete=False)
    temp_file.close()
    return Path(temp_file.name), keep_dump


def local_config_for_cli(cli: PostgresCli, local_config: DatabaseConfig) -> DatabaseConfig:
    if cli.mode == "docker":
        return local_config.for_docker_local()
    return local_config


def main() -> int:
    args = parse_args()

    if not args.yes:
        print("Abortado: use --yes para confirmar a recriacao destrutiva do banco local.", file=sys.stderr)
        return 2

    try:
        load_env_file(args.env_file)
        if args.prod_env_file:
            load_env_file(args.prod_env_file)

        cli = resolve_postgres_cli(use_docker=args.docker, use_host=args.no_docker, service=args.docker_service)

        prod_config = DatabaseConfig.from_env(prefix="PROD_")
        local_config = local_config_for_cli(cli, DatabaseConfig.from_env(prefix="LOCAL_", fallback_prefixes=("",)))
        ensure_safe_targets(prod_config, local_config)

        dump_path, keep_dump = build_dump_path(args.dump_file, args.keep_dump)

        print(f"Origem (somente leitura): {prod_config.safe_label()}")
        print(f"Destino local: {local_config.safe_label()}")
        print(f"Arquivo dump: {dump_path}")

        create_dump(cli, prod_config, dump_path)
        recreate_local_database(cli, local_config, args.local_maintenance_db)
        restore_dump(cli, local_config, dump_path)
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
