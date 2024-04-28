.DEFAULT_GOAL := help
.PHONY: coverage deps help lint publish push sonar test tox

coverage:  ## Run tests with coverage
	rm .coverage ||:
	rm coverage.xml ||:
	pytest --cov fractal_repositories --cov-report=xml

deps:  ## Install dependencies
	python -m pip install --upgrade pip
	python -m pip install -U black cloud-storage-mocker coverage django firebase-admin flake8 flit fractal-specifications google-cloud-firestore google-cloud-storage isort mccabe mock-firestore mongomock mypy pydantic pylint pymongo "pytest<8" pytest-cov pytest-asyncio pytest-lazy-fixture pytest-mock 'sqlalchemy<2.0' tox tox-gh-actions pre-commit autoflake
	pre-commit install

lint:  ## Lint and static-check
	pre-commit run --all-files

publish:  ## Publish to PyPi
	python -m flit publish

push:  ## Push code with tags
	git push && git push --tags

sonar:  ## Run sonar-scanner
	make coverage
	sonar-scanner

test:  ## Run tests
	pytest --cov fractal_repositories

tox:   ## Run tox
	python -m tox

help: ## Show help message
	@IFS=$$'\n' ; \
	help_lines=(`fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##/:/'`); \
	printf "%s\n\n" "Usage: make [task]"; \
	printf "%-20s %s\n" "task" "help" ; \
	printf "%-20s %s\n" "------" "----" ; \
	for help_line in $${help_lines[@]}; do \
		IFS=$$':' ; \
		help_split=($$help_line) ; \
		help_command=`echo $${help_split[0]} | sed -e 's/^ *//' -e 's/ *$$//'` ; \
		help_info=`echo $${help_split[2]} | sed -e 's/^ *//' -e 's/ *$$//'` ; \
		printf '\033[36m'; \
		printf "%-20s %s" $$help_command ; \
		printf '\033[0m'; \
		printf "%s\n" $$help_info; \
	done
