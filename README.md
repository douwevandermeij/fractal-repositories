# Fractal Repositories

> Fractal Repositories is an implementation of the repository pattern of Domain Driven Design (DDD) for building SOLID logic for your Python applications.

[![PyPI Version][pypi-image]][pypi-url]
[![Build Status][build-image]][build-url]
[![Code Coverage][coverage-image]][coverage-url]
[![Code Quality][quality-image]][quality-url]

<!-- Badges -->

[pypi-image]: https://img.shields.io/pypi/v/fractal-repositories
[pypi-url]: https://pypi.org/project/fractal-repositories/
[build-image]: https://github.com/douwevandermeij/fractal-repositories/actions/workflows/build.yml/badge.svg
[build-url]: https://github.com/douwevandermeij/fractal-repositories/actions/workflows/build.yml
[coverage-image]: https://codecov.io/gh/douwevandermeij/fractal-repositories/branch/main/graph/badge.svg
[coverage-url]: https://codecov.io/gh/douwevandermeij/fractal-repositories
[quality-image]: https://api.codeclimate.com/v1/badges/2286ddcfaf5e815d61a5/maintainability
[quality-url]: https://codeclimate.com/github/douwevandermeij/fractal-repositories

## Installation

```sh
pip install fractal-repositories
```

## Development

Setup the development environment by running:

```sh
make deps
pre-commit install
```

Happy coding.

Occasionally you can run:

```sh
make lint
```

This is not explicitly necessary because the git hook does the same thing.

**Do not disable the git hooks upon commit!**

## Usage

To get started, define an Entity you would like to store:

```python
from dataclasses import dataclass

from fractal_repositories.core.entity import Entity


@dataclass
class DemoModel(Entity):
    id: str
    name: str
```

Next, define the generic Repository:

```python
from abc import ABC

from fractal_repositories.core.repositories import Repository


class DemoRepository(Repository[DemoModel], ABC):
    entity = DemoModel
```

Now choose your target storage system, e.g., Google Firestore and define the adapter:

```python
from fractal_repositories.contrib.gcp.firestore.mixins import FirestoreRepositoryMixin


class FirestoreDemoRepository(DemoRepository, FirestoreRepositoryMixin[DemoModel]):
    ...
```

## Utilities

### FieldPermissionsRepository

`FieldPermissionsRepository` wraps any repository to enforce field-level read masking and write validation based on the caller's roles. It is useful when different users should see or modify only certain fields of the same entity — for example, a superadmin can set a sensitive field that regular users can never read or overwrite.

#### Defining field permissions on an entity

Add a `field_permissions()` classmethod to your entity. Each entry maps a field name to its `read_roles` and/or `write_roles`:

```python
from dataclasses import dataclass
from fractal_repositories.core.entity import Entity


@dataclass
class Order(Entity):
    id: str
    amount: float
    internal_notes: str = ""  # only visible/writable by staff

    @classmethod
    def field_permissions(cls):
        return {
            "internal_notes": {
                "read_roles": ["staff"],
                "write_roles": ["staff"],
            }
        }
```

Entities without a `field_permissions()` method are handled transparently — no masking or validation is applied.

#### Wrapping a repository

```python
from fractal_repositories.utils.field_permissions_repository import (
    FieldPermissionsRepository,
    OnWriteConflict,
)

inner_repo = OrderRepository()  # any Repository implementation
repo = FieldPermissionsRepository(inner_repo)
```

#### Read masking

Pass `roles` to `find_one()` or `find()`. Fields the caller is not allowed to read are set to `None`. Pass `roles=None` to skip masking (e.g. for internal service calls):

```python
# Staff sees everything
order = repo.find_one(Specification.parse(id="1"), roles=["staff"])
# order.internal_notes == "confidential"

# Regular user gets the field blanked
order = repo.find_one(Specification.parse(id="1"), roles=["customer"])
# order.internal_notes is None

# Internal call — no masking
order = repo.find_one(Specification.parse(id="1"))
# order.internal_notes == "confidential"
```

