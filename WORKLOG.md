# WORKLOG — iOS 16 на Poco X3 NFC (surya)

Рабочий журнал. Новые записи сверху. Наблюдения (проверено на железе/CI) отделены от гипотез.
Подробный технический журнал прежних агентов — `NOTES.md`.

## Цели владельца (2026-10-27)
Довести порт до максимума: лаги, все ядра, GPU, ядро как у sweet, датчики, камера и остальное.
Источники: `dipa-studio/ios-sweet` (база), `oosexgang/hackios-xnu-kernel` (HakiOS, POCO X5 Pro: GPU через Mesa,
звук, Wi-Fi, камеры, 8 ядер). Клоны лежат в `research/` (в git не попадают).

## 2026-10-28 — GUI на 8 ядрах и план следующего этапа
- `boot-smp8.img`: загрузка до экрана ~1 мин 27 с (наблюдение владельца; на 6 ядрах было ~1 мин, замер на глаз). Отклик быстрее, чем на 6 ядрах, "но вообще не очень"; работа **нестабильна** (подробности сбоев не собраны).
- Владелец ставит приоритет: GPU, датчики, кнопки. Указал `oosexgang/hackios-xnu-kernel` как источник.
- Разбор HakiOS (POCO X5 Pro, SM7325, другой SoC, поэтому адреса и регистры нельзя копировать без проверки): ядро в `xnu/files/bsd/dev/` — `hakios.buttons.c` (кнопки через SPMI-арбитр, только чтение), `hakios.adreno.c` (GPU, A642L), `hakios.cpufreq.c`, `hakios.adsp.c` (батарея/датчики через ADSP), `hakios.camera.c`. Лицензия: ядро — APSL 2.0, остальное — MIT; при переносе сохранять заголовки и указывать источник.
- Кнопки на surya (из живого DT, наблюдение): SPMI-арбитр `qcom,spmi-pmic-arb` @0xc440000 (core 0x1100, chnls 0xc600000, obsrvr 0xe600000, intr 0xe700000, cnfg 0xc40a000), PMIC pm6150@0 и pm6150l@4, у обоих `qcom,power-on@800`; `gpio_keys` содержит только vol_up (GPIO 2, code 0x73). Питание и vol_down, по аналогии с HakiOS, вероятно PON KPDPWR/RESIN (гипотеза, проверить в DT/на железе).
- Нестабильность 8 ядер: гипотеза — XNU видит A55 и A76 как однородные и нет cpufreq; не проверено. Пока основной образ — `boot-smp6.img`.
- Порядок (предложение): 1) кнопки (малый риск, чтение), 2) GPU по этапам G1–G7, 3) датчики через ADSP/SSC, 4) cpufreq/стабильность параллельно.

## 2026-10-28 — 8/8 ядер (с A76) на железе (наблюдение, фото владельца)
- `boot-smp8-diag.img` (sha256 503881e6...), `fastboot boot` 0.454s/5.094s. Консоль: `requested=8 selected=8`,
  cpu=6 (mpidr 0x600) и cpu=7 (0x700): `PSCI CPU_ON rc=0`, `came alive; SGI1 OK`, итог **`8/8 CPUs initialized, SGI1 verified`**.
- Тот же `gPanicBase` warning, загрузка идёт дальше. НЕ проверено: GUI на 8 ядрах (`boot-smp8.img`), стабильность/нагрев,
  отклик. Ядра A76 и A55 сидят в одном "homogeneous" кластере XNU (планировщик не знает про big.LITTLE) — возможна неравномерность.

## 2026-10-28 — GUI на 6 ядрах: время загрузки 15 мин -> ~1 мин (наблюдение владельца)
- `boot-smp6.img` (sha256 983312d5...), `fastboot boot`: дисплей работает, система грузится ~1 минуту (раньше ~15 мин на одном ядре).
- Лаги остаются, но заметно меньше. Вероятные причины остатка (гипотезы): рендер на CPU (GPU не используется), частоты CPU
  оставлены как есть после ABL (нет cpufreq-драйвера; у HakiOS это `hakios.cpufreq.c`), A76-ядра (6,7) не включены.
