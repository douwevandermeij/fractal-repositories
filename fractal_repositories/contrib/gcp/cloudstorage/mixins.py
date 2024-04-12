import uuid

from google.cloud.storage import Client  # type: ignore

from fractal_repositories.core.repositories import EntityType, Repository


def get_cloudstorage_client(settings):
    if not hasattr(settings, "cloudstorage_client"):
        settings.cloudstorage_client = Client()
    return settings.cloudstorage_client


class CloudStorageRepositoryMixin(Repository[EntityType]):
    """
    https://github.com/googleapis/python-storage/tree/main/samples/snippets
    """

    entity: EntityType

    def __init__(
        self,
        settings,
        collection: str = "",
        collection_prefix: str = "",
        *args,
        **kwargs,
    ):
        super(CloudStorageRepositoryMixin, self).__init__(*args, **kwargs)

        client = get_cloudstorage_client(settings)
        if not collection and self.entity:
            collection = self.entity.__name__  # type: ignore
        if collection_prefix:
            collection = "-".join([collection_prefix, collection])
        self.bucket = client.bucket(collection.lower().replace(" ", "-"))

    def upload_file(self, data: bytes, content_type: str, reference: str = "") -> str:
        # https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_upload_from_memory.py
        if not reference:
            reference = str(uuid.uuid4())
        blob = self.bucket.blob(reference)
        blob.upload_from_string(data, content_type=content_type)
        return reference

    def get_file(self, reference: str) -> bytes:
        # https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_download_into_memory.py
        blob = self.bucket.blob(reference)
        return blob.download_as_string()

    def delete_file(self, reference: str) -> bool:
        # https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_delete_file.py
        blob = self.bucket.blob(reference)
        blob.delete()
        return True

    # def get_upload_url(self, reference: str) -> str:
    #     # https://cloud.google.com/storage/docs/access-control/signing-urls-with-helpers#storage-signed-url-object-python
    #     blob = self.bucket.blob(reference)
    #
    #     return blob.generate_signed_url(
    #         version="v4",
    #         # This URL is valid for 15 minutes
    #         expiration=datetime.timedelta(minutes=15),
    #         # Allow PUT requests using this URL.
    #         method="PUT",
    #         content_type="application/octet-stream",
    #     )
