"""MinIO observability without coupling ingestion to object storage internals."""

import urllib3
from minio import Minio

from ulpf.config import Settings, settings


class MinioService:
    def __init__(self, config: Settings = settings):
        self.config = config
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=2.0, read=3.0),
            retries=False,
        )
        self.client = Minio(
            config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=False,
            http_client=http_client,
        )

    def status(self) -> dict:
        try:
            exists = self.client.bucket_exists(self.config.minio_bucket)
            return {
                "ready": exists,
                "error": "" if exists else "Warehouse bucket is missing",
            }
        except Exception as exc:
            return {"ready": False, "error": str(exc)}