- Подготовлены `boot-smp8.img` (GUI, cpus=8) и `boot-smp8-diag.img` (консоль) в `research/images/`; не загружались.
- Следующий шаг: проверить cpus=8, затем cpufreq по образцу HakiOS (проверить источник частот на surya), затем GPU.

## 2026-10-28 — SMP на железе: 6 ядер подняты (наблюдение, фото владельца)
- Образ `boot-smp6-diag.img` (sha256 afefb95a...), `fastboot boot`, Sending 0.450s / Booting 5.093s. Без записи разделов.
  (Телефон был в fastbootd из recovery — `boot` там не работает; `fastboot reboot bootloader` помог.)
- Фото консоли: `SWEET CPU: requested=6 selected=6 (limit=8)`, для cpu=1..5 `PSCI CPU_ON rc=0` (target 0x100..0x500,
  entry_pa=0x101492000), `cpu=N mpidr=0x.. came alive; SGI1 OK`, итог **`6/6 CPUs initialized, SGI1 verified`**.
  Ядро дальше грузится, потом отчёт тача (повторяется каждые 20 с, launchd на паузе — это диагностический профиль).
- Видно также `debug_log_init: Error!! gPanicBase is still not initialized` (дважды) и `kdp_core zlib memory 0x8000`;
  загрузка при этом продолжилась (отчёт тача появляется позже). Это сообщение уже встречалось раньше; область лога паники
  намеренно убрана из ADT (см. запись про слияние), оставлено как TODO.
- НЕ проверено: A76 (cpus=7..8), отклик GUI/лаги (нужен `boot-smp6.img`), стабильность под нагрузкой.

## 2026-10-28 — SMP-образы собраны (на хосте project-make, не загружены)
- Linux-хост `burmalda@192.168.1.112` (4 ядра, 7 ГБ): вход по отдельному ключу `~/.ssh/id_claude_surya` (без фразы;
  добавлен владельцем). Есть clang, aarch64-linux-gnu-gcc, dtc, mkbootimg (~/mkbootimg), старая сборка в ~/surya-build.
- Ядро = артефакт CI-рана 39571436818 (d8281fa), sha256 22de5055...a37c; совпадает с ~/surya-build/kernel.development.surya.
  Новая сборка ядра не нужна: SMP-патчи 0065/0078 уже внутри, менялись только ADT и cmdline.
- Рабочая копия `~/surya-smp` (клон форка f1ebefc; локально убран флаг `--no-warn-rwx-segments` в shim/build.sh — старый ld).
  61 тест OK. ADT: `surya.py --apple-root --cpus 6` (RAM 0x100000000+0xfc000000, evidence из ~/surya-build/live).
- Образы (на ПК `research/images/`): `boot-smp6-diag.img` (touch-diagnostic: консоль видна, `cpus=6`, тач-прошивка Tianma)
  sha256 afefb95a...; `boot-smp6.img` (чистый GUI, консоль выключена) sha256 983312d5....
- Ожидаем в логе: `SWEET CPU: cpu=N mpidr=0x.. came alive; SGI1 OK` для cpu 0..5. НЕ загружено на телефон, результат неизвестен.

## 2026-10-28 — фаза 0 выполнена (Poco в recovery, adb 5d1eea87)
**Наблюдения** (данные в `research/live-surya-android/`, в git не идут)
- Телефон: POCO X3 NFC, vendor Android 12 MIUI 14 (surya_eea), recovery fox_surya. Динамические разделы целы (`super`=sda15).
- Рядом в adb висит чужое устройство 192.168.1.124 (раньше колонка, теперь Nexus 4): не трогаю, скрипт работает по серийнику.
- Скрипт `pull-surya-inventory.sh`: DT (18816 файлов), разделы, /proc/iomem, interrupts. Починил: проверка по `ro.product.device`
  (в recovery DT-модель общая "IDP"), `MSYS_NO_PATHCONV` (Git Bash ломал /vendor), NUL-байт в `tr`.
