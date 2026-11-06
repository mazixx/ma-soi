[app]

title = Ma Soi - Lang Suong Mu
package.name = masoilangsuongmu
package.domain = vn.anlac

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,atlas,json,ttf
source.exclude_dirs = .git,.github,.venv,venv,__pycache__,bin

version = 0.1.0

requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0

# Bộ phiên bản cố định để hạn chế thay đổi ngoài ý muốn.
# Dành cho bản APK thử nghiệm cài trực tiếp.
android.api = 33
android.minapi = 23
android.ndk = 25b

# Điện thoại Android 64-bit.
android.archs = arm64-v8a

android.accept_sdk_license = True
android.debug_artifact = apk

p4a.branch = v2024.01.21


[buildozer]

log_level = 2
warn_on_root = 1
