#!/bin/bash
# Save / restore the app's own data (theme, language, onboarding done…) so QC switches light / dark / RTL by
# swapping files (seconds) instead of tapping through Settings (each Maestro call costs 60-90 s on iOS).
# Names: <ios|android>-<light|dark>-<en|ar|vi…>, e.g. ios-dark-ar = dark + Arabic (RTL).
# Usage (by QC, any cwd): app-state.sh save|load|list <name>   Env: APP_ID
# States live in ctx/states (downloaded) and ctx/states-new (saved this run; uploaded after QC).
set -euo pipefail
cmd=$1; name=${2:-}
CTX=$(cd "$(dirname "$0")/../../ctx" && pwd); mkdir -p "$CTX/states" "$CTX/states-new"
if [ "$cmd" = list ]; then ls "$CTX/states" "$CTX/states-new" 2>/dev/null | grep '\.tgz$' | sed 's/\.tgz$//' | sort -u; exit 0; fi
[ -n "$name" ] || { echo "usage: app-state.sh save|load|list <name>"; exit 2; }
case "$name" in ios-*) P=ios ;; android-*) P=android ;; *) echo "name must start with ios- or android-"; exit 2 ;; esac
file="$CTX/states-new/$name.tgz"; [ "$cmd" = load ] && { [ -s "$file" ] || file="$CTX/states/$name.tgz"; [ -s "$file" ] || { echo "no state $name"; exit 1; }; }

if [ "$P" = ios ]; then
  C=$(xcrun simctl get_app_container booted "$APP_ID" data)
  xcrun simctl terminate booted "$APP_ID" 2>/dev/null || true
  if [ "$cmd" = save ]; then
    tar czf "$file" -C "$C" --exclude ./Library/Caches --exclude ./tmp .
  else
    find "$C" -mindepth 1 -maxdepth 1 ! -name Library -exec rm -rf {} +
    find "$C/Library" -mindepth 1 -maxdepth 1 ! -name Caches -exec rm -rf {} + 2>/dev/null || true
    tar xzf "$file" -C "$C"
  fi
  xcrun simctl launch booted "$APP_ID" >/dev/null
else
  D=/data/data/$APP_ID
  adb root >/dev/null 2>&1 || true; adb wait-for-device
  adb shell am force-stop "$APP_ID"
  if [ "$cmd" = save ]; then
    adb shell "cd $D && tar czf /data/local/tmp/state.tgz --exclude=./cache --exclude=./code_cache --exclude=./lib ."
    adb pull /data/local/tmp/state.tgz "$file" >/dev/null
  else
    adb push "$file" /data/local/tmp/state.tgz >/dev/null
    adb shell "u=\$(stat -c %u $D); cd $D && rm -rf files databases shared_prefs no_backup app_* && tar xzf /data/local/tmp/state.tgz && chown -R \$u:\$u $D && restorecon -R $D"
  fi
  adb shell monkey -p "$APP_ID" 1 >/dev/null 2>&1
fi
echo "$cmd $name ok"