- /vendor в recovery пуст: смонтировал вручную **только на чтение** (loop `-r` на sda15 со смещением из `lpdump`;
  OFFSET считать на ПК: в toybox `$((...))` переполняется) в `/mnt/vend_ro`, `modem`(sde4, vfat)->`/mnt/modem_ro`,
  `dsp`(sde9)->`/mnt/dsp_ro`. Ничего не записано. Потом `losetup -d /dev/block/loop0` и umount, либо перезагрузка.
- **CPU: подтверждено.** DT: 8 ядер, `reg` = 0x000..0x700 (Aff1 = номер ядра), enable-method psci, метод `smc`,
  ядра 0–5 A55, 6–7 A76 (CPU part 0x805 у части). RAM: 0x80000000+2 GiB и 0x100000000+0xfcc00000 — как у sweet.
  => `--cpus 6/8` имеет смысл проверять на железе.
- **GPU-прошивки получены:** a630_sqe.fw, a618_gmu.bin, a615_zap.{b00,b01,b02,mdt}; плюс тач Novatek (huaxing/tianma),
  haptic (aw8624/drv2624), CAMERA_ICP.elf, adsp/cdsp/venus из modem/image.
- **Датчики:** в DT surya нет датчиков на I2C/SPI основного процессора. Список Android: accel, gyro, mag, ambient_light,
  proximity, sar, pedometer, tilt, pickup, sig_motion, device_orient, rotv/game_rv/geomag_rv, gravity. Конфиги SSC:
  lsm6dso (accel/gyro, также варианты bmi220/bmi26x/icm4x6xx), ak0991 (магнитометр), stk3a5x (свет/приближение, варианты
  huaxing/tianma под панель), adux1050 (SAR). HAL = `sensors.ssc.so`. Т.е. датчики за SSC на **ADSP** (SM7150 без SLPI) ->
  нужен путь через ADSP (remoteproc/glink/QMI sns), прямого I2C-драйвера не будет. Какая именно микросхема стоит
  на этом экземпляре — по registry/sensors_list (сверить).
- **Камеры:** cam-sensor@0..6 на CCI `ac4a000`. Модули Android: IMX682 (64 МП, ofilm/sunny), HI1337 (ultra), HI259 (macro,
  ofilm/aac), OV02B1B / GC02M1B (depth), S5K3T2 (front, ofilm/sunny). Файлы sensormodule/tuned/.so в `camera/`.
  Какие реально установлены — по DT-узлам cam-sensor и по probe (не проверено).

**Следующее:** SMP (сборка в Actions) и GPU G1–G3. Датчики/камера — после.

## 2026-10-27 — слияние форка
- Влит `origin/main` (10a8f7a): сайт, LICENSE, upstream-правка `mkadt.py` (лог паники `/pram` + `embedded-panic-log-size`).
- Эта правка кладёт `/pram` по адресам sweet (DRAM-верх 0xb0000000+...), а не по RAM surya. В `surya.py` узел и свойство
  убраны, как в ранее загружавшихся образцах; тест `test_sweet_panic_region_is_not_inherited`. 60 тестов OK.
- TODO (гипотеза): если на surya снова будет `gPanicBase is still not initialized`, отмерить область и поставить её
  внутрь проверяемого диапазона RAM surya (учесть контракт base/size в `validate_payload`).

## 2026-10-27 — фаза 0: инвентаризация
- `adb devices` показал устройство `192.168.1.124:5555`: это **Yandex Station Mini 2** (колонка), не Poco. Прочитал только
  model/compatible/разделы, ничего не тянул и не менял. Poco по adb не подключён.
- Добавил `tools/pull-surya-inventory.sh`: только чтение; отказывается работать, если DT-модель не surya;
  складывает DT, прошивки (a630_sqe, a618_gmu, a615_zap, тач, DSP), камерные модули, реестр сенсоров и /proc-информацию
  в `research/live-surya-android/` (в git не попадает). Запуск: `tools/pull-surya-inventory.sh [SERIAL]`.
