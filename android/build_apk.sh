#!/usr/bin/env bash
# =====================================================================
# AutoV Trader — zero-Gradle APK builder
# Builds dist/AutoVTrader-v1.0.0.apk from app/src/main using:
#   aapt2 + d8 + apksigner (Android build-tools) + ECJ/javac
# Tools are auto-provisioned into $TOOLS_DIR (default /tmp/autov-tools).
# Requires: bash, zip, python3, gh  (GitHub CLI)  — no Android Studio needed.
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

TOOLS="${TOOLS_DIR:-/tmp/autov-tools}"
JDKPY="${JDKPY_DIR:-/tmp/jdk4py}"
SRC="app/src/main"
OUT="build"
VER="1.0.0"
VCODE=1
APK_NAME="AutoVTrader-v${VER}.apk"

# pinned tool sources (committed copies of official Android SDK build-tools)
AAPT2_BLOB="ItzVladik/android-sdk/c2d8b2aff2b032379961c276a41e64f27a75fbbe"
ZIPALIGN_BLOB="ItzVladik/android-sdk/e159fdf8f073edd3a7b9ada37d5be21e95163cf7"
D8_JAR_BLOB="ItzVladik/android-sdk/b4c7be9ef7baed425fb53113c06b8be9cf9178ea"
APKSIGNER_JAR_BLOB="ItzVladik/android-sdk/f6f77e0585b3e92e317ef2012db71045c200b507"
ANDROID_JAR_BLOB="Sable/android-platforms/4d76f1707c0640ff5119af5570619d601779a866"
LIBCXX_BLOB="MasElonn/ApkUtility-GUI/454cc1074eb3b3006c580f6b3fbba188c01ea55f"
ECJ_JAR_BLOB="SciAps/nexus/$(gh api "repos/SciAps/nexus/git/trees/HEAD?recursive=1" \
    --jq '.tree[]?|select(.path=="org/eclipse/jdt/core/compiler/ecj/4.6.1/ecj-4.6.1.jar")|.sha' 2>/dev/null || true)"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

blob_to() { # repo sha dest
    [ -s "$3" ] && return 0
    log "download $(basename "$3")"
    gh api "repos/$1/git/blobs/$2" --jq .content | base64 -d > "$3.tmp"
    mv "$3.tmp" "$3"
}

provision_tools() {
    mkdir -p "$TOOLS/bin" "$TOOLS/lib"
    command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required to fetch build tools"; exit 1; }
    local r s
    r=${AAPT2_BLOB%/*};       s=${AAPT2_BLOB##*/};       blob_to "$r" "$s" "$TOOLS/bin/aapt2"
    r=${ZIPALIGN_BLOB%/*};    s=${ZIPALIGN_BLOB##*/};    blob_to "$r" "$s" "$TOOLS/bin/zipalign"
    r=${D8_JAR_BLOB%/*};      s=${D8_JAR_BLOB##*/};      blob_to "$r" "$s" "$TOOLS/lib/d8.jar"
    r=${APKSIGNER_JAR_BLOB%/*}; s=${APKSIGNER_JAR_BLOB##*/}; blob_to "$r" "$s" "$TOOLS/lib/apksigner.jar"
    r=${ANDROID_JAR_BLOB%/*}; s=${ANDROID_JAR_BLOB##*/}; blob_to "$r" "$s" "$TOOLS/android.jar"
    r=${ECJ_JAR_BLOB%/*};     s=${ECJ_JAR_BLOB##*/};     blob_to "$r" "$s" "$TOOLS/lib/ecj.jar"
    r=${LIBCXX_BLOB%/*};      s=${LIBCXX_BLOB##*/};      blob_to "$r" "$s" "$TOOLS/lib/libc++.so"
    chmod +x "$TOOLS/bin/aapt2" "$TOOLS/bin/zipalign"
    export LD_LIBRARY_PATH="$TOOLS/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
}

