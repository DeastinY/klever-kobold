#!/bin/sh
# Wraps dist/kobold (the PyInstaller folder from deploy/windows/kobold.spec)
# and Ollama's standalone macOS build into "dist/The Klever Kobold.app", ad-hoc
# signed, then into dist/KleverKobold-macOS-<arch>.dmg. Run on a Mac:
#
#     uv run --with pyinstaller pyinstaller --noconfirm deploy/windows/kobold.spec
#     sh deploy/macos/build_app.sh 1.2.3
#
# Ad-hoc signing is what lets an arm64 binary run at all; it is not notarization,
# so Gatekeeper still asks the user to allow the app once (docs/running.md).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
VERSION=${1:-0.0.0}
ARCH=$(uname -m)
APP="$ROOT/dist/The Klever Kobold.app"
DMG="$ROOT/dist/KleverKobold-macOS-$ARCH.dmg"

echo "app     $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp -R "$ROOT/dist/kobold" "$APP/Contents/Resources/kobold"
cp "$HERE/launcher.sh" "$APP/Contents/MacOS/launcher"
chmod +x "$APP/Contents/MacOS/launcher"
cp "$ROOT/deploy/icon/kobold.icns" "$APP/Contents/Resources/kobold.icns"
sed "s/@VERSION@/$VERSION/g" "$HERE/Info.plist" > "$APP/Contents/Info.plist"

echo "ollama  standalone build, into Resources/kobold/ollama/"
mkdir -p "$ROOT/build"
curl -fsSL -o "$ROOT/build/ollama-darwin.tgz" https://ollama.com/download/ollama-darwin.tgz
mkdir -p "$APP/Contents/Resources/kobold/ollama"
tar -xzf "$ROOT/build/ollama-darwin.tgz" -C "$APP/Contents/Resources/kobold/ollama"
"$APP/Contents/Resources/kobold/ollama/ollama" --version

echo "sign    ad-hoc"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "dmg     $DMG"
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "The Klever Kobold" -srcfolder "$STAGE" -ov -format UDZO -quiet "$DMG"
ls -la "$DMG"
