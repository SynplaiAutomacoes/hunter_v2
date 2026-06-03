from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from django.conf import settings

logger = logging.getLogger(__name__)


class StorageConfigurationError(Exception):
    pass


class StorageServiceError(Exception):
    pass


@dataclass(frozen=True)
class StorageObject:
    key: str
    content: bytes
    content_type: str
    metadata: dict[str, str]


def _to_ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


class S3StorageService:
    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        endpoint: str,
        region: str,
    ) -> None:
        normalized_access_key = str(access_key_id or "").strip()
        normalized_secret_key = str(secret_access_key or "").strip()
        normalized_bucket = str(bucket or "").strip()
        normalized_endpoint = str(endpoint or "").strip()
        normalized_region = str(region or "").strip() or "auto"

        missing_settings = [
            setting_name
            for setting_name, value in (
                ("ACCESS_KEY_ID", normalized_access_key),
                ("SECRET_ACCESS_KEY", normalized_secret_key),
                ("BUCKET", normalized_bucket),
                ("ENDPOINT", normalized_endpoint),
            )
            if not value
        ]
        if missing_settings:
            missing_display = ", ".join(missing_settings)
            raise StorageConfigurationError(f"Configure as variaveis {missing_display} para usar o bucket S3.")

        self.bucket = normalized_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=normalized_endpoint,
            aws_access_key_id=normalized_access_key,
            aws_secret_access_key=normalized_secret_key,
            region_name=normalized_region,
        )

    def upload_file(
        self,
        file: bytes,
        key: str,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise StorageServiceError("Chave invalida para upload no bucket.")

        safe_metadata = {str(k): _to_ascii(str(v)) for k, v in (metadata or {}).items()}

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=normalized_key,
                Body=file,
                ContentType=str(content_type or "application/octet-stream"),
                Metadata=safe_metadata,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("S3 put_object failed for key=%s", normalized_key)
            raise StorageServiceError(f"Falha ao enviar arquivo para o bucket configurado: {exc}") from exc

    def read_file(self, key: str) -> StorageObject:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise StorageServiceError("Chave invalida para leitura no bucket.")

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=normalized_key)
            body = response["Body"].read()
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise StorageServiceError("Falha ao ler arquivo do bucket configurado.") from exc

        raw_metadata = response.get("Metadata") or {}
        metadata = {str(k): str(v) for k, v in raw_metadata.items()}
        content_type = str(response.get("ContentType") or "application/octet-stream")
        return StorageObject(
            key=normalized_key,
            content=body,
            content_type=content_type,
            metadata=metadata,
        )

    def delete_file(self, key: str) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return

        try:
            self.client.delete_object(Bucket=self.bucket, Key=normalized_key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageServiceError("Falha ao remover arquivo do bucket configurado.") from exc

    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise StorageServiceError("Chave invalida para gerar URL assinada.")

        try:
            return str(
                self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": normalized_key},
                    ExpiresIn=expires_in,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageServiceError("Falha ao gerar URL assinada para o bucket configurado.") from exc


@lru_cache(maxsize=1)
def get_storage_service() -> S3StorageService:
    return S3StorageService(
        access_key_id=str(getattr(settings, "STORAGE_ACCESS_KEY_ID", "") or ""),
        secret_access_key=str(getattr(settings, "STORAGE_SECRET_ACCESS_KEY", "") or ""),
        bucket=str(getattr(settings, "STORAGE_BUCKET", "") or ""),
        endpoint=str(getattr(settings, "STORAGE_ENDPOINT", "") or ""),
        region=str(getattr(settings, "STORAGE_REGION", "auto") or "auto"),
    )