#### Write validation

Pass `roles` to `add()` or `update()`. By default (`OnWriteConflict.RAISE`), a `PermissionError` is raised if the caller submits a non-default value for a field they are not allowed to write:

```python
# Allowed — internal_notes is at its default value
repo.add(Order(id="1", amount=99.0), roles=["customer"])

# Raises PermissionError — customer cannot set internal_notes
repo.add(Order(id="1", amount=99.0, internal_notes="hack"), roles=["customer"])
```

#### on_write_conflict="preserve" — PUT-style APIs

When callers send back the full entity (e.g. a REST PUT), they will have received secured fields set to `None`. Submitting `None` against a staff-set value would raise under the default mode. Use `OnWriteConflict.PRESERVE` to silently restore the stored value instead, so the rest of the update proceeds normally:

```python
repo = FieldPermissionsRepository(inner_repo, on_write_conflict=OnWriteConflict.PRESERVE)

# Staff sets a note
repo.update(Order(id="1", amount=99.0, internal_notes="VIP customer"), roles=["staff"])

# Customer updates the amount — internal_notes is silently preserved, not raised
repo.update(Order(id="1", amount=120.0, internal_notes=None), roles=["customer"])
# stored: internal_notes == "VIP customer"
```

#### Custom exception class

Replace `PermissionError` with your own exception by passing `forbidden_exception_class`:

```python
from myapp.exceptions import ForbiddenError

repo = FieldPermissionsRepository(inner_repo, forbidden_exception_class=ForbiddenError)
```

### MemoizedRepository

`MemoizedRepository` wraps any repository and caches `find_one()` results in-process, so repeated lookups for the same specification never hit the underlying store more than once. Mutations are cache-aware: `update` refreshes the cached entry in place, `remove_one` and `delete` evict only the affected entity, and `add` leaves the cache untouched (the new entity is populated lazily on the next `find_one`).

`find()`, `count()`, and `is_healthy()` always delegate directly to the inner repository without caching.

#### Constructor

```python
from fractal_repositories.utils.memoized_repository import MemoizedRepository

inner_repo = ItemRepository()  # any Repository implementation
repo = MemoizedRepository(inner_repo)
```

#### Caching behaviour

```python
spec = Specification.parse(id="42")

item = repo.find_one(spec)   # hits the inner repository
item = repo.find_one(spec)   # served from in-process cache — inner not called again

item = repo.get("42")        # get() calls find_one() internally, so also cached
```

#### Cache invalidation

Each write operation is targeted — only the affected entity's cache entry changes:

```python
repo.add(Item(id="1", name="Alice"))          # no cache effect; populated lazily on next find_one
repo.update(Item(id="1", name="Bob"))         # updates _cache["1"] in place; other entries untouched
repo.remove_one(Specification.parse(id="1"))  # evicts _cache["1"] only
repo.delete("1")                              # evicts _cache["1"] only (calls remove_one)
```

Each `MemoizedRepository` instance maintains its own independent cache, so wrapping the same inner repo in two separate `MemoizedRepository` objects gives two separate caches.

### CachedRepository

`CachedRepository` implements a write-through dual-layer cache. It takes a `main_repository` (e.g. Mongo or Postgres) and a `cache_repository` (e.g. InMemory) and keeps them in sync automatically. Reads are always served from the fast cache; writes go to both layers simultaneously.

#### Constructor

```python
from fractal_repositories.utils.cached_repository import CachedRepository

repo = CachedRepository(
    main_repository=mongo_repo,   # any Repository implementation
    cache_repository=memory_repo, # any Repository implementation
)
```

#### Write-through behaviour

Every mutation is applied to both the main repository and the cache:

```python
repo.add(item)              # written to main_repository and cache_repository
repo.update(item)           # updated in main_repository and cache_repository
repo.remove_one(spec)       # removed from main_repository and cache_repository
```

