def test_upload_get_file(file_file_repository, mocker_file_open_data):
    reference = file_file_repository.upload_file(data="data", content_type="text/plain")
    mocker_file_open_data("data")
    assert file_file_repository.get_file(reference) == "data"


def test_delete_file(file_file_repository, mocker_os_remove):
    reference = file_file_repository.upload_file(data="data", content_type="text/plain")
    assert file_file_repository.delete_file(reference)


def test_delete_file_error(file_file_repository, mocker_os_remove_error):
    assert not file_file_repository.delete_file("reference")
