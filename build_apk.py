import os
import sys
import subprocess
import zipfile
import shutil
from sync_backend_config import sync_backend_config

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ANDROID_DIR = os.path.join(PROJECT_ROOT, "android")
APP_DIR = os.path.join(ANDROID_DIR, "app")
SRC_DIR = os.path.join(APP_DIR, "src", "main")
BUILD_DIR = os.path.join(APP_DIR, "build")
OUTPUT_DIR = os.path.join(BUILD_DIR, "outputs", "apk", "debug")

# Toolchain paths
SDK_DIR = r"F:\ADROI"
BUILD_TOOLS_DIR = os.path.join(SDK_DIR, "build-tools", "34.0.0")
AAPT2 = os.path.join(BUILD_TOOLS_DIR, "aapt2.exe")
D8 = os.path.join(BUILD_TOOLS_DIR, "d8.bat")
ZIPALIGN = os.path.join(BUILD_TOOLS_DIR, "zipalign.exe")
APKSIGNER = os.path.join(BUILD_TOOLS_DIR, "apksigner.bat")
ANDROID_JAR = os.path.join(SDK_DIR, "platforms", "android-35", "android.jar")

JDK_BIN = r"C:\Program Files\Java\jdk-17\bin"
JAVAC = os.path.join(JDK_BIN, "javac.exe")
KEYTOOL = os.path.join(JDK_BIN, "keytool.exe")

def run_proc(cmd_args, desc):
    print(f"[BUILD-APK] {desc}...")
    res = subprocess.run(cmd_args, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[ERROR] {desc} failed (code {res.returncode}):")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        sys.exit(1)
    return res.stdout

def build():
    # Đồng bộ asset địa chỉ trước khi đóng gói để APK không dùng bản IP cũ.
    sync_backend_config()
    print("=======================================================")
    print("=== BUILDING SMART PARKING ANDROID APK (OFFICIAL SDK) ===")
    print("=======================================================\n")

    os.makedirs(BUILD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    compiled_res_dir = os.path.join(BUILD_DIR, "compiled_res")
    gen_dir = os.path.join(BUILD_DIR, "gen")
    classes_dir = os.path.join(BUILD_DIR, "classes")
    dex_dir = os.path.join(BUILD_DIR, "dex")

    for d in [compiled_res_dir, gen_dir, classes_dir, dex_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    # 1. AAPT2 COMPILE RESOURCES
    res_dir = os.path.join(SRC_DIR, "res")
    res_zip = os.path.join(compiled_res_dir, "resources.zip")
    run_proc([AAPT2, "compile", "--dir", res_dir, "-o", res_zip], "1. Compiling Android Resources (AAPT2)")

    # 2. AAPT2 LINK
    manifest = os.path.join(SRC_DIR, "AndroidManifest.xml")
    assets_dir = os.path.join(SRC_DIR, "assets")
    proto_apk = os.path.join(BUILD_DIR, "base.apk")

    run_proc([
        AAPT2, "link",
        "-o", proto_apk,
        "-I", ANDROID_JAR,
        "--manifest", manifest,
        "-A", assets_dir,
        "--java", gen_dir,
        "--auto-add-overlay",
        res_zip
    ], "2. Linking Manifest, Assets & Generating R.java (AAPT2)")

    # 3. JAVAC COMPILE JAVA CODE
    java_files = []
    for root, _, files in os.walk(os.path.join(SRC_DIR, "java")):
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))
    for root, _, files in os.walk(gen_dir):
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))

    sources_txt = os.path.join(BUILD_DIR, "sources.txt")
    with open(sources_txt, "w", encoding="utf-8") as f:
        for jf in java_files:
            f.write(f'"{jf.replace(os.sep, "/")}"\n')

    run_proc([
        JAVAC, "-encoding", "UTF-8",
        "-cp", ANDROID_JAR,
        "-d", classes_dir,
        f"@{sources_txt}"
    ], "3. Compiling Java Sources (javac)")

    # 4. PACKAGE CLASSES INTO TEMPORARY JAR
    print("[BUILD-APK] Packaging compiled .class files into intermediate JAR...")
    app_jar = os.path.join(BUILD_DIR, "app.jar")
    with zipfile.ZipFile(app_jar, "w") as z:
        for root, _, files in os.walk(classes_dir):
            for f in files:
                if f.endswith(".class"):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, classes_dir)
                    z.write(full_p, rel_p)

    # 5. D8 DEX COMPILATION
    run_proc([
        "cmd", "/c", D8,
        "--lib", ANDROID_JAR,
        "--output", dex_dir,
        app_jar
    ], "4. Converting Bytecode to Dalvik Executable (D8)")

    # 6. INSERT CLASSES.DEX INTO BASE APK
    print("[BUILD-APK] 5. Adding classes.dex to APK package...")
    classes_dex = os.path.join(dex_dir, "classes.dex")
    unaligned_apk = os.path.join(BUILD_DIR, "unaligned.apk")
    shutil.copyfile(proto_apk, unaligned_apk)

    with zipfile.ZipFile(unaligned_apk, 'a') as apk_zip:
        apk_zip.write(classes_dex, "classes.dex")

    # 7. ZIPALIGN
    aligned_apk = os.path.join(BUILD_DIR, "aligned.apk")
    if os.path.exists(aligned_apk):
        os.remove(aligned_apk)
    run_proc([ZIPALIGN, "-f", "4", unaligned_apk, aligned_apk], "6. Optimizing 4-byte Alignment (zipalign)")

    # 8. GENERATE DEBUG KEYSTORE IF NOT PRESENT
    keystore = os.path.join(BUILD_DIR, "debug.keystore")
    if not os.path.exists(keystore):
        run_proc([
            KEYTOOL, "-genkey", "-v",
            "-keystore", keystore,
            "-storepass", "android",
            "-alias", "androiddebugkey",
            "-keypass", "android",
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-dname", "CN=Android Debug,O=Android,C=US"
        ], "Generating Debug Keystore")

    # 9. APKSIGNER SIGNING
    final_apk = os.path.join(OUTPUT_DIR, "app-debug.apk")
    if os.path.exists(final_apk):
        os.remove(final_apk)
    shutil.copyfile(aligned_apk, final_apk)

    run_proc([
        "cmd", "/c", APKSIGNER, "sign",
        "--ks", keystore,
        "--ks-pass", "pass:android",
        "--key-pass", "pass:android",
        "--ks-key-alias", "androiddebugkey",
        final_apk
    ], "7. Signing APK Package (apksigner)")

    apk_size = os.path.getsize(final_apk) / (1024 * 1024)
    print("\n=======================================================")
    print("SUCCESS! ANDROID APK BUILT PASS 100%!")
    print(f"File location: {final_apk}")
    print(f"File size:     {apk_size:.2f} MB")
    print("=======================================================\n")

if __name__ == "__main__":
    build()
