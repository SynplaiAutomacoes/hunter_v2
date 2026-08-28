from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sync_local_db_from_prod import (
    DatabaseConfig,
    DockerExecPostgresRunner,
    DockerRunPostgresRunner,
    HostPostgresRunner,
    _docker_run_env,
    _replace_path_argument,
    find_local_postgres_container,
    host_postgres_tools_available,
    resolve_postgres_runner,
)


class SyncLocalDbRunnerTests(unittest.TestCase):
    def test_docker_run_env_rewrites_local_host(self) -> None:
        env = {"PGHOST": "localhost", "PGPORT": "5432", "PGUSER": "usuario"}

        adjusted = _docker_run_env(env)

        self.assertEqual(adjusted["PGHOST"], "host.docker.internal")
        self.assertEqual(adjusted["PGUSER"], "usuario")

    def test_replace_path_argument_updates_dump_file(self) -> None:
        source = Path("/tmp/prod-sync-abc.dump")
        container = Path("/tmp/sync-local-db-prod-sync-abc.dump")

        self.assertEqual(
            _replace_path_argument(f"--file={source}", source, container),
            f"--file={container}",
        )
        self.assertEqual(_replace_path_argument(str(source), source, container), str(container))

    @patch("scripts.sync_local_db_from_prod.host_postgres_tools_available", return_value=False)
    @patch("scripts.sync_local_db_from_prod.docker_available", return_value=True)
    @patch("scripts.sync_local_db_from_prod.find_local_postgres_container", return_value="postgres-container")
    def test_resolve_runner_uses_docker_exec_for_local_target(
        self,
        _find_container: object,
        _docker: object,
        _host_tools: object,
    ) -> None:
        config = DatabaseConfig(
            name="meu_crm",
            user="usuario_crm",
            password="secret",
            host="localhost",
            port="5432",
        )

        runner = resolve_postgres_runner(target=config, root=Path("/project"))

        self.assertIsInstance(runner, DockerExecPostgresRunner)
        self.assertEqual(runner.container_id, "postgres-container")

    @patch("scripts.sync_local_db_from_prod.host_postgres_tools_available", return_value=False)
    @patch("scripts.sync_local_db_from_prod.docker_available", return_value=True)
    @patch("scripts.sync_local_db_from_prod.find_local_postgres_container", return_value=None)
    def test_resolve_runner_uses_docker_run_for_remote_target(
        self,
        _find_container: object,
        _docker: object,
        _host_tools: object,
    ) -> None:
        config = DatabaseConfig(
            name="prod_db",
            user="prod_user",
            password="secret",
            host="db.example.com",
            port="5432",
        )

        runner = resolve_postgres_runner(target=config, root=Path("/project"))

        self.assertIsInstance(runner, DockerRunPostgresRunner)

    @patch("scripts.sync_local_db_from_prod.host_postgres_tools_available", return_value=True)
    def test_resolve_runner_uses_host_when_tools_available(self, _host_tools: object) -> None:
        config = DatabaseConfig(
            name="meu_crm",
            user="usuario_crm",
            password="secret",
            host="localhost",
            port="5432",
        )

        runner = resolve_postgres_runner(target=config, root=Path("/project"))

        self.assertIsInstance(runner, HostPostgresRunner)

    @patch.dict(os.environ, {"LOCAL_POSTGRES_DOCKER_CONTAINER": "custom-postgres"}, clear=False)
    def test_find_local_postgres_container_honors_env_override(self) -> None:
        container = find_local_postgres_container(root=Path("/project"))

        self.assertEqual(container, "custom-postgres")

    def test_host_postgres_tools_available_reflects_path(self) -> None:
        self.assertIsInstance(host_postgres_tools_available(), bool)


if __name__ == "__main__":
    unittest.main()
