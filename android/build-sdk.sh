#!/usr/bin/env bash
# Offline APK build using official Android SDK tools; no Gradle dependencies.
set -euo pipefail
cd "$(dirname "$0")"
: "${ANDROID_JAR:?Set ANDROID_JAR to platforms/android-35/android.jar}"
: "${ANDROID_BUILD_TOOLS:?Set ANDROID_BUILD_TOOLS to build-tools/35.0.0}"
: "${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
output_dir="$PWD/build-sdk"
mkdir -p "$output_dir"/{generated,classes,dex}
"$ANDROID_BUILD_TOOLS/aapt2" compile --dir app/src/main/res -o "$output_dir/resources.zip"
python3 - "$output_dir" <<'PYMANIFEST'
import sys,xml.etree.ElementTree as ET
from pathlib import Path
ET.register_namespace('android','http://schemas.android.com/apk/res/android')
tree=ET.parse('app/src/main/AndroidManifest.xml');tree.getroot().set('package','org.streamport.mobile')
tree.write(Path(sys.argv[1])/'AndroidManifest.xml',encoding='utf-8',xml_declaration=True)
PYMANIFEST
"$ANDROID_BUILD_TOOLS/aapt2" link -o "$output_dir/base.apk" -I "$ANDROID_JAR" --manifest "$output_dir/AndroidManifest.xml" --java "$output_dir/generated" --min-sdk-version 26 --target-sdk-version 35 --version-code 11 --version-name 1.7.0 -A app/src/main/assets "$output_dir/resources.zip"
find app/src/main/java "$output_dir/generated" -name '*.java' > "$output_dir/sources.txt"
"$JAVA_HOME/bin/javac" -encoding UTF-8 -source 17 -target 17 -classpath "$ANDROID_JAR" -d "$output_dir/classes" @"$output_dir/sources.txt"
"$JAVA_HOME/bin/jar" --create --file "$output_dir/classes.jar" -C "$output_dir/classes" .
"$ANDROID_BUILD_TOOLS/d8" --lib "$ANDROID_JAR" --min-api 26 --output "$output_dir/dex" "$output_dir/classes.jar"
python3 - "$output_dir" <<'PY'
import sys,zipfile,shutil
from pathlib import Path
p=Path(sys.argv[1]);shutil.copyfile(p/'base.apk',p/'unsigned.apk')
with zipfile.ZipFile(p/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as z:
 for f in (p/'dex').glob('*.dex'):z.write(f,f.name)
PY
"$ANDROID_BUILD_TOOLS/zipalign" -f -p 4 "$output_dir/unsigned.apk" "$output_dir/aligned.apk"
# Use your own signing key kept OUTSIDE the repository. No default credentials.
: "${STREAMPORT_KEYSTORE:?Set STREAMPORT_KEYSTORE to your private signing keystore path}"
: "${STREAMPORT_KEY_ALIAS:?Set STREAMPORT_KEY_ALIAS to your private key alias}"
: "${STREAMPORT_KEYSTORE_PASSWORD:?Set STREAMPORT_KEYSTORE_PASSWORD (do not commit)}"
: "${STREAMPORT_KEY_PASSWORD:?Set STREAMPORT_KEY_PASSWORD (do not commit)}"
[[ -f "$STREAMPORT_KEYSTORE" ]] || { echo 'Signing keystore file not found.' >&2; exit 1; }
"$ANDROID_BUILD_TOOLS/apksigner" sign \
  --ks "$STREAMPORT_KEYSTORE" --ks-key-alias "$STREAMPORT_KEY_ALIAS" \
  --ks-pass env:STREAMPORT_KEYSTORE_PASSWORD --key-pass env:STREAMPORT_KEY_PASSWORD \
  --out "$output_dir/StreamPort-Android.apk" "$output_dir/aligned.apk"
"$ANDROID_BUILD_TOOLS/apksigner" verify --verbose "$output_dir/StreamPort-Android.apk"
