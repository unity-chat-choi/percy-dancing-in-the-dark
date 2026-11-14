Platform: iOS simulator (booted), bundle id $APP_ID. Time budget: 35 minutes, then the run is killed (keep verdict.json up to date).
Scope on iOS: the JS is the same code Android runs, and Android runs every functional test case in parallel. On iOS check only:
- the look of every screen in scope in light, dark and RTL vs Figma (layout, safe area / notch, fonts, clipping, icons);
- test cases or bugs that are iOS-specific (safe area, native modules, iOS-only screens) or that name iOS.
List the other functional cases as "Android kiểm" in the report (not "Không test được"). Do not repeat them here.
- Theme and language are settings INSIDE the app (Profile → Settings), not the OS: `simctl ui appearance` and AppleLanguages change nothing. Run the ready flows in ../ctx/flows/ios-*.yaml first.
- Deeplink: staging scheme is `uni-stag://app/...` (`xcrun simctl openurl booted <url>`); the first one shows a system "Open in …" prompt: maestro tapOn "Open".
- Taps: `tapOn` by text often misses custom touchables; use an id from `maestro hierarchy`, else absolute pixel points from the screenshot (1206x2622), never percentages.
- Launch/stop: `xcrun simctl launch booted $APP_ID` / `xcrun simctl terminate booted $APP_ID`
- Screenshot: `xcrun simctl io booted screenshot ../shots/<name>.png`
- Small copy to Read: `sips -Z 900 ../shots/<name>.png --out /tmp/v-<name>.png`
