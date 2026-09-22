"""The compare-and-swap contract, asserted identically against every backend
that claims to honour it.

The case that matters is the one `update` cannot express: two callers read the
same row, both change it, both write it back. Under `update` the second wins and
the first is erased without a word. Under `compare_and_swap` the second is told
it lost, and the row still holds what the winner put there.
"""

import pytest
from fractal_specifications.generic.specification import Specification

from tests.fixtures.repositories import AnObject

BACKENDS = ["inmemory_repository", "file_repository_on_disk", "sqlite_repository"]


@pytest.fixture(params=BACKENDS)
def repository(request):
    return request.getfixturevalue(request.param)


def test_backend_declares_support(repository):
    assert repository.supports_compare_and_swap is True


def test_swaps_while_the_expectation_holds(repository):
    repository.add(AnObject("1", "first"))

    swapped = repository.compare_and_swap(
        AnObject("1", "second"), expected=Specification.parse(name="first")
    )

    assert swapped is True
    assert repository.find_one(Specification.parse(id="1")).name == "second"


def test_refuses_once_the_row_has_moved_on(repository):
    repository.add(AnObject("1", "first"))
    # Both callers read "first". The winner gets there first.
    repository.compare_and_swap(
        AnObject("1", "winner"), expected=Specification.parse(name="first")
    )

    swapped = repository.compare_and_swap(
        AnObject("1", "loser"), expected=Specification.parse(name="first")
    )

    assert swapped is False
    # The point of all this: the winner's value is still standing.
    assert repository.find_one(Specification.parse(id="1")).name == "winner"


def test_refuses_a_row_that_is_not_there(repository):
    assert (
        repository.compare_and_swap(
            AnObject("nope", "x"), expected=Specification.parse(name="whatever")
        )
        is False
    )


def test_a_swap_that_changes_nothing_still_counts_as_won(repository):
    """Writing back an identical row is a swap this caller won.

    Mongo would report zero documents modified here; the caller still beat
    everyone else to the row, which is what it asked.
    """
    repository.add(AnObject("1", "same"))

    assert (
        repository.compare_and_swap(
            AnObject("1", "same"), expected=Specification.parse(name="same")
        )
        is True
    )


def test_a_backend_without_support_says_so_rather_than_guessing():
    from fractal_repositories.core.repositories import Repository

    class Unsupported(Repository[AnObject]):
        entity = AnObject

        def add(self, entity): ...
        def update(self, entity, *, upsert=False): ...
        def remove_one(self, specification): ...
        def find_one(self, specification): ...
        def find(self, specification=None, *, offset=0, limit=0, order_by=""): ...
        def count(self, specification=None): ...
        def is_healthy(self): ...

    repository = Unsupported()

    assert repository.supports_compare_and_swap is False
    with pytest.raises(NotImplementedError, match="compare_and_swap"):
        repository.compare_and_swap(
            AnObject("1"), expected=Specification.parse(name="x")
        )
