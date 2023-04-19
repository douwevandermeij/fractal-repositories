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
* Mongo
* Google Firestore
* Elastic
