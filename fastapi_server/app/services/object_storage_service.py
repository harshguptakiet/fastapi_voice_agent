from __future__ import annotations

from pathlib import Path

from app.core import config


class ObjectStorageService:
    def __init__(self) -> None:
        self.provider = (config.OBJECT_STORAGE_PROVIDER or "local").strip().lower()
        self.base_dir = Path(config.LOCAL_DOCUMENT_STORAGE_DIR)
        self.raw_dir = self.base_dir / "raw"
        self.text_dir = self.base_dir / "text"

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)

        self._s3_client = None
        self._s3_bucket = config.OBJECT_STORAGE_BUCKET
        if self.provider == "s3":
            self._init_s3_client()

    def _init_s3_client(self) -> None:
        try:
            import boto3  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "OBJECT_STORAGE_PROVIDER=s3 requires boto3 package"
            ) from exc

        if not self._s3_bucket:
            raise RuntimeError("OBJECT_STORAGE_BUCKET is required when using s3 storage")

        self._s3_client = boto3.client(
            "s3",
            region_name=config.OBJECT_STORAGE_REGION or None,
            endpoint_url=config.OBJECT_STORAGE_ENDPOINT_URL or None,
            aws_access_key_id=config.OBJECT_STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=config.OBJECT_STORAGE_SECRET_KEY or None,
        )

    def save_raw(self, file_name: str, content: bytes) -> str:
        if self.provider == "s3" and self._s3_client:
            key = f"raw/{file_name}"
            self._s3_client.put_object(Bucket=self._s3_bucket, Key=key, Body=content)
            return f"s3://{self._s3_bucket}/{key}"

        file_path = self.raw_dir / file_name
        file_path.write_bytes(content)
        return str(file_path)

    def save_text(self, text_file_name: str, text: str) -> str:
        text_bytes = text.encode("utf-8")
        if self.provider == "s3" and self._s3_client:
            key = f"text/{text_file_name}"
            self._s3_client.put_object(Bucket=self._s3_bucket, Key=key, Body=text_bytes)
            return f"s3://{self._s3_bucket}/{key}"

        text_file_path = self.text_dir / text_file_name
        text_file_path.write_text(text, encoding="utf-8")
        return str(text_file_path)

    def list_text_documents(self) -> list[str]:
        if self.provider == "s3" and self._s3_client:
            response = self._s3_client.list_objects_v2(Bucket=self._s3_bucket, Prefix="text/")
            out: list[str] = []
            for item in response.get("Contents", []):
                key = item.get("Key")
                if not key or not key.endswith(".txt"):
                    continue
                out.append(Path(key).stem)
            return sorted(out)

        return sorted([f.stem for f in self.text_dir.glob("*.txt")])


object_storage = ObjectStorageService()
