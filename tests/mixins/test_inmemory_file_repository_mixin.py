def test_upload_file(inmemory_file_repository):
    reference = inmemory_file_repository.upload_file(
        data="data", content_type="text/plain"
    )
    assert inmemory_file_repository.files[reference] == "data"


def test_get_file(inmemory_file_repository):
    reference = inmemory_file_repository.upload_file(
        data="data", content_type="text/plain"
    )
    assert inmemory_file_repository.get_file(reference) == "data"


def test_delete_file(inmemory_file_repository):
    reference = inmemory_file_repository.upload_file(
        data="data", content_type="text/plain"
    )
    assert inmemory_file_repository.delete_file(reference)
    assert len(inmemory_file_repository.files) == 0


def test_delete_file_error(inmemory_file_repository):
    assert not inmemory_file_repository.delete_file("reference")
