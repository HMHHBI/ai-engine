from __future__ import annotations

import io
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from app.storage.base import StorageBackend


class R2StorageBackend(StorageBackend):
    """
    Cloudflare R2 implementation using the S3-compatible API.
    """

    def __init__(self) -> None:
        required = {
            "R2_ACCOUNT_ID": settings.R2_ACCOUNT_ID,
            "R2_ACCESS_KEY_ID": settings.R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": settings.R2_SECRET_ACCESS_KEY,
            "R2_BUCKET_NAME": settings.R2_BUCKET_NAME,
        }

        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "R2 storage is enabled but required configuration is missing: "
                + ", ".join(missing)
            )

        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
        self.bucket_name = settings.R2_BUCKET_NAME

    def save(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str,
    ) -> str:
        self.client.upload_fileobj(
            stream,
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    def get_stream(
        self,
        key: str,
    ) -> BinaryIO:
        response = self.client.get_object(
            Bucket=self.bucket_name,
            Key=key,
        )
        # Genuinely stream body without buffering full file into RAM
        return response["Body"]

    def delete(
        self,
        key: str,
    ) -> None:
        self.client.delete_object(
            Bucket=self.bucket_name,
            Key=key,
        )

    def exists(
        self,
        key: str,
    ) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
