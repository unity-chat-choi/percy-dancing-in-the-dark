Platform: Android emulator (adb, one device), package $APP_ID.
- Launch/stop: `adb shell monkey -p $APP_ID 1` / `adb shell am force-stop $APP_ID`; deeplink: `adb shell am start -a android.intent.action.VIEW -d '<url>'`
- Screenshot: `adb exec-out screencap -p > ../shots/<name>.png`
- Light / Dark: `adb shell cmd uimode night no|yes`, then force-stop + launch
- RTL: `adb shell settings put global debug.force_rtl 1` (0 to undo), then force-stop + launch; for Arabic text also switch the app language in its settings
