def test_filter(inmemory_filter_repository, an_object, another_object):
    inmemory_filter_repository.add(an_object)
    inmemory_filter_repository.add(another_object)

    from fractal_specifications.generic.specification import (
        EmptySpecification,
        Specification,
    )

    assert len(list(inmemory_filter_repository.find_filter(EmptySpecification()))) == 2
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="default_name")
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="default")
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="name")
                )
            )
        )
        == 2
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="t_n")
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="_")
                )
            )
        )
        == 2
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="x")
                )
            )
        )
        == 0
    )


def test_filter_specification(inmemory_filter_repository, an_object, another_object):
    inmemory_filter_repository.add(an_object)
    inmemory_filter_repository.add(another_object)

    from fractal_specifications.generic.specification import Specification

    specification = Specification.parse(id="1")

    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="_"), specification=specification
                )
            )
        )
        == 1
    )


def test_filter_pre_processor(inmemory_filter_repository, an_object):
    an_object.name = an_object.name.upper()

    inmemory_filter_repository.add(an_object)

    from fractal_specifications.generic.specification import Specification

    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="default_name")
                )
            )
        )
        == 0
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="DEFAULT_NAME")
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="default_name"),
                    pre_processor=lambda e: setattr(e, "name", e.name.lower()) or e,
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                inmemory_filter_repository.find_filter(
                    Specification.parse(name__contains="default_name")
                )
            )
        )
        == 0
    )