#### Read-from-cache behaviour

`find_one()` and `find()` are served exclusively from the cache, so they never touch the main repository after the cache has been populated:

```python
item  = repo.find_one(spec)   # reads from cache_repository only
items = list(repo.find())     # reads from cache_repository only
n     = repo.count()          # reads from main_repository (authoritative count)
```

#### Populating the cache

The cache starts empty. Call one of the two sync helpers before your application begins serving reads:

- **`load_cache()`** — one-way populate. Copies every entity from the main repository into the cache. Use this on a fresh, empty cache (calling it on a non-empty cache will attempt to `add` entities that already exist).
- **`reload_cache()`** — full sync. Upserts every entity from the main repository into the cache, then removes any cache entries whose ids are no longer present in the main repository. Safe to call repeatedly for periodic refresh.

```python
# Startup: populate the cache once
repo.load_cache()

# Periodic refresh: keep the cache in sync with the source of truth
repo.reload_cache()
```

#### Example

```python
from fractal_repositories.utils.cached_repository import CachedRepository

# inner_main_repo  — e.g. a PostgresProductRepository
# inner_cache_repo — e.g. an InMemoryProductRepository

repo = CachedRepository(
    main_repository=inner_main_repo,
    cache_repository=inner_cache_repo,
)

# Populate the cache on application startup
repo.load_cache()

# From here on, find_one/find are served from memory
product = repo.find_one(Specification.parse(id="sku-42"))
```

---

### DistributedReadRepository

`DistributedReadRepository` is a read-only data-federation layer. It takes a `main_repository` and a list of `DistributedRelation` objects. For every entity returned by the main repository, it queries each related repository and merges the results into the entity before yielding it. There are no `add`, `update`, or `remove_one` methods — this class is intentionally read-only.

#### `DistributedRelation`

```python
from fractal_repositories.utils.distributed_read_repository import DistributedRelation

relation = DistributedRelation(
    repository=other_repo,              # ReadRepository to query for each main entity
    specification_func=lambda e: ...,   # callable: main entity → Specification
    aggregate_target_field="",          # "" = flat merge (default), or a field name for aggregation
)
```

| Field | Type | Description |
|---|---|---|
| `repository` | `ReadRepository` | The secondary repository to query. |
| `specification_func` | `Callable[[EntityType], Specification]` | Given a main entity, returns the specification used to look up related data. |
| `aggregate_target_field` | `str` | `""` for flat merge; a field name to collect matching entities into a list on the main entity. |

#### Constructor

```python
from fractal_repositories.utils.distributed_read_repository import DistributedReadRepository

repo = DistributedReadRepository(
    main_repository=main_repo,
    other_repositories=[relation1, relation2],
)
```

`count()` returns the sum of counts across all repositories. `is_healthy()` checks all repositories.

#### Flat-merge example (field enrichment)

When `aggregate_target_field` is `""` (the default), non-empty, non-`id` fields from the related entity are merged field-by-field into the main entity. This is useful when a second repository holds supplementary data for the same entity type.

```python
from fractal_specifications.generic.specification import Specification
from fractal_repositories.utils.distributed_read_repository import (
    DistributedReadRepository,
    DistributedRelation,
)

# product_repo  — main store: id, name, price
# metadata_repo — secondary store: id, description, tags

repo = DistributedReadRepository(
    main_repository=product_repo,
    other_repositories=[
        DistributedRelation(
            repository=metadata_repo,
            specification_func=lambda p: Specification.parse(id=p.id),
            # aggregate_target_field="" — fields are merged directly onto the product
        )
    ],
)

# Each yielded Product has name, price AND description, tags populated
product = repo.find_one(Specification.parse(id="sku-42"))
```

#### Aggregation example (one-to-many)

When `aggregate_target_field` is set to a field name, every matching entity from the related repository is appended to that list field on the main entity. The field must already exist on the entity (typically defined as an empty list default).

