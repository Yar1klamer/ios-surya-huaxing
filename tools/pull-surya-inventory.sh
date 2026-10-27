#!/bin/bash
# Read-only inventory of the Poco X3 NFC (surya) over adb: live device tree, firmware and
# Android's sensor/camera configuration. Writes only on the PC, under research/ (git-ignored:
# the files are the vendor's and the DT holds the serial number). Run with the phone in
# Android or a recovery with root adb. Usage: tools/pull-surya-inventory.sh [ADB_SERIAL]
set -u
cd "$(dirname "$0")/.."
OUT=research/live-surya-android
ADB=(adb)
[ $# -ge 1 ] && ADB=(adb -s "$1")

# Refuse any device that is not a surya: other adb devices on the network are not ours.
model=$("${ADB[@]}" shell 'cat /proc/device-tree/model 2>/dev/null; cat /proc/device-tree/compatible 2>/dev/null | tr "\0" " "' | tr -d '\r')
case "$model" in
	*surya*|*SURYA*|*"POCO X3"*|*"Poco X3"*) ;;
	*) echo "pull-surya-inventory.sh: not a surya (got: $model). Pass the phone's serial as argument." >&2; exit 1 ;;
esac
echo "device: $model"

mkdir -p "$OUT/device-tree" "$OUT/fw" "$OUT/camera" "$OUT/sensors" "$OUT/info"
# Live device tree (what the running kernel was given, DTBO fixups applied).
"${ADB[@]}" pull /proc/device-tree/. "$OUT/device-tree/" >/dev/null 2>&1 || echo "device-tree: pull failed"
echo "device-tree: $(find "$OUT/device-tree" -type f | wc -l) files"

pull() { # DIR SOURCE...  (missing files are reported, not fatal)
	local dir=$1; shift
	for f in "$@"; do "${ADB[@]}" pull "$f" "$dir/" >/dev/null 2>&1 || echo "missing: $f"; done
}
# GPU (Adreno 618), touch, DSPs. Wildcards are expanded on the phone.
for pat in /vendor/firmware/a630_sqe.fw /vendor/firmware/a618_gmu.bin '/vendor/firmware/a615_zap.*' \
           '/vendor/firmware/novatek*' '/vendor/firmware/*tianma*' '/vendor/firmware/*nt36*' \
           '/vendor/firmware_mnt/image/adsp.*' '/vendor/firmware_mnt/image/slpi.*' '/vendor/firmware_mnt/image/cdsp.*' \
           '/vendor/firmware_mnt/image/modem.*' '/vendor/firmware_mnt/image/venus.*'; do
	for f in $("${ADB[@]}" shell "ls $pat 2>/dev/null" | tr -d '\r'); do pull "$OUT/fw" "$f"; done
done
# Camera sensor modules/tuning and Android's sensor registry (tells which sensors exist and on which bus).
for f in $("${ADB[@]}" shell 'ls /vendor/lib64/camera/com.qti.sensormodule.*.bin /vendor/lib64/camera/com.qti.tuned.*.bin 2>/dev/null' | tr -d '\r'); do pull "$OUT/camera" "$f"; done
for d in /vendor/etc/sensors /vendor/etc/camera /mnt/vendor/persist/sensors; do
	"${ADB[@]}" pull "$d" "$OUT/sensors/" >/dev/null 2>&1 || echo "missing: $d"
done
# Plain-text facts: partitions, loaded modules, I2C/SPI devices, sensor list.
"${ADB[@]}" shell 'ls -l /dev/block/bootdevice/by-name; cat /proc/cpuinfo; cat /proc/iomem; cat /proc/interrupts; ls /sys/bus/i2c/devices /sys/bus/spi/devices /sys/class/sensors /sys/bus/iio/devices 2>&1; dumpsys sensorservice 2>/dev/null | head -150; getprop' \
	> "$OUT/info/live.txt" 2>&1
echo "done: $OUT (do not commit; contains identifiers)"
