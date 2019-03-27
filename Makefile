.PHONY: help lint test clean flit-publish

SYSTEM_PYTHON=$(shell which python3)
PLATFORM=$(shell printf '%s_%s' "$$(uname -s | tr '[:upper:]' '[:lower:]')" "$$(uname -m)")
VERSION=$(shell $(SYSTEM_PYTHON) -c 'exec(open("snooty/__init__.py").read()); print(__version__)')
export SOURCE_DATE_EPOCH = $(shell date +%s)

help: ## Show this help message
	@grep -E '^[a-zA-Z_.0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.venv/.EXISTS:
	-rm -r .venv snooty.py
	python3 -m virtualenv .venv
	. .venv/bin/activate && \
		python3 -m pip install --upgrade pip && \
		python3 -m pip install flit && \
		flit install --deps=develop
	touch $@

lint: .venv/.EXISTS ## Run all linting
	. .venv/bin/activate && python3 -m mypy --strict snooty
	. .venv/bin/activate && python3 -m flake8 --max-line-length=100 snooty

test: lint ## Run unit tests
	. .venv/bin/activate && python3 -m pytest --cov=snooty

dist/snooty/.EXISTS: .venv/.EXISTS pyproject.toml snooty/*.py snooty/gizaparser/*.py
	-rm -rf snooty.dist dist
	mkdir dist
	echo 'from snooty import main; main.main()' > snooty.py
	PYTHONHOME=`pwd`/.venv python3 -m nuitka \
		--standalone --python-flag=no_site --remove-output \
		--lto snooty.py
	rm snooty.py
	mv snooty.dist dist/snooty
	install -m644 snooty/rstspec.toml LICENSE* dist/snooty/
	chmod -R u+w dist/snooty

	# on macOS, bundle Python and openssl
	if [ $$(uname -s) = Darwin ]; then \
		dep_python_path=$$(otool -L dist/snooty/snooty | grep Python | awk '{print $$1}'); \
		dep_libssl_path=$$(otool -L dist/snooty/_hashlib.so | grep libssl | awk '{print $$1}'); \
		dep_libcrypto_path=$$(otool -L "$$dep_libssl_path" | grep libcrypto | awk '{print $$1}'); \
		install -m644 "$$dep_python_path" dist/snooty/ || exit 1; \
		install -m644 "$$dep_libssl_path" dist/snooty/ || exit 1; \
		install_name_tool \
			-change "$$dep_python_path" \
			@executable_path/Python \
			dist/snooty/snooty || exit 1; \
		install_name_tool \
			-change "$$dep_libssl_path" \
			"@executable_path/$$(basename $$dep_libssl_path)" \
			dist/snooty/_hashlib.so || exit 1; \
		install_name_tool \
			-change "$$dep_libcrypto_path" \
			"@executable_path/$$(basename $$dep_libcrypto_path)" \
			"dist/snooty/$$(basename $$dep_libssl_path)" || exit 1; \
	fi

	touch $@

dist/snooty-${VERSION}-${PLATFORM}.zip: snooty/rstspec.toml dist/snooty/.EXISTS ## Build a binary tarball
	# Normalize the mtime, and zip in sorted order
	find dist/snooty -exec touch -t "$$(date -jf '%s' '+%Y%m%d%H%M.%S' $$SOURCE_DATE_EPOCH)" {} +
	cd dist && find snooty -print | sort | zip -X ../$@ -@

dist/snooty-${VERSION}-${PLATFORM}.zip.asc: dist/snooty-${VERSION}-${PLATFORM}.zip ## Build and sign a binary tarball
	gpg --armor --detach-sig $^

clean: ## Remove all build artifacts
	-rm -r snooty.tar.zip* snooty.py .venv
	-rm -rf dist

flit-publish: test ## Deploy the package to pypi
	SOURCE_DATE_EPOCH="$$SOURCE_DATE_EPOCH" flit publish
