from mockfirestore import CollectionReference  # type: ignore

from tests.fixtures import *  # NOQA

old_where = CollectionReference.where


def where(*args, **kwargs):
    if "filter" in kwargs:
        return old_where(
            args[0],
            field=kwargs["filter"].field_path,
            op=kwargs["filter"].op_string,
            value=kwargs["filter"].value,
        )
    return old_where(*args, **kwargs)


CollectionReference.where = where
