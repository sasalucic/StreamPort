# Development, building and testing

## Server

Use Python 3.11+, FFmpeg/ffprobe, and `cryptography`. In a virtual environment in `server/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_*.py'
```

Use Node.js for pure DOM, UI, and syntax checks:

```bash
for test in tests/*.cjs; do node "$test"; done
for f in static/*.js; do node --check "$f"; done
```

Some JS integration tests need optional packages (such as jsdom or Playwright) not declared as mandatory runtime dependencies; install those tools **only for local testing**. Do not point tests at your personal media library or production database. Tests simulate upstream API calls; **passing mocks does not prove a live Seerr/qBittorrent deployment works**.

## Android phone / Android TV

Requirements: Java/JDK 17, Android SDK 35, Android Gradle Plugin 8.7.3/Gradle 8.9. Open `android/` or `android-tv/` in Android Studio, or build with:

```bash
cd android       # or android-tv
./gradlew assembleDebug
```

Output: `app/build/outputs/apk/debug/app-debug.apk`. This debug APK has the standard debug signing identity and is not suitable as a production distribution.

The optional offline `build-sdk.sh` (using platform `android-35` and build tools `35.0.0`) produces an APK using **your own private keystore**, never a bundled project key. You must set:

```bash
export JAVA_HOME=/path/to/jdk-17
export ANDROID_JAR=/path/to/android-sdk/platforms/android-35/android.jar
export ANDROID_BUILD_TOOLS=/path/to/android-sdk/build-tools/35.0.0
export STREAMPORT_KEYSTORE=/path/outside/repo/to/your-release.jks
export STREAMPORT_KEY_ALIAS=your-key-alias
# Supply the following two values securely in your shell/session. Do not write them in repository files.
export STREAMPORT_KEYSTORE_PASSWORD='...'
export STREAMPORT_KEY_PASSWORD='...'
bash build-sdk.sh
```

Keep signing keys outside Git. `apksigner` reads passwords from environment, not hardcoded command-line passwords. New APKs use `org.streamport.mobile` and `org.streamport.tv` IDs; they are **not in-place upgrades** over previously distributed private builds. Build/test on devices you own.

JVM-only tests:

```bash
# From android/
mkdir -p build-tests
javac -d build-tests app/src/main/java/org/streamport/mobile/ServerAddress.java tests/ServerAddressTest.java
java -cp build-tests ServerAddressTest

# From android-tv/
mkdir -p build-tests
javac -d build-tests app/src/main/java/org/streamport/tv/ServerAddress.java tests/ServerAddressTest.java
java -cp build-tests ServerAddressTest
javac -d build-tests app/src/main/java/org/streamport/tv/SessionCookie.java tests/SessionCookieTest.java
java -cp build-tests org.streamport.tv.SessionCookieTest
```

## Roku

```bash
cd roku
npm ci
npm run build
npm test
```

This packages Roku source via BrighterScript; sideload through the developer interface on your own Roku device. Off-device BrightScript tests are not a substitute for real Roku playback and navigation validation.

## Code and privacy rules

Prefer small patches with tests. Never include host addresses, personal usernames, account database files, live tokens, media libraries, signing keys or private release packages. Test with reserved documentation addresses (RFC 5737) only. Review the [security guide](SECURITY.md) before publishing.
