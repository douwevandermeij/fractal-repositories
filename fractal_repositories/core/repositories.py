from abc import ABC, abstractmethod
from typing import Generic, Iterator, Optional, Type, TypeVar

from fractal_specifications.generic.specification import Specification

from fractal_repositories.core.entity import Entity
from fractal_repositories.exceptions import ObjectNotFoundException, RepositoryException

EntityType = TypeVar("EntityType", bound=Entity)


class ReadRepository(Generic[EntityType], ABC):
    """
    Abstract base class for read-only repository operations.

    Provides query capabilities for retrieving entities from a data store
    using the Repository Pattern from Domain-Driven Design.

    Attributes:
        entity: The entity class this repository manages (must be set by subclass)
        object_not_found_exception_class: Custom exception class for not found errors
        order_by: Default ordering for queries (e.g., "-created_at" for descending)

    Example:
        @dataclass
        class User(Entity):
            id: str
            name: str
            email: str

        class UserRepository(ReadRepository[User], ABC):
            entity = User

        class InMemoryUserRepository(UserRepository, InMemoryRepositoryMixin[User]):
            pass

        repo = InMemoryUserRepository()
        users = list(repo.find())
    """

    entity: EntityType
    object_not_found_exception_class: Optional[Type[ObjectNotFoundException]] = None
    order_by: str = ""

    def __init__(self, *args, **kwargs) -> None:
        if not hasattr(self, "entity"):
            raise RepositoryException()

    @abstractmethod
    def find_one(self, specification: Specification) -> EntityType:
        """
        Find a single entity matching the specification.

        Args:
            specification: Filter criteria for the query

        Returns:
            The matching entity

        Raises:
            ObjectNotFoundException: If no entity matches the specification

        Example:
            user = repo.find_one(Specification.parse(email="alice@example.com"))
        """
        raise NotImplementedError

    @abstractmethod
    def find(
        self,
        specification: Optional[Specification] = None,
        *,
        offset: int = 0,
        limit: int = 0,
        order_by: str = "",
    ) -> Iterator[EntityType]:
        """
        Find multiple entities matching the specification with pagination.

        Args:
            specification: Optional filter criteria (None returns all entities)
            offset: Number of results to skip (for pagination)
            limit: Maximum number of results to return (0 = no limit)
            order_by: Field to order by (prefix with "-" for descending, e.g., "-created_at")

        Returns:
            Iterator of matching entities

        Example:
            # Get all users
            all_users = list(repo.find())

            # Get active users with pagination
            active_users = list(repo.find(
                Specification.parse(active=True),
                offset=0,
                limit=10,
                order_by="-created_at"
            ))
        """
        raise NotImplementedError

    @abstractmethod
    def count(self, specification: Optional[Specification] = None) -> int:
        """
        Count entities matching the specification.

        Args:
            specification: Optional filter criteria (None counts all entities)

        Returns:
            Number of matching entities

        Example:
            total_users = repo.count()
            active_users = repo.count(Specification.parse(active=True))
        """
        raise NotImplementedError

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the repository/database connection is healthy.

        Returns:
            True if the repository can connect and query the data store

        Example:
            if repo.is_healthy():
                print("Database connection is OK")
        """
        raise NotImplementedError

    def _object_not_found(self):
        """Helper method to create ObjectNotFoundException with entity name."""
        entity_name = self.entity.__name__ if hasattr(self, "entity") else "Object"
        if self.object_not_found_exception_class:
            return self.object_not_found_exception_class(f"{entity_name} not found!")
        return ObjectNotFoundException(f"{entity_name} not found!")


class WriteRepository(Generic[EntityType], ABC):
    """
    Abstract base class for write repository operations.

    Provides create, update, and delete capabilities for entities in a data store
    using the Repository Pattern from Domain-Driven Design.

    Example:
        @dataclass
        class User(Entity):
            id: str
            name: str
            email: str

        class UserRepository(WriteRepository[User], ABC):
            entity = User

        class MongoUserRepository(UserRepository, MongoRepositoryMixin[User]):
            pass

        repo = MongoUserRepository(host="localhost", database="mydb")
        user = User(id="1", name="Alice", email="alice@example.com")
        repo.add(user)
    """

    @abstractmethod
    def add(self, entity: EntityType) -> EntityType:
        """
        Add a new entity to the repository.

        Args:
            entity: The entity to add

        Returns:
            The added entity (may include generated fields like timestamps)

        Raises:
            May raise database-specific exceptions if entity already exists
            or validation fails

        Example:
            user = User(id="1", name="Alice", email="alice@example.com")
            saved_user = repo.add(user)
        """
        raise NotImplementedError

    @abstractmethod
    def update(self, entity: EntityType, *, upsert: bool = False) -> EntityType:
        """
        Update an existing entity in the repository.

        Args:
            entity: The entity to update (must have existing id)
            upsert: If True, insert the entity if it doesn't exist (default: False)

        Returns:
            The updated entity

        Raises:
            ObjectNotFoundException: If entity doesn't exist and upsert=False

        Example:
            user = repo.find_one(Specification.parse(id="1"))
            user.email = "newemail@example.com"
            repo.update(user)

            # Or with upsert
            new_user = User(id="2", name="Bob", email="bob@example.com")
            repo.update(new_user, upsert=True)  # Creates if doesn't exist
        """
        raise NotImplementedError

    @abstractmethod
    def remove_one(self, specification: Specification) -> None:
        """
        Remove a single entity matching the specification.

        Args:
            specification: Filter criteria to identify the entity to remove

        Example:
            repo.remove_one(Specification.parse(id="1"))
            repo.remove_one(Specification.parse(email="alice@example.com"))
        """
        raise NotImplementedError

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the repository/database connection is healthy.

        Returns:
            True if the repository can connect and write to the data store

        Example:
            if repo.is_healthy():
                print("Database connection is OK")
        """
        raise NotImplementedError


