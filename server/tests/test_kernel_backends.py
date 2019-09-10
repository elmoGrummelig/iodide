import pytest

from server.kernels.remote.backends import Backend, get_backend, registry
from server.kernels.remote.exceptions import BackendError
from server.kernels.remote.models import RemoteFile, RemoteOperation
from server.kernels.remote.query.backends import QueryBackend

TEST_CHUNK = """
data_source = telemetry
output_name = result
filename = user_count_query.json
-----
select count(*) from telemetry.users
"""


class FailureTestBackend(Backend):
    pass


class PassingTestBackend(QueryBackend):
    token = "test"

    def execute_operation(self, *args, **kwargs):
        return b"result!"


@pytest.fixture
def remote_backend():
    registry.register(PassingTestBackend)
    return PassingTestBackend()


@pytest.fixture
def remote_operation(remote_backend, test_notebook):
    return RemoteOperation.objects.create(
        notebook=test_notebook,
        filename="test.ioresult",
        backend="test",
        parameters={},
        snippet="SELECT 1;",
    )


@pytest.fixture
def two_remote_operations(remote_backend, test_notebook):
    for x in range(2, 1):
        return RemoteOperation.objects.create(
            notebook=test_notebook,
            filename=f"test{x}.ioresult",
            backend="test",
            parameters={},
            snippet="SELECT 1;",
        )


@pytest.fixture
def remote_file(remote_operation):
    return RemoteFile.objects.create(
        notebook=remote_operation.notebook,
        filename=remote_operation.filename,
        operation=remote_operation,
    )


def test_missing_abstractmethods_errors():
    with pytest.raises(TypeError):
        FailureTestBackend()


def test_passing_init():
    assert PassingTestBackend()


def test_get_backend_success():
    assert isinstance(get_backend("query"), Backend)


def test_get_backend_failure():
    with pytest.raises(BackendError):
        get_backend("non-existing")


def test_build_filename(remote_backend, test_notebook):
    assert (
        remote_backend.build_filename(test_notebook, "a chunk")
        == "74cb59e4cec5989f9651e974223ee773.ioresult"
    )


def test_split_chunk(remote_backend):
    assert remote_backend.split_chunk(TEST_CHUNK) == [
        """
data_source = telemetry
output_name = result
filename = user_count_query.json
""",
        "select count(*) from telemetry.users",
    ]


def test_create_operation(remote_backend, test_notebook):
    operation = remote_backend.create_operation(test_notebook)
    assert isinstance(operation, RemoteOperation)
    assert operation.status == operation.STATUS_PENDING
    assert operation.parameters == {}
    assert str(operation) == str(operation.pk)


def test_save_result_remote_file_new(remote_backend, remote_operation):
    remote_file = remote_backend.save_result(
        remote_operation,
        b"""
        {
            "objects": [
                {"spam": 1, "eggs": 2},
                {"foo": 3, "bar": 4}
            ]
        }
        """,
    )
    assert remote_file.operation == remote_operation
    assert RemoteFile.objects.count() == 1


def test_save_result_remote_file_exists(remote_backend, remote_operation, remote_file):
    # doesn't create another remote file but just updates the one
    remote_file_2 = remote_backend.save_result(remote_operation, b"something entirely different")
    assert remote_file.operation == remote_operation
    assert remote_file == remote_file_2
    assert RemoteFile.objects.count() == 1


def test_refresh_file(remote_backend, remote_file):
    assert RemoteFile.objects.count() == 1
    assert RemoteOperation.objects.count() == 1
    new_operation = remote_backend.refresh_file(remote_file)
    assert RemoteFile.objects.count() == 1
    assert RemoteOperation.objects.count() == 2
    assert isinstance(new_operation, RemoteOperation)
    assert new_operation.notebook == remote_file.notebook