provision_java() {
    # prefer a real JDK on PATH, else the jdk4py runtime from PyPI
    if command -v java >/dev/null 2>&1 && command -v javac >/dev/null 2>&1; then
        JAVA_BIN=$(command -v java); JAVAC_BIN=$(command -v javac); KEYTOOL_BIN=$(command -v keytool || true)
        return 0
    fi
    if [ ! -x "$JDKPY/jdk4py/java-runtime/bin/java" ]; then
        log "install jdk4py runtime (PyPI)"
        pip3 install -q --target "$JDKPY" --no-deps "jdk4py==17.0.9.2"
    fi
    JAVA_BIN="$JDKPY/jdk4py/java-runtime/bin/java"
    KEYTOOL_BIN="$JDKPY/jdk4py/java-runtime/bin/keytool"
    JAVAC_BIN=""   # fall back to ECJ
}

compile_java() {
    mkdir -p "$OUT/classes"
    local files
    files=$(find "$SRC/java" -name '*.java')
    if [ -n "$JAVAC_BIN" ]; then
        log "javac"
        "$JAVAC_BIN" -source 8 -target 8 -Xlint:-options \
            -bootclasspath "$TOOLS/android.jar" -classpath "$TOOLS/android.jar" \
            -d "$OUT/classes" $files
    else
        log "ecj (Eclipse compiler)"
        "$JAVA_BIN" -jar "$TOOLS/lib/ecj.jar" -1.8 -warn:none -proc:none \
            -bootclasspath "$TOOLS/android.jar" -classpath "$TOOLS/android.jar" \
            -d "$OUT/classes" $files
    fi
}

build() {
    rm -rf "$OUT"; mkdir -p "$OUT"

    # icons (idempotent)
    if [ ! -f "$SRC/res/mipmap-xxxhdpi/ic_launcher.png" ]; then
        log "generate launcher icons"
        python3 make_icons.py
    fi

    log "aapt2 compile + link"
    "$TOOLS/bin/aapt2" compile --dir "$SRC/res" -o "$OUT/res.zip"
    "$TOOLS/bin/aapt2" link -o "$OUT/base.apk" -I "$TOOLS/android.jar" \
        --manifest "$SRC/AndroidManifest.xml" "$OUT/res.zip" \
        --min-sdk-version 24 --target-sdk-version 34 \
        --version-code "$VCODE" --version-name "$VER" \
        --auto-add-overlay

    compile_java

    log "d8 -> classes.dex"
    (cd "$OUT/classes" && zip -qr ../classes.jar .)
    "$JAVA_BIN" -cp "$TOOLS/lib/d8.jar" com.android.tools.r8.D8 \
        --release --min-api 24 --lib "$TOOLS/android.jar" \
        --output "$OUT" "$OUT/classes.jar"

    log "inject classes.dex"
    (cd "$OUT" && zip -q base.apk classes.dex)

    log "zipalign"
    "$TOOLS/bin/zipalign" -f 4 "$OUT/base.apk" "$OUT/aligned.apk"

    log "sign (v1+v2, keystore android/keystore/autov.keystore)"
    mkdir -p keystore
    if [ ! -f keystore/autov.keystore ]; then
        "$KEYTOOL_BIN" -genkeypair -keystore keystore/autov.keystore -alias autov \
            -keyalg RSA -keysize 2048 -validity 10000 \
            -storepass autov-trader -keypass autov-trader \
            -dname "CN=AutoV Trader, OU=AutoV, O=AutoV, L=Singapore, C=SG"
    fi
    "$JAVA_BIN" -jar "$TOOLS/lib/apksigner.jar" sign \
        --ks keystore/autov.keystore \
        --ks-pass pass:autov-trader --key-pass pass:autov-trader \
        --out "$OUT/$APK_NAME" "$OUT/aligned.apk"

    log "verify signature"
    "$JAVA_BIN" -jar "$TOOLS/lib/apksigner.jar" verify --verbose "$OUT/$APK_NAME" | head -6

    mkdir -p ../dist
    cp "$OUT/$APK_NAME" "../dist/$APK_NAME"
    local sha
    sha=$(sha256sum "../dist/$APK_NAME" | cut -d' ' -f1)
    log "DONE → dist/$APK_NAME"
    log "size:   $(du -h "../dist/$APK_NAME" | cut -f1)"
    log "sha256: $sha"
}

log "provision tools"
provision_tools
provision_java
build