```python
from fractal_repositories.utils.distributed_read_repository import (
    DistributedReadRepository,
    DistributedRelation,
)

# order_repo    — main store: Order(id, customer_id, total, line_items=[])
# line_item_repo — secondary store: LineItem(id, order_id, sku, qty)

repo = DistributedReadRepository(
    main_repository=order_repo,
    other_repositories=[
        DistributedRelation(
            repository=line_item_repo,
            specification_func=lambda order: Specification.parse(order_id=order.id),
            aggregate_target_field="line_items",  # collect into Order.line_items
        )
    ],
)

# Each yielded Order has its line_items list populated
order = repo.find_one(Specification.parse(id="order-99"))
# order.line_items == [LineItem(...), LineItem(...), ...]
```

---

## Contrib

Fractal Repositories comes with ready to use adapter mixins for:
* Django
* SQLAlchemy
* PostgreSQL
* MongoDB
* DuckDB
* Google Firestore
* Google Cloud Storage

## Examples

### DuckDB (In-process Analytical Database)

DuckDB is an in-process SQL OLAP database management system, perfect for analytical workloads and embedded analytics.

```python
from dataclasses import dataclass
from fractal_repositories.core.entity import Entity
from fractal_repositories.core.repositories import Repository
from fractal_repositories.contrib.duckdb import DuckDBRepositoryMixin
from fractal_specifications.generic.specification import Specification


@dataclass
class User(Entity):
    id: str
    name: str
    email: str


class UserRepository(Repository[User], DuckDBRepositoryMixin[User]):
    entity = User


# In-memory database (great for testing)
repo = UserRepository(database=":memory:", table="users")

# Or file-based database for persistence
# repo = UserRepository(database="analytics.db", table="users")

# Add entities
user = User(id="1", name="Alice", email="alice@example.com")
repo.add(user)

# Query with specifications
found_user = repo.find_one(Specification.parse(id="1"))

# Find all users
all_users = list(repo.find())

# Count users
user_count = repo.count()

# Update
user.email = "newemail@example.com"
repo.update(user)

# Remove
repo.remove_one(Specification.parse(id="1"))
```

### MongoDB

```python
from fractal_repositories.contrib.mongo import MongoRepositoryMixin


class MongoUserRepository(UserRepository, MongoRepositoryMixin[User]):
    pass


repo = MongoUserRepository(
    host="localhost",
    port="27017",
    username="user",
    password="pass",
    database="mydb",
    collection="users"
)
```

### Google Firestore

```python
from fractal_repositories.contrib.gcp.firestore import FirestoreRepositoryMixin


class FirestoreUserRepository(UserRepository, FirestoreRepositoryMixin[User]):
    pass


repo = FirestoreUserRepository(
    collection="users",
    service_account_path="/path/to/service-account.json"
)
```

### PostgreSQL

```python
from fractal_repositories.contrib.postgresql import PostgresRepositoryMixin


class PostgresUserRepository(UserRepository, PostgresRepositoryMixin[User]):
    pass


repo = PostgresUserRepository(
    postgres_host="localhost",
    postgres_port="5432",
    postgres_db="mydb",
    postgres_user="user",
    postgres_password="pass",
    table="users"
)
```

### Django

```python
from fractal_repositories.contrib.django import DjangoModelRepositoryMixin


class DjangoUserRepository(UserRepository, DjangoModelRepositoryMixin[User]):
    pass


# Assuming you have a Django model
from myapp.models import UserModel

repo = DjangoUserRepository(django_model=UserModel)
```

### SQLAlchemy

```python
from fractal_repositories.contrib.sqlalchemy.mixins import SqlAlchemyRepositoryMixin


class SqlAlchemyUserRepository(UserRepository, SqlAlchemyRepositoryMixin[User]):
    pass


# Use with your SQLAlchemy session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine("sqlite:///example.db")
Session = sessionmaker(bind=engine)
session = Session()

repo = SqlAlchemyUserRepository(session=session, model=YourSqlAlchemyModel)
```
