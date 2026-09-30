#!/bin/sh
# Wraps dist/kobold (the PyInstaller folder from deploy/windows/kobold.spec)
# into dist/KleverKobold-<arch>.AppImage. Run on Linux:
#
#     uv run --with pyinstaller --with zstandard pyinstaller --noconfirm deploy/windows/kobold.spec
#     sh deploy/linux/build_appimage.sh 1.2.3
#
# Ollama is not inside: its Linux build is 1.4 GB, so the kobold fetches it
# into the data directory on first start instead (`setup --install-ollama`),
# which is why the freeze above carries zstandard, the archive's compression.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
VERSION=${1:-0.0.0}
ARCH=$(uname -m)
APPDIR="$ROOT/build/AppDir"
OUT="$ROOT/dist/KleverKobold-$ARCH.AppImage"

echo "appdir  $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -R "$ROOT/dist/kobold" "$APPDIR/usr/bin/kobold"
cp "$HERE/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp "$HERE/kobold.desktop" "$APPDIR/kobold.desktop"
cp "$ROOT/deploy/icon/kobold.png" "$APPDIR/kobold.png"

TOOL="$ROOT/build/appimagetool-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
  echo "tool    appimagetool"
  curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
  chmod +x "$TOOL"
fi
echo "image   $OUT"
rm -f "$OUT"
# Extract-and-run: no FUSE needed on the build machine.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" VERSION="$VERSION" "$TOOL" --no-appstream "$APPDIR" "$OUT"
ls -la "$OUT"
