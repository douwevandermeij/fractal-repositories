import os


def test_upload_file(cloudstorage_test_repository):
    reference = cloudstorage_test_repository.upload_file(
        data="data", content_type="text/plain"
    )
    assert cloudstorage_test_repository.get_file(reference).decode() == "data"
    os.remove(reference)  # clean up local file


def test_get_file(cloudstorage_test_repository):
    reference = cloudstorage_test_repository.upload_file(
        data="data", content_type="text/plain"
    )
    assert cloudstorage_test_repository.get_file(reference).decode() == "data"
    os.remove(reference)  # clean up local file


def test_delete_file(cloudstorage_test_repository):
    reference = cloudstorage_test_repository.upload_file(
        data="data", content_type="text/plain"
    )
    os.remove(reference)  # clean up local file
    # assert cloudstorage_test_repository.delete_file(reference)  TODO delete doesn't work on mock library (yet)


def test_delete_file_error(cloudstorage_test_repository):
    ...
    # assert not cloudstorage_test_repository.delete_file("reference")  TODO delete doesn't work on mock library (yet)
