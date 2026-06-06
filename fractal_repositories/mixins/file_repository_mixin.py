import json
import logging
import os
import tempfile
import uuid
from typing import Iterator

from fractal_specifications.generic.operators import NotSpecification
from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.repositories import EntityType, FileRepository
from fractal_repositories.exceptions import ObjectNotFoundException
from fractal_repositories.mixins.inmemory_repository_mixin import (
    InMemoryRepositoryMixin,
)
from fractal_repositories.utils.json_encoder import EnhancedEncoder

logger = logging.getLogger(__name__)


class RootDirMixin(object):
    def __init__(self, *, root_dir: str, **kwargs):
        super(RootDirMixin, self).__init__(**kwargs)

        self.root_dir = root_dir


class FileRepositoryMixin(RootDirMixin, InMemoryRepositoryMixin[EntityType]):
    """File-backed repository that survives corrupt data.

    Reader: skips empty lines, null bytes, and JSON that does not deserialize
    into an entity instead of crashing. Appends keep each entry on exactly one
    line, so a torn write (process killed mid-append) only ever produces a
    single malformed trailing line, which the reader skips. Rewrites (deletes
    and updates) go through an atomic temp-file-plus-rename so a crash leaves
    either the old complete file or the new one, never a truncated table.

    Single-writer only: there is no file locking, so two processes writing
    concurrently can still clobber each other on the rewrite path.
    """

    # Deserialization errors that mean "this line is corrupt/stale data" rather
    # than "from_dict has a bug": malformed JSON, JSON that is not a mapping, or
    # an object missing required fields. Anything else propagates loudly so a
    # genuine bug can't silently delete every row from every read.
    _CORRUPT_LINE_ERRORS = (json.JSONDecodeError, TypeError, ValueError)

    @property
    def _filename(self) -> str:
        return os.path.join(self.root_dir, "db", f"{self.__class__.__name__}.jsonl")

    @property
    def _get_entities(self) -> Iterator[EntityType]:
        if not os.path.exists(self._filename):
            os.makedirs(os.path.dirname(self._filename), exist_ok=True)
            open(self._filename, "a").close()
        with open(self._filename, "r", encoding="utf-8") as fp:
            for line_number, line in enumerate(fp, start=1):
                raw = line.strip().replace("\x00", "")
                if not raw:
                    continue
                try:
                    yield self.entity.from_dict(json.loads(raw))
                except self._CORRUPT_LINE_ERRORS as exc:
                    logger.warning(
                        "Skipping malformed line %d in %s: %s — %r",
                        line_number,
                        self._filename,
                        exc,
                        raw[:120],
                    )
                    continue

    def _atomic_write(self, lines: list) -> None:
        """Replace the file's contents atomically.

        Writes to a temp file in the same directory (so the rename stays on one
        filesystem), fsyncs it, then ``os.replace``s it over the original. A
        reader or a crash sees either the old complete file or the new one,
        never a partially rewritten table.
        """
        directory = os.path.dirname(self._filename)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                fp.writelines(lines)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp, self._filename)  # atomic on POSIX and Windows
        except BaseException:
            os.unlink(tmp)
            raise

    def add(self, entity: EntityType) -> EntityType:
        serialized = json.dumps(entity.asdict(), cls=EnhancedEncoder)
        with open(self._filename, "a", encoding="utf-8") as fp:
            fp.write(serialized + "\n")
        return super().add(entity)

    def update(self, entity: EntityType, *, upsert=False) -> EntityType:
        try:
            current = self.find_one(Specification.parse(id=entity.id))
        except ObjectNotFoundException:
            current = None
        if current or upsert:
            if current:
                self.remove_one(Specification.parse(id=current.id))
            return self.add(entity)
        raise self._object_not_found()

    def remove_one(self, specification: Specification):
        super().remove_one(specification)
        entities = list(self.find(NotSpecification(specification)))
        self._atomic_write(
            [json.dumps(e.asdict(), cls=EnhancedEncoder) + "\n" for e in entities]
        )


class FileFileRepositoryMixin(RootDirMixin, FileRepository):
    def upload_file(self, data: bytes, content_type: str, reference: str = "") -> str:
        if not reference:
            reference = str(uuid.uuid4())
        with open(os.path.join(self.root_dir, "media", reference), "wb") as fp:
            fp.write(data)
        return reference

    def get_file(self, reference: str) -> bytes:
        with open(os.path.join(self.root_dir, "media", reference), "rb") as fp:
            return fp.read()

    def delete_file(self, reference: str) -> bool:
        try:
            os.remove(os.path.join(self.root_dir, "media", reference))
            return True
        except FileNotFoundError:
            return False
