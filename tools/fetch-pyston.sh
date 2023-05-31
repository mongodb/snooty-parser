#!/bin/sh
set -eu
VERSION="2.3.5"
EXTRACTED_PATH="`pwd`/pyston_${VERSION}"

if [ ! -d "${EXTRACTED_PATH}" ]; then
    curl -OL "https://github.com/pyston/pyston/releases/download/pyston_${VERSION}/pyston_${VERSION}_portable_amd64.tar.gz"
    tar -xf "pyston_${VERSION}_portable_amd64.tar.gz"
    rm "pyston_${VERSION}_portable_amd64.tar.gz"
    ln -s "libpython3.8-pyston2.3.so" "pyston_${VERSION}/lib/libpython3.8.so"
    ln -s "libpython3.8-pyston2.3.so" "pyston_${VERSION}/lib/libpython3.8.so.1.0"
fi
echo "${EXTRACTED_PATH}"
