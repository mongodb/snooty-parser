.PHONY: help lint format test clean flit-publish package cut-release performance-report

SYSTEM_PYTHON=$(shell which python3)
PLATFORM=$(shell printf '%s_%s' "$$(uname -s | tr '[:upper:]' '[:lower:]')" "$$(uname -m)")
VERSION=$(shell git describe --tags)
PUSH_TO=$(shell git remote -v | grep -m1 -E 'github.com:|/mongodb/snooty-parser.git' | cut -f 1)
PACKAGE_NAME=snooty-${VERSION}-${PLATFORM}.zip
export SOURCE_DATE_EPOCH = $(shell date +%s)

help: ## Show this help message
	@grep -E '^[a-zA-Z_.0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.venv/.EXISTS: pyproject.toml
	-rm -r .venv snootycli.py
	python3 -m venv .venv
	. .venv/bin/activate && \
		python3 -m pip install --upgrade pip && \
		python3 -m pip install flit && \
		flit install -s --deps=develop
	touch $@

lint: .venv/.EXISTS ## Run all linting
	. .venv/bin/activate && python3 -m mypy --strict snooty tools
	. .venv/bin/activate && python3 -m pyflakes snooty tools
	. .venv/bin/activate && python3 -m black snooty tools --check
	tools/lint_changelog.py CHANGELOG.md

format: .venv/.EXISTS ## Format source code with black
	. .venv/bin/activate && python3 -m isort snooty tools
	. .venv/bin/activate && python3 -m black snooty tools

test: lint ## Run unit tests
	. .venv/bin/activate && python3 -X dev -m pytest --cov=snooty

dist/snooty/.EXISTS: .venv/.EXISTS pyproject.toml snooty/*.py snooty/gizaparser/*.py
	-rm -rf snooty.dist dist
	mkdir dist
	echo 'from snooty import main; main.main()' > snootycli.py
	. .venv/bin/activate && python3 -m PyInstaller -n snooty snootycli.py
	rm snootycli.py
	install -m644 snooty/config.toml snooty/rstspec.toml LICENSE* dist/snooty/
	touch $@

dist/${PACKAGE_NAME}: snooty/rstspec.toml snooty/config.toml dist/snooty/.EXISTS ## Build a binary tarball
	# Normalize the mtime, and zip in sorted order
	cd dist && find snooty -print | sort | zip -X ../$@ -@
	# Ensure that the generated binary runs
	./dist/snooty/snooty --help >/dev/null
	echo "::set-output name=package_filename::${PACKAGE_NAME}"

dist/${PACKAGE_NAME}.asc: dist/snooty-${VERSION}-${PLATFORM}.zip ## Build and sign a binary tarball
	gpg --armor --detach-sig $^

clean: ## Remove all build artifacts
	-rm -r snooty.tar.zip* snootycli.py .venv
	-rm -rf dist
	-rm -rf .docs

flit-publish: test ## Deploy the package to pypi
	SOURCE_DATE_EPOCH="$$SOURCE_DATE_EPOCH" flit publish

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
	git tag -s -m "Release v${BUMP_TO_VERSION}" "v${BUMP_TO_VERSION}"

	if [ -n "${PUSH_TO}" ]; then git push "${PUSH_TO}" "v${BUMP_TO_VERSION}"; fi

	# Make a post-release version bump
	tools/bump_version.py dev
	git add snooty/__init__.py
	git commit -m "Post-release bump"

	@echo
	@echo "Creating the release may now take several minutes. Check https://github.com/mongodb/snooty-parser/actions for status."
	@echo "Release will be created at: https://github.com/mongodb/snooty-parser/releases/tag/v${BUMP_TO_VERSION}"

DOCS_COMMIT=1c6dfe71fd45fbdcdf5c7b73f050f615f4279064
performance-report: .venv/.EXISTS ## Fetch a sample corpus, and generate a timing report for each part of the parse
	if [ ! -d .docs ]; then git clone https://github.com/mongodb/docs.git .docs; fi
	cd .docs; if [ `git rev-parse HEAD` != "${DOCS_COMMIT}" ]; then git fetch && git reset --hard "${DOCS_COMMIT}"; fi
	. .venv/bin/activate && python3 -m snooty.performance_report .docs
