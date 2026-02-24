#!/bin/bash
# Build a custom Wine runner for Bottles with JM Studio patches.
# Produces a tarball that can be extracted into the Bottles runners directory.

set -euo pipefail

WINE_REPO="https://github.com/poita66/wine.git"
WINE_BRANCH="test/all-prs"
LIBUSB_URL="https://github.com/libusb/libusb/releases/download/v1.0.27/libusb-1.0.27.tar.bz2"
LIBUSB_SHA256="ffaa41d741a8a3bee244ac8e54a72ea05bf2879663c098c82fc5757853441575"

RUNNER_NAME="wine-jmstudio"
BUILD_DIR="$(pwd)/build"
INSTALL_DIR="$(pwd)/${RUNNER_NAME}"

JOBS="${JOBS:-$(nproc)}"

cleanup() {
    echo "Build artifacts are in: ${BUILD_DIR}"
    echo "Runner installed to: ${INSTALL_DIR}"
}
trap cleanup EXIT

echo "=== Building ${RUNNER_NAME} runner ==="

mkdir -p "${BUILD_DIR}"

# --- libusb ---
echo "--- Building libusb ---"
cd "${BUILD_DIR}"
if [ ! -f libusb-1.0.27.tar.bz2 ]; then
    curl -LO "${LIBUSB_URL}"
    echo "${LIBUSB_SHA256}  libusb-1.0.27.tar.bz2" | sha256sum -c -
fi
if [ ! -d libusb-1.0.27 ]; then
    tar xf libusb-1.0.27.tar.bz2
fi
cd libusb-1.0.27
./configure --prefix="${INSTALL_DIR}"
make -j"${JOBS}"
make install

# --- Wine ---
echo "--- Building Wine ---"
cd "${BUILD_DIR}"
if [ ! -d wine ]; then
    git clone --depth=1 -b "${WINE_BRANCH}" "${WINE_REPO}" wine
fi
mkdir -p wine-build
cd wine-build

# WoW64 mode: single 64-bit build that handles 32-bit Windows apps natively
"${BUILD_DIR}/wine/configure" \
    --prefix="${INSTALL_DIR}" \
    --enable-archs=i386,x86_64 \
    --with-x \
    --without-capi \
    --without-gphoto \
    --without-gstreamer \
    --without-oss \
    --without-sane \
    --without-krb5 \
    LIBUSB_CFLAGS="-I${INSTALL_DIR}/include/libusb-1.0" \
    LIBUSB_LIBS="-L${INSTALL_DIR}/lib -lusb-1.0"

make -j"${JOBS}"
make install

# --- Package ---
echo "--- Packaging runner tarball ---"
cd "$(pwd)/../.."
tar czf "${RUNNER_NAME}.tar.gz" "${RUNNER_NAME}"

echo ""
echo "=== Done ==="
echo "Runner tarball: ${RUNNER_NAME}.tar.gz"
echo ""
echo "Install with:"
echo "  tar xzf ${RUNNER_NAME}.tar.gz -C ~/.var/app/com.usebottles.bottles/data/bottles/runners/"
