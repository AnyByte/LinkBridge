#!/usr/bin/env bash
# Package dist/LinkBridge.app into dist/LinkBridge-v<version>.dmg using hdiutil.
#
# Usage:
#   ./scripts/build_dmg.sh <version>
#
# Requires that ./scripts/build_app.sh has already produced dist/LinkBridge.app.
# The resulting .dmg, when mounted, shows a Finder window with LinkBridge.app
# next to a symlink to /Applications so the user can drag-to-install.

set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    echo "usage: $0 <version>" >&2
    exit 2
fi

APP="dist/LinkBridge.app"
DMG="dist/LinkBridge-v${VERSION}.dmg"

if [[ ! -d "$APP" ]]; then
    echo "error: $APP not found. Run ./scripts/build_app.sh first." >&2
    exit 1
fi

rm -f "$DMG"

# Build the contents of the disk image in a temp directory: the .app plus a
# symlink to /Applications so the user can drag-to-install visually.
STAGE=$(mktemp -d -t linkbridge-dmg)
trap 'rm -rf "$STAGE"' EXIT

ditto "$APP" "$STAGE/LinkBridge.app"
ln -s /Applications "$STAGE/Applications"

hdiutil create \
    -volname "LinkBridge" \
    -srcfolder "$STAGE" \
    -ov \
    -format UDZO \
    "$DMG" >/dev/null

echo "Built: $DMG"
ls -lh "$DMG"
