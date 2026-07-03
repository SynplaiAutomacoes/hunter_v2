from __future__ import annotations

import logging
import unicodedata
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from apps.core.domain.contracts.storage import IStorageService, StorageConfigurationError, StorageObject, StorageServiceError
from apps.core.observability import observe_dependency_call

logger = logging.getLogger(__name__)


def _to_ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


class S3StorageService(IStorageService):
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

    def upload_file(self, file: bytes, key: str, *, content_type: str = "application/octet-stream", metadata: dict[str, str] | None = None) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise StorageServiceError("Chave invalida para upload no bucket.")
        safe_metadata = {str(k): _to_ascii(str(v)) for k, v in (metadata or {}).items()}
        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="storage",
                dependency_name="s3",
                operation="upload_file",
                log_context={"bucket": self.bucket, "key": normalized_key},
            ) as dependency_call:
                dependency_call.set_attribute("storage.bucket", self.bucket)
                dependency_call.set_attribute("storage.key", normalized_key)
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=normalized_key,
                    Body=file,
                    ContentType=str(content_type or "application/octet-stream"),
                    Metadata=safe_metadata,
                )
                dependency_call.success(extra={"bucket": self.bucket, "key": normalized_key, "content_type": str(content_type or "application/octet-stream")})
        except (BotoCoreError, ClientError) as exc:
            raise StorageServiceError(f"Falha ao enviar arquivo para o bucket configurado: {exc}") from exc

    def read_file(self, key: str) -> StorageObject:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise StorageServiceError("Chave invalida para leitura no bucket.")
        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="storage",
                dependency_name="s3",
                operation="read_file",
                log_context={"bucket": self.bucket, "key": normalized_key},
            ) as dependency_call:
                dependency_call.set_attribute("storage.bucket", self.bucket)
                dependency_call.set_attribute("storage.key", normalized_key)
                response = self.client.get_object(Bucket=self.bucket, Key=normalized_key)
                body = response["Body"].read()
                dependency_call.success(extra={"bucket": self.bucket, "key": normalized_key, "content_length": len(body)})
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise StorageServiceError("Falha ao ler arquivo do bucket configurado.") from exc
        raw_metadata = response.get("Metadata") or {}
        metadata = {str(k): str(v) for k, v in raw_metadata.items()}
        content_type = str(response.get("ContentType") or "application/octet-stream")
        return StorageObject(key=normalized_key, content=body, content_type=content_type, metadata=metadata)

    def delete_file(self, key: str) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return
        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="storage",
                dependency_name="s3",
                operation="delete_file",
                log_context={"bucket": self.bucket, "key": normalized_key},
            ) as dependency_call:
                dependency_call.set_attribute("storage.bucket", self.bucket)
                dependency_call.set_attribute("storage.key", normalized_key)
                self.client.delete_object(Bucket=self.bucket, Key=normalized_key)
                dependency_call.success(extra={"bucket": self.bucket, "key": normalized_key})
        except (BotoCoreError, ClientError) as exc:
            raise StorageServiceError("Falha ao remover arquivo do bucket configurado.") from exc

    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise StorageServiceError("Chave invalida para gerar URL assinada.")
        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="storage",
                dependency_name="s3",
                operation="generate_presigned_url",
                log_context={"bucket": self.bucket, "key": normalized_key},
            ) as dependency_call:
                dependency_call.set_attribute("storage.bucket", self.bucket)
                dependency_call.set_attribute("storage.key", normalized_key)
                dependency_call.set_attribute("app.expires_in", expires_in)
                presigned_url = str(
                    self.client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self.bucket, "Key": normalized_key},
                        ExpiresIn=expires_in,
                    )
                )
                dependency_call.success(extra={"bucket": self.bucket, "key": normalized_key, "expires_in": expires_in})
                return presigned_url
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
