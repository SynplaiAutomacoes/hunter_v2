from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase


def _load_sync_module():
    path = Path(__file__).resolve().parents[3] / "scripts" / "sync_local_db_from_prod.py"
    spec = importlib.util.spec_from_file_location("sync_local_db_from_prod", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sync = _load_sync_module()


def _docker_cli() -> object:
    return sync.PostgresCli(
        mode="docker",
        compose_command=("docker", "compose"),
        service="postgres",
        compose_cwd=sync.REPO_ROOT,
    )


def _host_cli() -> object:
    return sync.PostgresCli(mode="host")


def _db(*, name: str = "meu_crm", host: str = "localhost", port: str = "5432") -> object:
    return sync.DatabaseConfig(
        name=name,
        user="usuario_crm",
        password="senha_secreta",
        host=host,
        port=port,
    )


class PostgresCliDockerTests(SimpleTestCase):
    def test_docker_wrap_forwards_env_keys_without_inlining_password(self) -> None:
        env = {
            "PGHOST": "localhost",
            "PGPORT": "5432",
            "PGUSER": "usuario_crm",
            "PGPASSWORD": "senha-secreta",
            "PGDATABASE": "postgres",
        }
        command = _docker_cli().build_command(["dropdb", "--if-exists", "--force", "meu_crm"], env=env)

        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "-e",
                "PGHOST",
                "-e",
                "PGPORT",
                "-e",
                "PGUSER",
                "-e",
                "PGPASSWORD",
                "-e",
                "PGDATABASE",
                "postgres",
                "dropdb",
                "--if-exists",
                "--force",
                "meu_crm",
            ],
        )
        self.assertNotIn("senha-secreta", command)

    def test_host_mode_keeps_raw_command(self) -> None:
        command = _host_cli().build_command(["createdb", "meu_crm"], env={"PGUSER": "usuario_crm"})
        self.assertEqual(command, ["createdb", "meu_crm"])

    def test_docker_dump_writes_custom_format_to_stdout_file(self) -> None:
        dump_path = Path("/tmp/prod-sync.dump")
        command, _env, stdout_path = sync.build_dump_invocation(_docker_cli(), _db(name="railway", host="prod.example", port="15758"), dump_path)

        self.assertEqual(stdout_path, dump_path)
        self.assertIn("--file=-", command)
        self.assertEqual(command[-1], "railway")
        self.assertEqual(command[:4], ["docker", "compose", "exec", "-T"])

    def test_host_dump_writes_directly_to_file(self) -> None:
        dump_path = Path("/tmp/prod-sync.dump")
        command, _env, stdout_path = sync.build_dump_invocation(_host_cli(), _db(), dump_path)

        self.assertIsNone(stdout_path)
        self.assertEqual(command, ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", f"--file={dump_path}", "meu_crm"])

    def test_docker_restore_reads_dump_from_stdin(self) -> None:
        dump_path = Path("/tmp/prod-sync.dump")
        command, _env, stdin_path = sync.build_restore_invocation(_docker_cli(), _db(), dump_path)

        self.assertEqual(stdin_path, dump_path)
        self.assertEqual(command[-1], "-")
        self.assertIn("--dbname=meu_crm", command)

    def test_host_restore_passes_dump_path(self) -> None:
        dump_path = Path("/tmp/prod-sync.dump")
        command, _env, stdin_path = sync.build_restore_invocation(_host_cli(), _db(), dump_path)

        self.assertIsNone(stdin_path)
        self.assertEqual(command[-1], str(dump_path))


class LocalDockerConfigTests(SimpleTestCase):
    def test_remaps_host_published_port_to_container_localhost(self) -> None:
        remapped = _db(host="127.0.0.1", port="5433").for_docker_local()

        self.assertEqual(remapped.host, "localhost")
        self.assertEqual(remapped.port, "5432")
        self.assertIsNone(remapped.sslmode)

    def test_keeps_non_local_host(self) -> None:
        original = _db(host="db.internal", port="5432")
        self.assertEqual(original.for_docker_local(), original)

    def test_local_config_for_cli_only_remaps_in_docker_mode(self) -> None:
        local = _db(host="localhost", port="5433")
        self.assertEqual(sync.local_config_for_cli(_docker_cli(), local).port, "5432")
        self.assertEqual(sync.local_config_for_cli(_host_cli(), local).port, "5433")


class ResolvePostgresCliTests(SimpleTestCase):
    def test_no_docker_requires_host_binaries(self) -> None:
        with patch.object(sync.shutil, "which", return_value=None):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.resolve_postgres_cli(use_docker=False, use_host=True, service="postgres")
        self.assertIn("pg_dump", str(ctx.exception))

    def test_conflicting_flags_are_rejected(self) -> None:
        with self.assertRaises(sync.SyncError):
            sync.resolve_postgres_cli(use_docker=True, use_host=True, service="postgres")

    def test_prefers_running_docker_compose_service(self) -> None:
        cli = _docker_cli()
        with (
            patch.object(sync, "activate_docker_cli", return_value=cli) as activate,
            patch.object(sync.shutil, "which", return_value="/usr/bin/pg_dump"),
        ):
            resolved = sync.resolve_postgres_cli(use_docker=False, use_host=False, service="postgres")

        self.assertIs(resolved, cli)
        activate.assert_called_once_with(service="postgres")

    def test_falls_back_to_host_binaries_when_docker_fails(self) -> None:
        with (
            patch.object(sync, "activate_docker_cli", side_effect=sync.SyncError("daemon down")),
            patch.object(sync, "missing_host_binaries", return_value=[]),
        ):
            resolved = sync.resolve_postgres_cli(use_docker=False, use_host=False, service="postgres")

        self.assertEqual(resolved.mode, "host")

    def test_docker_flag_does_not_fall_back_to_host(self) -> None:
        with patch.object(sync, "activate_docker_cli", side_effect=sync.SyncError("daemon down")):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.resolve_postgres_cli(use_docker=True, use_host=False, service="postgres")
        self.assertIn("daemon down", str(ctx.exception))

    def test_errors_when_neither_docker_nor_host_client_is_available(self) -> None:
        with (
            patch.object(sync, "activate_docker_cli", side_effect=sync.SyncError("compose ausente")),
            patch.object(sync, "missing_host_binaries", return_value=["pg_dump", "pg_restore"]),
        ):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.resolve_postgres_cli(use_docker=False, use_host=False, service="postgres")
        message = str(ctx.exception)
        self.assertIn("docker compose up -d postgres", message)
        self.assertIn("--no-docker", message)


class ActivateDockerCliTests(SimpleTestCase):
    def test_starts_postgres_when_service_is_stopped(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with (
            patch.object(sync, "detect_compose_command", return_value=("docker", "compose")),
            patch.object(sync, "compose_running_services", return_value=set()),
            patch.object(sync, "start_postgres_service") as start,
            patch.object(sync, "wait_for_postgres") as wait,
            patch.object(sync.subprocess, "run", return_value=completed),
        ):
            cli = sync.activate_docker_cli(service="postgres")

        self.assertEqual(cli.mode, "docker")
        start.assert_called_once()
        wait.assert_called_once()

    def test_does_not_restart_already_running_service(self) -> None:
        with (
            patch.object(sync, "detect_compose_command", return_value=("docker", "compose")),
            patch.object(sync, "compose_running_services", return_value={"postgres"}),
            patch.object(sync, "start_postgres_service") as start,
            patch.object(sync, "wait_for_postgres") as wait,
        ):
            sync.activate_docker_cli(service="postgres")

        start.assert_not_called()
        wait.assert_called_once()