class Repository(ReadRepository[EntityType], WriteRepository[EntityType], ABC):
    """
    Complete repository with both read and write operations.

    Combines ReadRepository and WriteRepository to provide full CRUD
    (Create, Read, Update, Delete) capabilities.

    This is the most commonly used repository base class.

    Example:
        @dataclass
        class User(Entity):
            id: str
            name: str
            email: str

        class UserRepository(Repository[User], ABC):
            entity = User

        # Implement with any storage backend
        class PostgresUserRepository(UserRepository, PostgresRepositoryMixin[User]):
            pass

        repo = PostgresUserRepository(
            postgres_host="localhost",
            postgres_db="mydb",
            postgres_user="user",
            postgres_password="pass",
        )

        # Full CRUD operations
        user = User(id="1", name="Alice", email="alice@example.com")
        repo.add(user)                                      # Create
        found = repo.find_one(Specification.parse(id="1"))  # Read
        found.name = "Alice Smith"
        repo.update(found)                                  # Update
        repo.remove_one(Specification.parse(id="1"))        # Delete
    """

    pass


class FileRepository(Generic[EntityType], ABC):
    """
    Abstract base class for file storage operations.

    Provides file upload, download, and deletion capabilities independent
    of the entity repository pattern.

    Useful for storing binary data like images, documents, or any file content
    alongside or separate from entity data.

    Example:
        from fractal_repositories.contrib.gcp.cloudstorage import (
            CloudStorageRepositoryMixin
        )

        class DocumentRepository(
            FileRepository[Document],
            CloudStorageRepositoryMixin[Document]
        ):
            entity = Document

        repo = DocumentRepository(bucket_name="my-documents")

        # Upload a file
        with open("report.pdf", "rb") as f:
            file_data = f.read()
        reference = repo.upload_file(
            data=file_data,
            content_type="application/pdf",
            reference="reports/2024-q1.pdf"  # Optional, auto-generated if not provided
        )

        # Download the file
        downloaded = repo.get_file(reference)

        # Delete the file
        repo.delete_file(reference)
    """

    @abstractmethod
    def upload_file(self, data: bytes, content_type: str, reference: str = "") -> str:
        """
        Upload a file to the storage system.

        Args:
            data: File content as bytes
            content_type: MIME type of the file (e.g., "image/png", "application/pdf")
            reference: Optional file identifier/path. If not provided, will be auto-generated
                      (typically a UUID or storage-specific identifier)

        Returns:
            The reference/identifier for the uploaded file (can be used to retrieve or delete)

        Example:
            with open("avatar.png", "rb") as f:
                ref = repo.upload_file(f.read(), "image/png", "avatars/user-123.png")
            # Returns: "avatars/user-123.png" or auto-generated like "550e8400-e29b-41d4-a716-446655440000"
        """
        raise NotImplementedError

    @abstractmethod
    def get_file(self, reference: str) -> bytes:
        """
        Retrieve a file from the storage system.

        Args:
            reference: The file identifier/path returned by upload_file()

        Returns:
            File content as bytes

        Raises:
            May raise storage-specific exceptions if file not found

        Example:
            data = repo.get_file("avatars/user-123.png")
            with open("downloaded.png", "wb") as f:
                f.write(data)
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, reference: str) -> bool:
        """
        Delete a file from the storage system.

        Args:
            reference: The file identifier/path to delete

        Returns:
            True if file was deleted successfully

        Example:
            success = repo.delete_file("avatars/user-123.png")
        """
        raise NotImplementedError
