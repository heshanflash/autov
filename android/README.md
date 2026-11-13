# 📱 AutoV Trader — Android APK

Mobile client for the AutoV Trader desk. The app is a **WebView client**: it loads the
dashboard served by `./run.sh` on your PC, so every scan, entry/SL/TP plan, risk rule and
the $1000 day-planner work exactly as in the browser — on your phone.

```
Phone (APK) ──Wi-Fi──▶ PC:5000 (./run.sh) ──▶ Binance API
```

## Install (sideload)
1. Copy `dist/AutoVTrader-v1.0.0.apk` to your phone.
2. Tap it → allow **Install unknown apps** for your file manager/browser.
3. Open **AutoV Trader** → enter your PC's LAN address (e.g. `http://192.168.1.10:5000`)
   → **CONNECT**. Phone and PC must be on the same Wi-Fi.

> Cleartext HTTP is enabled (`usesCleartextTraffic`) because the desk runs on your LAN.

## Build it yourself

### A) Zero-Gradle pipeline (works without Android Studio)
```bash
cd android
./build_apk.sh          # → ../dist/AutoVTrader-v1.0.0.apk
```
Requires: `bash zip python3 gh` (GitHub CLI fetches the official Android build-tools
`aapt2`, `d8`, `apksigner`, `zipalign`, `android.jar` + the ECJ compiler from pinned
public repos into `/tmp/autov-tools`). If a full JDK (`javac`) is on PATH it is used
automatically; otherwise the jdk4py runtime from PyPI is installed.

Signing key: `keystore/autov.keystore` (alias `autov`, password `autov-trader`) —
committed so future builds stay update-compatible. Treat it as low-value (sideload only).

### B) Android Studio / Gradle
Open the `android/` folder in Android Studio (AGP 7.4.2, compileSdk 34) and use
**Build ▸ Generate Signed Bundle/APK**. No third-party dependencies — pure framework code.

## App spec
| | |
|---|---|
| Package | `com.autov.trader` (v1.0.0, versionCode 1) |
| minSdk / targetSdk | 24 (Android 7.0) / 34 |
| Permissions | `INTERNET`, `ACCESS_NETWORK_STATE` only |
| Code | single `MainActivity`, UI built in code (no layout XML), ~260 lines |
| Features | saved server URL, auto-reconnect, connect/offline screen, progress bar, external-link handling, back-button = history back, rotation-safe WebView state |
