#!/bin/bash
# JS-only branch on iOS: re-bundle the JS into a prebuilt staging .app instead of a 25-min xcodebuild.
# Same steps as react-native-xcode.sh (Release + Hermes). Simulator apps are unsigned, so editing the .app is fine.
# Usage (from the RN repo root): ios-js-swap.sh <path/to/App.app>
set -euo pipefail
APP="$1"
HERMESC=ios/Pods/hermes-engine/destroot/bin/hermesc
[ -x "$HERMESC" ] || HERMESC=node_modules/react-native/sdks/hermesc/osx-bin/hermesc
T=$(mktemp -d)
node node_modules/react-native/cli.js bundle --entry-file index.js --platform ios --dev false --minify false \
  --reset-cache --bundle-output "$T/main.js" --assets-dest "$APP" >"$T/bundle.log" 2>&1 \
  || { tail -20 "$T/bundle.log" >&2; exit 1; }
"$HERMESC" -emit-binary -max-diagnostic-width=80 -O -out "$APP/main.jsbundle" "$T/main.js"
rm -rf "$T"
