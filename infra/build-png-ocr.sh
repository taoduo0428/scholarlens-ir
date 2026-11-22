#!/bin/sh
# Build only the OCR features used by figure_legend. Keep both source versions in dpkg.
set -eu
export DEBIAN_FRONTEND=noninteractive
sed 's/^Types: deb$/Types: deb-src/' /etc/apt/sources.list.d/debian.sources > /etc/apt/sources.list.d/ocr-src.sources
apt-get update
apt-get install -y --no-install-recommends build-essential cmake dpkg-dev pkg-config libpng-dev
mkdir -p /build/src /packages
cd /build/src
apt-get source leptonlib tesseract
lept=$(realpath leptonlib-*/)
tess=$(realpath tesseract-*/)
prefix=/opt/scholarlens-ocr

cmake -S "$lept" -B /build/leptonica -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=ON -DBUILD_PROG=OFF \
    -DENABLE_PNG=ON -DENABLE_ZLIB=ON -DENABLE_TIFF=OFF -DENABLE_JPEG=OFF \
    -DENABLE_GIF=OFF -DENABLE_OPENJPEG=OFF -DENABLE_WEBP=OFF
cmake --build /build/leptonica --parallel 3
cmake --install /build/leptonica

export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
cmake -S "$tess" -B /build/tesseract -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
    -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_PREFIX_PATH="$prefix" -DLeptonica_DIR="$prefix/lib/cmake/leptonica" -DBUILD_SHARED_LIBS=ON \
    -DDISABLE_CURL=ON -DDISABLE_ARCHIVE=ON -DBUILD_TRAINING_TOOLS=OFF -DBUILD_TESTS=OFF \
    -DGRAPHICS_DISABLED=ON -DOPENMP_BUILD=OFF -DDISABLE_NATIVE=ON
cmake --build /build/tesseract --parallel 3
cmake --install /build/tesseract

stage_package() {
    src=$1
    pkg=$2
    deps=$3
    root=/build/"$pkg"
    mkdir -p "$root/DEBIAN" "$root$prefix/lib" "$root/usr/share/doc/$pkg"
    cp "$src/debian/copyright" "$root/usr/share/doc/$pkg/copyright"
    version=$(dpkg-parsechangelog -l"$src/debian/changelog" -SVersion)
    source=$(dpkg-parsechangelog -l"$src/debian/changelog" -SSource)
    cat > "$root/DEBIAN/control" <<EOF
Package: $pkg
Source: $source ($version)
Version: ${version}+scholarlens1
Architecture: $(dpkg --print-architecture)
Maintainer: ScholarLens maintainers <maintainers@users.noreply.github.com>
Depends: $deps
Description: Locally rebuilt PNG-only ScholarLens OCR component from Debian sources
EOF
}

stage_package "$lept" scholarlens-leptonica "libc6, libpng16-16t64, zlib1g"
cp -a "$prefix"/lib/liblept*.so* "$root$prefix/lib/"
dpkg-deb --build "$root" /packages/leptonica.deb

stage_package "$tess" scholarlens-tesseract "scholarlens-leptonica, libc6, libstdc++6, libgcc-s1, tesseract-ocr-eng"
cp -a "$prefix"/lib/libtesseract.so* "$root$prefix/lib/"
install -D "$prefix/bin/tesseract" "$root$prefix/bin/tesseract"
install -D -m644 "$tess/tessdata/configs/tsv" "$root/usr/share/tesseract-ocr/5/tessdata/configs/tsv"
mkdir -p "$root/etc/ld.so.conf.d"
printf '%s\n' "$prefix/lib" > "$root/etc/ld.so.conf.d/scholarlens-ocr.conf"
dpkg-deb --build "$root" /packages/tesseract.deb
