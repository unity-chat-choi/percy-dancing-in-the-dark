Platform: iOS simulator (booted), bundle id $APP_ID.
- Launch/stop: `xcrun simctl launch booted $APP_ID` / `xcrun simctl terminate booted $APP_ID`; deeplink: `xcrun simctl openurl booted <url>`
- Screenshot: `xcrun simctl io booted screenshot ../shots/<name>.png`
- Light / Dark: `xcrun simctl ui booted appearance light|dark`
- RTL: `xcrun simctl spawn booted defaults write -g AppleLanguages -array ar`, then terminate + launch (set back to `en` after)
- Small copy to Read: `sips -Z 900 ../shots/<name>.png --out /tmp/v-<name>.png`
