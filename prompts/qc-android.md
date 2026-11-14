Platform: Android emulator (adb, one device), package $APP_ID. Time budget: 45 minutes, then the run is killed (keep verdict.json up to date).
Scope on Android: every functional test case, plus light/dark/RTL vs Figma (iOS only re-checks the look). Theme and language are app settings: run the ready flows in ../ctx/flows/android-*.yaml first.
- Launch/stop: `adb shell monkey -p $APP_ID 1` / `adb shell am force-stop $APP_ID`; deeplink: `adb shell am start -a android.intent.action.VIEW -d '<url>'`
- Screenshot: `adb exec-out screencap -p > ../shots/<name>.png`
- `uimode night` and `debug.force_rtl` do NOT change this app (it uses its own settings); Arabic = RTL.
- Small copy to Read: `convert ../shots/<name>.png -resize 900x900 /tmp/v-<name>.png` (or `python3 -c` with PIL if convert is missing)
