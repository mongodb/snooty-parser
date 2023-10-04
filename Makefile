.PHONY: help lint format test clean package cut-release performance-report

PLATFORM=$(shell printf '%s_%s' "$$(uname -s | tr '[:upper:]' '[:lower:]')" "$$(uname -m)")
VERSION=$(shell git describe --tags)
PUSH_TO=$(shell git remote -v | grep -m1 -E 'github.com(:|/)mongodb/snooty-parser.git' | cut -f 1)
PACKAGE_NAME=snooty-${VERSION}-${PLATFORM}.zip

help: ## Show this help message
	@grep -E '^[a-zA-Z_.0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run all linting
	poetry run mypy --strict snooty tools
	poetry run pyflakes snooty tools
	poetry run black snooty tools --check
	tools/lint_changelog.py CHANGELOG.md

format: ## Format source code with black
	poetry run isort snooty tools
	poetry run black snooty tools

test: lint ## Run unit tests
	poetry run python3 -X dev -m pytest --cov=snooty

dist/snooty/.EXISTS: pyproject.toml snooty/*.py snooty/gizaparser/*.py
	-rm -rf snooty.dist dist
	mkdir dist
	echo 'from snooty import main; main.main()' > snootycli.py

	if [ "`uname -ms`" = "Linux x86_64" ]; then \
		poetry env use "`tools/fetch-pyston.sh`/pyston3" && poetry install; \
	fi; LD_LIBRARY_PATH=pyston_2.3.5/lib/ poetry run cxfreeze --target-name snooty --target-dir dist/snooty snootycli.py

	rm snootycli.py
	install -m644 snooty/config.toml snooty/rstspec.toml snooty/taxonomy.toml LICENSE* dist/snooty/
	touch $@

dist/${PACKAGE_NAME}: snooty/rstspec.toml snooty/config.toml snooty/taxonomy.toml dist/snooty/.EXISTS ## Build a binary tarball
	# Normalize the mtime, and zip in sorted order
	cd dist && find snooty -print | sort | zip -X ../$@ -@
	# Ensure that the generated binary runs
	./dist/snooty/snooty --help >/dev/null
	if [ -n "${GITHUB_OUTPUT}" ]; then echo "package_filename=${PACKAGE_NAME}" >> "${GITHUB_OUTPUT}"; fi

dist/${PACKAGE_NAME}.asc: dist/snooty-${VERSION}-${PLATFORM}.zip ## Build and sign a binary tarball
	gpg --armor --detach-sig $^

clean: ## Remove all build artifacts
	-rm -r snooty.tar.zip* snootycli.py
	-rm -rf dist
	-rm -rf .docs
	-rm -r pyston_2.3.5

package: dist/${PACKAGE_NAME}

cut-release: ## Release a new version of snooty. Must provide BUMP_TO_VERSION
	@if [ $$(echo "${BUMP_TO_VERSION}" | grep -cE '^[0-9]+\.[0-9]+\.[0-9]+(-[[:alnum:]_-]+)?$$') -ne 1 ]; then \
		echo "Must specify a valid BUMP_TO_VERSION (e.g. 'make cut-release BUMP_TO_VERSION=0.1.15')"; \
		exit 1; \
	fi
	@git diff-index --quiet HEAD -- || { echo "Uncommitted changes found"; exit 1; }
	$(MAKE) clean
	tools/bump_version.py "${BUMP_TO_VERSION}"
	git add snooty/__init__.py CHANGELOG.md
	git commit -m "Bump to v${BUMP_TO_VERSION}"
	$(MAKE) test
	git tag -m "Release v${BUMP_TO_VERSION}" "v${BUMP_TO_VERSION}"

	if [ -n "${PUSH_TO}" ]; then git push "${PUSH_TO}" "v${BUMP_TO_VERSION}"; fi

	# Make a post-release version bump
	tools/bump_version.py dev
	git add snooty/__init__.py
	git commit -m "Post-release bump"

	@echo
	@echo "Creating the release may now take several minutes. Check https://github.com/mongodb/snooty-parser/actions for status."
	@echo "Release will be created at: https://github.com/mongodb/snooty-parser/releases/tag/v${BUMP_TO_VERSION}"

DOCS_COMMIT=1c6dfe71fd45fbdcdf5c7b73f050f615f4279064
performance-report: ## Fetch a sample corpus, and generate a timing report for each part of the parse
	if [ ! -d .docs ]; then git clone https://github.com/mongodb/docs.git .docs; fi
	cd .docs; if [ `git rev-parse HEAD` != "${DOCS_COMMIT}" ]; then git fetch && git reset --hard "${DOCS_COMMIT}"; fi
	poetry run python3 -m snooty.performance_report .docs