- Ждём: Poco в Android/recovery с root adb (или файлы вручную).

## 2026-10-27 — план GPU / датчики / камера (черновик, ждёт решения владельца)
Фазы: 0 инвентаризация железа surya (DT + прошивки из Android) -> 1 SMP/лаги -> 2 GPU (A618) -> 3 датчики -> 4 камера.
GPU: SQE/ZAP-прошивки -> ringbuffer + CP init (A6xx, не A7xx из UniXNU) -> IRQ/fence -> userclient по образцу
HakiosGPUUserClient -> Mesa freedreno (a618 поддерживается) -> GLES-композитинг вместо CPU-рендера -> DVFS через GMU.
Датчики: выяснить по DT, на AP-шине или за SLPI/SSC; если SLPI — remoteproc+glink/qrtr по образцу hakios.adsp.c;
публикация как IOHIDEvent (accel/gyro/ALS/proximity) для CoreMotion.
Камера: по образцу hakios.camera.c (CCI, PM-регуляторы, MCLK, CSIPHY, CSID/IFE) + software ISP; iOS-сторона (AVCapture) не изучена.
Всё непроверено на железе; детали — в ответе владельцу в чате.

## 2026-10-27 — старт, анализ
**Наблюдения**
- Репо клонировано; последний коммит `d8281fa` (SMMUv2 CB0 + Stream 0).
- Система грузится до лок-скрина, но лагает (слова владельца).
- В SURYA жёстко `cpus=1` во всех cmdline (`tools/surya.py`) и ADT обрезан до одного CPU-узла.
  У sweet SMP уже работает (патчи 0065 PSCI, 0078 восемь ядер; их заметки: «input latency ~1 min with 1 CPU»).
  Патчи 0065/0078 лежат и в этом репо — ядро SMP умеет, мы его просто не включали.
- На ПК нет `gh`, `clang`, `aarch64-linux-gnu-gcc`; ядро собирается в GitHub Actions (`.github/workflows/xnu.yml`) на форке.
- HakiOS (oosexgang) уже имеет: GPU Adreno (Mesa/freedreno, `gpu=1`), звук/микрофон (ADSP), батарея, вибро,
  Wi-Fi (ath11k), камеры (`cam=5`), `/var` между перезагрузками, модем (в работе). Это SM7325 (778G),
  не SM7150 — драйверы нужно сверять, а не копировать вслепую.

**Сделано**
- `tools/surya.py`: параметр `cpus` (1..8) для `build()`, `with_cpus()`, флаг `--cpus`; валидатор payload
  требует, чтобы `cpus=` в cmdline совпадал с числом CPU-узлов в ADT.
- `tools/mksurya-apple-root.py`: флаг `--cpus N`.
- Тест `test_smp_cpu_count_matches_cmdline`; весь набор: 60 тестов OK (26 skipped, как и раньше).
- По умолчанию по-прежнему `cpus=1` (поведение не меняется, пока SMP не проверен на этом телефоне).

**Гипотезы / не проверено**
- SM7150 у surya и sweet — тот же SoC; MPIDR (Aff1 = номер ядра, 0–5 A55, 6–7 A76) должен совпадать.
  Реальный DT surya с телефона не сверялся (в клоне нет `research/live-surya-android`).
- Причина лагов = одно ядро + CPU-рендер. Подтвердится только запуском с `--cpus 6`.

**Следующие шаги**
1. Собрать ADT/образ с `--cpus 6`, затем `--cpus 8`; смотреть в логе `SWEET CPU: cpu=N ... came alive`.
2. GPU: сравнить с HakiOS (`xnu/files`, `tools/mesa`) — путь через Mesa/freedreno вместо собственного Metal.
3. Звук/датчики/камера/Wi-Fi: инвентаризация железа surya (DT) против драйверов HakiOS.
