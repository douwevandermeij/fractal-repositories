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
