import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

from app.config import get_settings

settings = get_settings()


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: BinaryIO, content_type: str) -> None: ...

    @abstractmethod
    def read(self, key: str) -> Optional[BinaryIO]: ...

    @abstractmethod
    def read_range(self, key: str, start: int, end: int) -> bytes: ...

    @abstractmethod
    def iter_read(self, key: str, start: int = 0, length: Optional[int] = None) -> Iterator[bytes]: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def public_url(self, key: str) -> str: ...


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
            raise ValueError("invalid storage key")
        return resolved

    def save(self, key: str, data: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            shutil.copyfileobj(data, fh)

    def read(self, key: str) -> Optional[BinaryIO]:
        path = self._path(key)
        return open(path, "rb") if path.exists() else None

    def read_range(self, key: str, start: int, end: int) -> bytes:
        path = self._path(key)
        if not path.exists():
            return b""
        with open(path, "rb") as fh:
            fh.seek(start)
            return fh.read(end - start + 1)

    def iter_read(self, key: str, start: int = 0, length: Optional[int] = None) -> Iterator[bytes]:
        path = self._path(key)
        if not path.exists():
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length if length is not None else -1
            while remaining != 0:
                chunk_size = 1024 * 1024 if remaining < 0 else min(1024 * 1024, remaining)
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def size(self, key: str) -> int:
        path = self._path(key)
        return path.stat().st_size if path.exists() else 0

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def public_url(self, key: str) -> str:
        return f"/media/{key}"


class AzureBlobStorageBackend(StorageBackend):
    def __init__(self, connection_string: str, container: str) -> None:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise RuntimeError(
                "Azure Blob storage selected but 'azure-storage-blob' is not installed. "
                "Run: pip install azure-storage-blob"
            ) from exc
        self.container = container
        self.service = BlobServiceClient.from_connection_string(connection_string)
        self.service.create_container(name=container)

    def save(self, key: str, data: BinaryIO, content_type: str) -> None:
        client = self.service.get_blob_client(container=self.container, blob=key)
        client.upload_blob(data, overwrite=True)

    def read(self, key: str) -> Optional[BinaryIO]:
        client = self.service.get_blob_client(container=self.container, blob=key)
        if not client.exists():
            return None
        return client.download_blob()

    def read_range(self, key: str, start: int, end: int) -> bytes:
        client = self.service.get_blob_client(container=self.container, blob=key)
        return client.download_blob(offset=start, length=end - start + 1).readall()

    def iter_read(self, key: str, start: int = 0, length: Optional[int] = None) -> Iterator[bytes]:
        client = self.service.get_blob_client(container=self.container, blob=key)
        downloader = client.download_blob(offset=start, length=length)
        yield from downloader.chunks()

    def size(self, key: str) -> int:
        client = self.service.get_blob_client(container=self.container, blob=key)
        props = client.get_blob_properties() if client.exists() else None
        return props.size if props else 0

    def delete(self, key: str) -> None:
        client = self.service.get_blob_client(container=self.container, blob=key)
        client.delete_blob()

    def public_url(self, key: str) -> str:
        return f"https://{self.service.account_name}.blob.core.windows.net/{self.container}/{key}"


class S3StorageBackend(StorageBackend):
    def __init__(self, bucket: str, region: str) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("S3 storage selected but 'boto3' is not installed. Run: pip install boto3") from exc
        self.bucket = bucket
        self.region = region
        self.client = boto3.client("s3", region_name=region)

    def save(self, key: str, data: BinaryIO, content_type: str) -> None:
        self.client.upload_fileobj(data, self.bucket, key, ExtraArgs={"ContentType": content_type})

    def read(self, key: str) -> Optional[BinaryIO]:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except Exception:
            return None

    def read_range(self, key: str, start: int, end: int) -> bytes:
        body = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")["Body"]
        return body.read()

    def iter_read(self, key: str, start: int = 0, length: Optional[int] = None) -> Iterator[bytes]:
        end = (start + length - 1) if length is not None else ""
        body = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")["Body"]
        yield from body.iter_chunks(chunk_size=1024 * 1024)

    def size(self, key: str) -> int:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except Exception:
            return 0

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def public_url(self, key: str) -> str:
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"


def get_storage_backend() -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalStorageBackend(settings.media_root)
    if settings.storage_backend == "azure":
        return AzureBlobStorageBackend(
            settings.azure_connection_string,
            settings.azure_container,
        )
    if settings.storage_backend == "s3":
        return S3StorageBackend(settings.s3_bucket, settings.s3_region)
    raise ValueError(f"Unknown storage backend: {settings.storage_backend}")


def materialise_local_path(backend: StorageBackend, key: str) -> Optional[Path]:
    if isinstance(backend, LocalStorageBackend):
        path = backend._path(key)
        return path if path.exists() else None
    data = backend.read(key)
    if data is None:
        return None
    fd, name = tempfile.mkstemp(suffix=".video")
    with os.fdopen(fd, "wb") as fh:
        shutil.copyfileobj(data, fh)
    return Path(name)
