# HANDOFF — всё про проект, телефон, сборку и что делать дальше

Документ написан 2026-10-28 агентом Claude (Sonnet 5.5) в конце длинной сессии, когда контекст был на исходе. Цель — чтобы любой следующий
агент (или человек) мог продолжить с того же места, ничего не угадывая. Читать вместе с `WORKLOG.md` (хронология, новые записи сверху),
`NOTES.md` (старая подробная история прежних агентов; её ранние разделы местами устарели, см. «Поправки к старым заметкам»),
`docs/gpu-plan.md` (план GPU), `docs/macos-setup.md` (работа на хакинтоше).

Правило разделения: **наблюдение** = увиденное на железе/в CI (фото владельца, лог сборки); **гипотеза** = моё предположение, не проверенное.
Ниже оба типа помечены.

---------------------------------------------------------------------------------------------------------------------------------

## 0. Кто есть кто и как с этим работать

- **Владелец** (русскоязычный) делает порт iOS 16 на **Poco X3 NFC (`surya`, Snapdragon 732G / SM7150)**. Общаться по-русски, коротко и ясно,
  без жаргона там, где можно обойтись; он не программист ядра, но терпеливо тестирует на телефоне и присылает **фото экрана**.
- Основа: проект `dipa-studio/ios-sweet` (порт на Redmi Note 10 Pro `sweet`, тот же SoC SM7150), форк-адаптация под surya; эталон по «умным»
  драйверам — `oosexgang/hackios-xnu-kernel` («HakiOS», POCO X5 Pro, SM7325; другой SoC, **адреса и регистры нельзя копировать не сверив**,
  но структура шагов и приёмы отличные; лицензия: ядро APSL 2.0, остальное MIT — при переносе сохранять заголовки/указывать источник).
- Репозитории: `fork` = `https://github.com/Yar1klamer/ios-surya-huaxing` (репозиторий владельца, **сюда пушить**: `git push fork main`),
  `origin` на хакинтоше = оригинал `arbuxiktech/ios-surya` (чужой, не трогать). Рабочая папка на хакинтоше: `/Users/t1lt/ios-surya`.
- **Правила, которые владелец задал явно:**
  - **Всегда записывать в файлы (WORKLOG.md и этот HANDOFF.md) всё, что поменялось, и каждый важный результат — сразу, до следующего шага** (сказано 2026-10-28).
  - Телефон: **временная загрузка (`fastboot boot`) только когда владелец написал «грузи»/«газ»/подтвердил, что смотрит на экран.** Ничего не прошивать
    в разделы; Android/разделы/бэкапы не трогать. Подтверждать каждый разрушающий шаг.
  - **Никогда не трогать adb-устройство 192.168.1.124** (чужое: колонка/Nexus 4). Наш телефон имеет свой серийный номер (смотреть `fastboot devices`;
    серийники в git не писать, это правило проекта).
  - Не вводить за владельца пароли/фразы (SSH-пароли, sudo, Apple ID): он вводит сам. Токены/пароли в репозиторий и файлы не писать.
  - Все важные результаты записывать в `WORKLOG.md` (новые записи **сверху**, по-русски) и в `NOTES.md` (короткая сводка «active handoff»).
  - Коммиты и пуши владелец разрешил. Коммиты делать так: `git -c user.name="Yar1klamer" -c user.email="yarnick.ps4@gmail.com" commit ...`
    и с хвостом в сообщении: пустая строка, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` и строка `Claude-Session: <ссылка сессии>`
    (если система её даёт). **Сначала запускать тесты, потом пушить** (однажды я запушил сломанный тест).
- Языки/стиль кода: C для ядра в стиле окружающего файла (табы в BSD-файлах, 4 пробела в сгенерированных ArmSmmu4K*), комментарии объясняют «почему».
- Ключевые уроки безопасности для железа: **чтения раньше записей; каждый шаг печатает на экран «что трогаю» ДО обращения** (после тихой перезагрузки
  по последней строке видно, где остановились); запись в PMIC/TrustZone/XPU-защищённое — только после сверки с Linux/Xiaomi и с read-back.

---------------------------------------------------------------------------------------------------------------------------------

## 1. Телефон и как он устроен (факты)

### 1.1 Железо (из живого дерева устройства, снятого с телефона, и измерений шима)
- SoC **SM7150 (Snapdragon 732G)**: 8 ядер: 0–5 = Cortex-A55, 6–7 = Cortex-A76. PSCI (метод `smc`) включает вторичные ядра. MPIDR ядра N = `N<<8`.
  GICv3: GICD `0x17a00000`, GICR `0x17a60000`. Таймер 19,2 МГц, виртуальный таймер INTID 19, физический 18.
- RAM: `0x80000000`+2 ГиБ и `0x100000000`+`0xfcc00000` (ядру отдаётся `0x100000000`+`0xfc000000`). Куски физической памяти заняты прошивками (reserved-memory).
- Дисплей: **IPS LCD Novatek NT36672C, вариант Huaxing** (в Android: `androidboot.lcmtype=dsi_nt36672c_huaxing_fhd_video_display`), 1080×2400, стартовый
  framebuffer от загрузчика на `0x9c000000`, stride 4320, xRGB; режим video (перерисовывать «пинком» не надо). XNU показывает его как «iPhone X» 1125×2436.
  **Подсветка — WLED в PM6150L** (`bl_ctrl_wled`), панель — не AMOLED (важно: код, написанный под AMOLED sweet, «выключает» экран только затемнением картинки).
- Тач: Novatek NT36672C через SPI/GENI SE (`0xa84000`), работает **только после загрузки прошивки в SRAM контроллера** (`novatek_ts_huaxing_fw.bin`
  для этого телефона; `…tianma…` — для другой версии панели, у владельца её НЕТ).
- Кнопки: не GPIO SoC, а входы PMIC на шине **SPMI** (арбитр `0xc440000`, версия 5): питание = KPDPWR, громкость вниз = RESIN (блок PON PM6150 SID0 `0x800`),
  громкость вверх = GPIO2 PM6150L (SID4, `0xc100`).
- Хранилище: UFS. iOS-корень лежит в разделе **userdata** (HFS+ ≈16 ГиБ внутри, «bounded Apple root»); границы заданы в ADT (`surya-root-contract`).
  Android на телефоне остался, всё грузится **временно** через `fastboot boot`, прошивки нет. Обратно в Android — просто перезагрузка.
- GPU **Adreno 618** (chip id `0x06010800`): регистры `0x05000000` (окно `0x40000`), GMU `0x0506a000`, GPUCC `0x05090000`, SMMU `0x05040000`
  (контекстный банк 0 по смещению `0x8000`), прерывание GPU — SPI 300, прошивки Android: `a630_sqe.fw`, `a618_gmu.bin`, `a615_zap.{mdt,b00,b01,b02}`.
  Память под zap-шейдер: reserved-memory `gpu_region@97715000`, `0x2000`, no-map.
- Датчики (гироскоп/акселерометр/магнитометр/свет/приближение): **не на I2C основного процессора**, а за Qualcomm SSC на **ADSP** (в Android HAL `sensors.ssc.so`).
  Нужен путь через ADSP (remoteproc/glink/QMI) — эталон `hakios.adsp.c`. Не начато.
- Камеры: CCI `ac4a000`, 7 узлов cam-sensor, модули Android: IMX682 (64 МП), HI1337, HI259, OV02B1B/GC02M1B, S5K3T2 (фронт). Не начато.
- Отладка: **UART нет**. Единственный канал — экран (консоль XNU рисуется в framebuffer) + фото владельца.

### 1.2 Как телефон грузится в нашем проекте (цепочка)
1. Владелец переводит телефон в режим **fastboot** (громкость вниз + питание) и подключает **напрямую** в порт Mac (через USB-хаб `fastboot boot` зависает).
2. `fastboot boot образ.img` отправляет образ в оперативную память и запускает его (Android-формат **boot.img v2**; пагайз 0x1000, base 0, kernel_offset 0x8000,
   ramdisk_offset 0x1000000, tags 0x100, dtb_offset 0x1f00000, cmdline `console=null`).
3. В образе: «ядро» = наш **шим** (`shim/`, `shim-Image`, ~180 КБ, ассемблер+C: `start.S`, `loader.c`, `mmu.c`, `console.c`, `ufs.c`, `fdt.c`), «ramdisk» = **payload**
   (`tools/mkpayload.py`: Mach-O ядро XNU + ADT + cmdline, формат magic `SWEETXNU`), `dtb` = штатный dtb телефона (нужен только загрузчику ABL).
4. Шим проверяет payload (`surya.validate_payload`-подобные проверки сделаны инструментами заранее), строит страничные таблицы (16К гранула), копирует сегменты ядра,
   готовит boot_args/ADT и передаёт управление XNU на EL1.
5. XNU (xnu-8796.141.3, «macOS 13.5», iOS 16-эпоха) стартует с машинной конфигурацией **SURYA**, поднимает 6 ядер (`cpus=6`), монтирует корень с UFS, и либо запускает
   `launchd` (профиль `gui`), либо **намеренно останавливается перед launchd** (диагностические профили) и показывает отчёт на экране.
6. Выход: **питание + громкость вниз** возвращают в fastboot (шим/ядро ловят это сочетание в диагностических режимах).

### 1.3 ADT (device tree для XNU)
- Генерируется `tools/surya.py` (+ `mkadt.py`, `adt.py`) из живого dtb: узлы `cpus` (по числу `--cpus`), `memory`, `chosen`, UFS, display, `product` (iPhone10,3, D22AP) и т. д.
  Файл `smp6.adt` — готовый ADT на 6 ядер.
- В `/chosen` **кладутся прошивки как свойства** (так ядро получает их без файловой системы): `surya-touch-panel` (`huaxing`) и `surya-touch-firmware`,
  `surya-gmu-firmware`, `surya-zap-mdt`, `surya-zap-code`, `surya-gpu-sqe`. Их добавляет `tools/mksurya-apple-root.py`, **только пиннованные по SHA-256**
  (модули `surya_touch_firmware.py`, `surya_zap_firmware.py`, `surya_sqe_firmware.py`; сами бинарники вендорские — в git не коммитятся).
- `surya.validate_payload()` — строгий «страж»: разрешены только известные командные строки (`APPLE_*_CMDLINE`; допустимо менять лишь `cpus=N`, равное числу CPU-узлов ADT),
  свойства прошивок допустимы только в своих профилях. При добавлении нового профиля — добавить cmdline в список разрешённых и тест.

### 1.4 Командные строки (boot-args) и профили
Профили заданы в `tools/surya.py`, выбираются флагами `tools/mksurya-apple-root.py` (и профилями `tools/make-boot-image.sh`):
| профиль (make-boot-image) | что делает |
|---|---|
| `gui` | обычный запуск iOS, консоль выключена (`sweetfb_noconsole=1`), тач и кнопки включены (`sweettouch=1 sweetkeys=1`) |
| `touch` | то же, но консоль видна и запуск **останавливается перед launchd** с отчётом тача (`suryatouchreport=1`) |
| `diag` | диагностика stderr демонов |
| `gpu` | GPU-диагностика: питание GPU, SMMU, отчёт (`suryagpummu=1`) |
| `gpu-zap` | `gpu` + передача zap-шейдера TrustZone (`suryazap=1`) |
| `gpu-core1`..`3` | `gpu-zap` + ядро 3D до этапа N (`suryacore=N`) — это текущая работа |
Общие аргументы: `rd=ufsroot0 ufsroot=userdata ufsrw=1 rootrw=1`, `cpus=6`, `sweetusb=0 sweetbattery=0 sweetlog=0`, `wdt=-1` и др.

---------------------------------------------------------------------------------------------------------------------------------

## 2. Ядро: патчи XNU и сборка

### 2.1 Серия патчей `xnu/patches/` (103 штуки, строго подряд 0001…0103, файлы в **LF**; `.gitattributes`/`eol=lf`)
- 0001–0081: порт ios-sweet (машинная конфигурация, фреймбуфер-консоль, свои драйверы UFS/touch/keys/HID, AMFI-/sandbox-заглушки, USB, SMP 0065/0078 и т. д.).
- 0082–0093: адаптация под surya (RAM-disk цель, чтение UFS, bounded Apple root 0086, Novatek-тач по SPI 0087–0091, диагностика таблиц GPU 0092, SMMU/ArmSmmu4K 0093).
  **0093 генерируется** `tools/gen_unixnu_smmu_patch.py` из вендорного `graphics/vendor/unixnu` (тест сверяет генератор с файлом — не править 0093 руками).
- **Мои патчи этой сессии:**
  - 0094 — PMIC-кнопки на surya: снята заглушка и добавлен вызов `sweet_keys_init()` на пути surya (раньше его никто не вызывал).
  - 0095 — чтение регистров WLED (только чтение).
  - 0096 — прошивка тача Huaxing: загрузчик Novatek знает обе панели (таблицы блоков читаются из заголовков файлов).
  - 0097 — выключатель подсветки WLED: один бит `MOD_EN` (бит 7, регистр `0x46` модуля `0xd800` PM6150L SID5), чтение-проверка, мьютекс SPMI, вызывается из IOMFB selector 12.
  - 0098 — «зондирование» TrustZone (только вопросы).
  - 0099 — загрузка zap-шейдера GPU в TrustZone (`PAS_INIT_IMAGE`, `MEM_SETUP`, копирование `b02`, `AUTH_AND_RESET`, затем `SHUTDOWN`).
  - 0100 — G3a: 34 записи в регистры ядра 3D по Linux `a6xx_hw_init` (с read-back).
  - 0101 — G3b: запуск командного процессора (SQE+кольцо+SMMU CB0+`CP_ME_INIT`).
  - 0102 — исправление: `leaf_budget` ArmSmmu4K — это число 4К-страниц, а не страниц таблиц.
  - 0103 — зондирование ширины регистров совпадения потока SMMU (SMR) и привязка потока 0 к контексту 0.
- Новые файлы ядра живут в `bsd/dev/`: `surya_gpu_pt.c` (оркестровка диагностики), `surya_gpu_core.{c,h}` (этапы 3D-ядра), `surya_tz.{c,h}`, `surya_zap.{c,h}`,
  `surya_unixnu_smmu.{c,h}` (мост к ArmSmmu4K), `ArmSmmu4K*.{c,h}` (вендорная библиотека SMMU), `sweet_keys.c`, `sweet_touch.c` и др. Файлы регистрируются в `bsd/conf/files`.
  `ARM64_BOARD_CONFIG_SURYA` определён при сборке SURYA; `SWEET` тоже (поэтому код sweet в surya-сборке виден; заглушки `#if SURYA` внутри функций).

### 2.2 Как собирается ядро
**Только на macOS** (нужны Xcode и Apple-инструменты). Вариантов два:
1. **GitHub Actions** (`.github/workflows/xnu.yml`): на каждый push в `xnu/patches/**` собирает на `macos-14` (Xcode 15.x) артефакт `xnu-kernel` (~8–9 минут + очередь; один раз раннер завис на 15 мин —
   перезапуск «Re-run»). Скачивание артефакта требует входа в GitHub (мне владелец давал токен в чате для Windows-сессии; **токен надо отозвать**, в репозитории его нет).
2. **Локально на хакинтоше** (основной способ теперь): `bash tools/build-kernel-macos.sh` → `research/kernel-local/kernel.development.surya` (~12 минут, каждый раз с нуля).
   Скрипт повторяет workflow: берёт проект `blacktop/darwin-xnu-build` (закреплён коммит), кладёт в него наши патчи, ставит `cmake`/`ninja` через pip (Homebrew на Intel больше не поддерживается),
   подкладывает заглушки `xcodes`/`gum`, правит `PATH` внутри `build.sh`, скачивает и ставит KDK 13.5 (при первом запуске спросит пароль администратора — вводит владелец).
   Сборочное дерево с применёнными патчами остаётся в `~/surya-xnu-build/dxb/xnu` — **удобно брать оттуда точную базу для нового патча**.

**Ловушки сборки (все уже встречались):**
- Нужна **Xcode 15.4** (`/Applications/Xcode_15.4.app`, активирована через `xcode-select`; Xcode 16 ломает `iig`). После установки обязателен `sudo xcodebuild -runFirstLaunch`
  и принятие лицензии, иначе `xcodebuild` в bootstrap_cmds падает на CoreSimulator.
- В bash-скрипте с `set -o pipefail` **нельзя** `cmd | head -1` (SIGPIPE, код 141) — заменено на `sed -n 1p`.
- `build.sh` пересобирает `PATH` и теряет наши каталоги — скрипт правит это sed'ом.
- Предупреждения «Skipping patch … (already upstream…)» про `iobuffermemd_monterey`, `skywalk_sonoma`, `syntax_checker_sonoma`, `TrustCache` — штатные.
- Контроль результата: `LC_ALL=C grep -a -c "<строка из нового патча>" kernel.development.surya` (в macOS-grep нужен `-a` и `LC_ALL=C` для бинарников).

### 2.3 Как собирается образ для телефона
`tools/make-boot-image.sh KERNEL PROFILE OUT.img [CPUS]` (работает на macOS и Linux, нужен python3):
1. `mksurya-apple-root.py` берёт ядро + `smp6.adt`, добавляет прошивки (по профилю) и командную строку → `payload.bin`.
2. `mkbootimg.py` (из AOSP, лежит в бандле) упаковывает: шим как kernel, payload как ramdisk, stock dtb, параметры из §1.2.
3. Бандл `research/macos-bundle/` (в git не попадает): `shim-Image`, `smp6.adt`, `stock.dtb`, `mkbootimg/`, `fw/` (`a618_gmu.bin`, `a630_sqe.fw`, `a615_zap.mdt`, `a615_zap.b02`,
   `novatek_ts_huaxing_fw.bin`) + `SHA256SUMS`. Архив `macos-bundle.tgz` лежит у владельца в Загрузках, на Linux-хосте (`~/macos-bundle.tgz`) и на Windows-ПК (`research/`).
   Откуда бандл: шим собран на Linux-хосте (`shim/build.sh`, нужны clang и aarch64-gcc), `smp6.adt` — `tools/surya.py --apple-root --cpus 6` с «evidence» из дампа телефона
   (память/UFS), `stock.dtb` — dtb из старого `boot-smp6.img` (`unpack_bootimg`), прошивки — `adb pull` с телефона (`tools/pull-surya-inventory.sh`, в recovery с монтированием vendor read-only).
4. Загрузка: `fastboot -s <серийник> boot образ.img`. Если «Unrecognized command boot» — телефон в fastbootd: `fastboot reboot bootloader`.

### 2.4 Рабочий процесс нового патча (как делал я)
1. База: взять нужные файлы из `~/surya-xnu-build/dxb/xnu` (там все патчи применены) в **временный git-репозиторий**, закоммитить как base.
2. Править файлы (для кода с `\n` в строках C надёжнее инструмент Edit/Write; **в bash-heredoc обратные слэши портятся**), для новых файлов — `git add -N`.
3. `git diff` → файл `xnu/patches/NNNN-имя.patch` (убрать строки `index`); если добавлен файл — добавить хунк в `bsd/conf/files` (табы как в соседних строках!).
4. Проверить: `git apply --check` на чистой базе; синтаксис `xcrun clang -target arm64-apple-macos -fsyntax-only -DARM64_BOARD_CONFIG_SURYA -I<заглушки> …`.
5. Тесты (`tests/`): патч-тексты проверяются как данные (порядок вызовов, смещения регистров по Linux, «только чтение» и т. п.), `python3 -m unittest discover -s tests`;
   `python3 tools/validate-repo.py` (проверяет, что патчи 0001…N подряд и форматом).
6. Коммит → `git push fork main` → `bash tools/build-kernel-macos.sh` → `tools/make-boot-image.sh … gpu-core2 …` → ждать «грузи» → загрузить → разбирать фото.
   Новый профиль/boot-arg: добавить cmdline в `surya.py` (+ список разрешённых), флаг в `mksurya-apple-root.py`, профиль в `make-boot-image.sh`, тест.

---------------------------------------------------------------------------------------------------------------------------------

## 3. Что подтверждено на железе (наблюдения, по порядку)
Все — по фото владельца, 2026-10-28, `fastboot boot` образов без прошивки разделов.
1. **SMP:** `cpus=6` и `cpus=8` (A55+A76) поднимаются (`SWEET CPU: 6/6 … SGI1 verified`). Загрузка GUI до экрана: 15 мин (1 ядро) → ~1 мин (6 ядер). 8 ядер — ~1:27 и **нестабильно**
   (причины не выяснены; гипотеза: XNU считает A55/A76 однородными, нет cpufreq). Основной образ — 6 ядер.
2. **Кнопки:** питание/громкость вверх/вниз читаются через PMIC (`SWEET KEYS: key=… down=1/0`) и работают в iOS (после 0094 и профиля `sweetkeys=1`).
3. **Тач:** с прошивкой **Tianma** одна половина экрана работала «зеркально»; с прошивкой **Huaxing** (0096) исправлено (подтвердил владелец). В логе: `loading verified Huaxing image`, `firmware boot result=0`, `fw=c3/3c`.
4. **Подсветка:** по питанию экран гаснет вместе с подсветкой и включается обратно (0097; регистры WLED совпали с Linux `qcom-wled.c`, WLED5).
5. **TrustZone** отвечает на SMC из нашего ядра: `PAS init-image 1, auth-and-reset 1`; вопрос `is_supported` даёт 0 для всех образов, включая заведомо рабочие аудио/модем — **неинформативен**.
6. **G2 (zap):** `SURYA ZAP: RAN stage=8 code=0 answer=0 header=6860 code=1984 region 0->0x16ff021` и `TRUSTZONE AUTHENTICATED THE ZAP SHADER; given back: yes`. Повторено и на ядре, собранном локально.
7. **G3a:** 34 записи в регистры ядра 3D (GBIF, `*_ADDR_MODE_CNTL`, UCHE, CP_ROQ…) прошли без зависания: `wrote=34 same=29 differ=5`. Пять регистров читаются иначе (маски/write-only/нет регистра):
   `RBBM_GBIF_HALT`@0x58 читается `0xdeafbead` (у A618 по этому смещению регистра нет), `RBBM_PERFCTR_GPU_BUSY_MASKED`, `UCHE_GMEM_RANGE_MAX`, `CP_ROQ_THRESHOLDS_2`, `UCHE_CLIENT_PF`.
8. **G3b, ход попыток:** (a) `stop=4` — отказ построения таблиц (`leaf_budget`, ошибка в моём коде, исправлено 0102); (b) после 0102 таблицы построены и контекст CB0 запрограммирован,
   `stop=7` — привязка потока: `S2CR0` записался (0), а **`SMR0` после записи `0x84010000` читается 0**. ID0=`0x48016605`: 5 групп сопоставления, 3 бита ID потока (`NUMSIDB=3`);
   (c) патч 0103 (образ `core2c`): контекст CB0 **включён** (`SCTLR=0x10e7`, `FSR=0`, `FAR=0`), все 5 групп `S2CR=0x200ff` (FAULT), все `SMR=0`, `SCR1=0`, `GFSR=0`; пробы ширины полей SMR
   (запись `0x7fff` в ID и в MASK при **сброшенном valid**) читаются `0x7fff` — то есть поля ID/MASK пишутся, но **запись с valid=1 и маской `0x401` отбрасывается** (читается 0).
   Гипотеза «сравниваются только NUMSIDB=3 бита» **не подтвердилась по исходникам Xiaomi** (в их DT для этого SMMU есть SID 0x9 и маска 0x401, на Android всё работает).
   (d) патчи 0104/0105 (образ `core2d`) — **результат: привязка потока ЗАРАБОТАЛА.** Принята запись SMR `0x80000000` (valid, id 0, **маска 0**); записи с ненулевой маской (`0x80010000`, `0x84010000`) отбрасываются (читаются 0).
   Этап 2 дошёл до конца (`stop=0/0`): CB0 включён, CP запущен, `CP_ME_INIT` в кольце (`wptr=9`), но **`rptr=0`, `RBBM_STATUS=0xc00015`, SMMU CB0 `FSR=0x40000402` (Translation Fault + транзакция остановлена), `FAR=0`**:
   GPU обратился к виртуальному адресу 0, которого нет в таблицах, и застрял. Источник обращения не выяснен (подозрение: `CP_RB_RPTR_ADDR`=0 — указатель чтения; либо другой указатель по умолчанию 0).
9. Питание/GMU: `BABEFACE PASS`, OOB6 ACK, `GX GDSC ON`, `RBBM_STATUS=0x1`; `GBIF_QOS@0x44=0xdeafbead` (смещение, вероятно, не регистр). SMMU стабильно читается; тест-контекст CB0 активировался.
   **Отличие этого телефона от старых заметок:** там ID0=`0x40016605`, ID1=`0x20000005`; здесь ID0=`0x48016605`, ID1=`0x20008005` (гипотеза: старые заметки с другого экземпляра/прошивки).

## 4. Где мы остановились ПРЯМО СЕЙЧАС (на момент написания документа)
- **Актуально:** см. §3.8 (d). Следующий патч — **0106**: «ловушка» на IOVA 0 (замапленная страница, чтобы GPU не застревал и было видно, что он туда пишет), `CP_RB_RPTR_ADDR` на замапленную страницу, чтение `FSYNR0/1` и `GFSR` после запуска CP.
  После него: G3c (zap остаётся авторизованным, `CP_SET_SECURE_MODE`, `CP_MEM_WRITE`). Историческое описание 0103/0104 ниже оставлено для контекста.
- (История) Патч **0103** загружен и дал результат (см. §3.8 (c)). Патч **0104** (маска обрезается до `NUMSIDB` бит; пробуются формы SMR: `valid|(0x401&mask3)<<16|id`, `valid|id` без маски, затем «как в DT»; группы 0, 1, 4;
  каждая попытка читается обратно, неудачные записи гасятся; в отчёт идут все попытки `try N: group G wrote SMR … read … (S2CR …)`, `GFSR`/`GFSYNR0` после попыток) закоммичен и запушен (`0f76734`),
  локальная сборка ядра запускалась в фоне (`~/surya-build6.log`). Дальше: собрать образ `tools/make-boot-image.sh research/kernel-local/kernel.development.surya gpu-core2 research/images/boot-mac-gpu-core2d.img`
  и ждать «грузи» владельца.
- Как загрузить: `cd ~/ios-surya && fastboot boot research/images/boot-mac-gpu-core2d.img` (одно устройство в `fastboot devices`); через ~минуту владелец присылает фото конца консоли.

### 4.1 Что смотреть в отчёте и что делать дальше (дерево решений)
Отчёт печатает строки `SURYA CORE:`, `SURYA CORE2:`:
- `SURYA CORE2: SMMU groups SMR … S2CR …; SCR1=… GFSR=…` — состояние 5 групп до записи.
- `SURYA CORE2: match id bits … mask bits …, SMR0 wanted … read …` — реализованные ширины и итог записи.
- `SURYA CORE2: RAN/STOPPED stop=N/код …` — `stop`: 1 SMMU-захват не там; 2 нет микрокода в ADT; 3 нет памяти; 4 отказ `ArmSmmu4KBuild` (код = ArmSmmu4KStatus); 5 нет отображения SMMU;
  6 отказ программирования контекста; 7 привязка потока не прошла; 0 — дошли до запуска CP.
- `SURYA CORE2: CP ring rptr=… wptr=… CAUGHT UP/NOT CAUGHT UP RBBM_STATUS=… INT0=… HW_FAULT=… CP_INT=…` и `SMMU SCTLR/FSR/FAR` — результат запуска командного процессора.

Дальше:
- **Если одна из форм SMR удержалась (`stream 0 on group N`, не -1):** CP запустится. Успех G3b = `CAUGHT UP` (rptr == wptr = 9), нет `FSR`-ошибок. Если `NOT CAUGHT UP` и `FSR != 0` — смотреть `FAR` (адрес GPU, на который споткнулся
  SMMU: микрокод? кольцо?) и править таблицы/атрибуты; если `FSR == 0`, но rptr не растёт — смотреть `HW_FAULT`/`CP_INT`/`RBBM_INT_0_STATUS`, проверить, что секурный режим не блокирует CP
  (в Linux zap грузится ПОСЛЕ `CP_ME_INIT`, затем `CP_SET_SECURE_MODE=0`).
- **Если ни одна форма SMR не удержалась (`stop=7`, все `try … read 0`):** посмотреть `GFSR/GFSYNR0` после попыток (заблокированная запись может фиксироваться как глобальный сбой), начальные SMR/S2CR 0–4 и `SCR1`. Гипотезы: (1) группы закреплены TrustZone/гипервизором и запись из нашего EL1 игнорируется — тогда
  попробовать другую группу (1–4) или «разведать» через Android-значения (снять `S2CR`/`SMR` из работающего Android — это запись состояния; на живом Android читать через /sys не получится, нужен снимок регистров
  из нашего ядра на «чистом» старте ABL); (2) нужно сначала `S2CR` с `EXIDVALID`/другим TYPE; (3) ожидается другая схема (GPU-поток маскируется/«транслируется» иначе). Не гадать — собрать ещё один диагностический образ
  с большим количеством чтений.
- **G3c** (после успешного G3b): оставить zap **авторизованным** (не вызывать `SHUTDOWN`, как сейчас в `surya_zap_load`; Linux грузит zap после CP init), послать `CP_SET_SECURE_MODE` (opcode 0x66) со словом 0,
  затем тест `CP_MEM_WRITE` (opcode 0x3d) в страницу scratch; прочитать слово (перед чтением `dc civac`). Это первый «настоящий» результат GPU («GPU записал слово в память»).
- **G4**: прерывания GPU (SPI 300 на GICv3), fence через `CACHE_FLUSH_TS`/`CP_EVENT_WRITE`, hang-recovery через GMU. **G5**: IOKit-сервис и user client (по образцу HakiosGPU), аллокация/маппинг буферов в SMMU, submit/wait.
  **G6**: Mesa freedreno/turnip с бэкендом под XNU и GLES-композитинг вместо CPU-рендера (единственный этап, дающий видимое ускорение UI). **G7**: DVFS/питание через GMU.

---------------------------------------------------------------------------------------------------------------------------------

## 5. Справочник регистров A6xx, использованных в `surya_gpu_core.c` (байтовые смещения в окне GPU `0x5000000`)
`RBBM_STATUS 0x840`, `RBBM_INT_0_STATUS 0x804`, `RBBM_GBIF_HALT 0x58` (нет на A618), `GBIF_HALT 0xf114`, `RBBM_SECVID_TSB_CNTL 0x3e00c`, `…TRUSTED_BASE 0x3e000` (64 бита), `…SIZE 0x3e008`,
`*_ADDR_MODE_CNTL`: CP `0x2108`, VSC `0x3004`, GRAS `0x21804`, RB `0x23814`, PC `0x27804`, HLSQ `0x2f814`, VFD `0x29804`, VPC `0x25804`, UCHE `0x3800`, SP `0x2b804`, TPL1 `0x2d804`, `RBBM_SECVID_TSB 0x3e040`;
`RBBM_VBIF_CLIENT_QOS_CNTL 0x40`, `RBBM_PERFCTR_GPU_BUSY_MASKED 0x142c`, `RBBM_PERFCTR_CNTL 0x1400`, `RBBM_INTERFACE_HANG_INT_CNTL 0x7c`; UCHE: `WRITE_RANGE_MAX 0x3814`, `TRAP_BASE 0x3824`, `WRITE_THRU_BASE 0x381c`,
`GMEM_RANGE_MIN 0x382c`, `GMEM_RANGE_MAX 0x3834`, `FILTER_CNTL 0x3860`, `CACHE_WAYS 0x385c`, `CLIENT_PF 0x3864`; CP: `ROQ_THRESHOLDS_1/2 0x2304/0x2308`, `MEM_POOL_SIZE 0x230c`, `AHB_CNTL 0x2634`,
`PC_DBG_ECO_CNTL 0x27800`; запуск CP: `CP_RB_BASE 0x2000` (64), `CP_RB_CNTL 0x2008`, `CP_RB_RPTR_ADDR 0x2010` (64), `CP_RB_RPTR 0x2018`, `CP_RB_WPTR 0x201c`, `CP_SQE_CNTL 0x2020`, `CP_SQE_INSTR_BASE 0x2058` (64),
`CP_HW_FAULT 0x2084`, `CP_INTERRUPT_STATUS 0x208c`, `CP_SQE_UCODE_DBG_ADDR 0x2440`, `RBBM_SECVID_TRUST_CNTL 0x3d000` (секурный, без zap не трогать).
Значение `CP_RB_CNTL`: `12 | (2<<8) | (1<<27)` = `0x0800020c` (размер кольца 32 КиБ → BUFSZ=log2(32К/8)=12, BLKSZ=log2(32/8)=2, NO_UPDATE без shadow-указателя).
Пакеты: `PKT7(opcode, count) = (7<<28) | count | parity(count)<<15 | (opcode&0x7f)<<16 | parity(opcode)<<23`, `parity` — `PM4_PARITY` из Linux; `CP_ME_INIT`=0x48 с 8 словами
`0x2f, 3, 0x20000000, 0,0,0,0,0` (заголовок `0x70c80008`). Микрокод SQE в GPU идёт **без первого слова файла** (`adreno_fw_create_bo`).
Источник всех значений: Linux `drivers/gpu/drm/msm/{adreno/a6xx_gpu.c, registers/adreno/a6xx.xml, adreno_pm4.xml, adreno/a6xx_catalog.c}` и Xiaomi `sm6150-gpu.dtsi` (поток GPU: `iommus = <&kgsl_smmu 0x0 0x401>`, секурный `0x2 0x400`).
У A618 в каталоге Linux: GMEM 512 КиБ, `prim_fifo_threshold 0x00180000`, квирк `ADRENO_QUIRK_4GB_VA` (адреса GPU держим ниже 4 ГиБ; мы мапим буфер по `0x10000000`).

### 5.1 SMMU (ARM MMU-500-подобный SMMUv2) на `0x5040000`
ID0=`0x48016605` (SMS=1; NUMSMRG=5; NUMSIDB=3), ID1=`0x20008005`, ID2=`0x7511` (4К-гранула), SCR0=`0x200626`; страница контекстных банков: банк 0 по `0x8000`; `S2CR` по `0xc00+4n`, `SMR` по `0x800+4n`;
`FSR` банка = `cb+0x58`, `FAR` = `cb+0x60`. Нужны клоки (GCC memnoc и GPUCC `0x5000` бит0 — голос HLOS1; без него чтение SMMU **зависает шину**). Мост `surya_unixnu_smmu.c` их включает.
Библиотека ArmSmmu4K: `ArmSmmu4KConfig = {input_bits=39, output_bits=36, table_physical, leaf_budget}` (**4-е поле = лимит 4К листьев**), `ArmSmmu4KRange = {iova, physical, bytes, perms, writeback(0=NC), shareability(2)}`,
таблицы — 4 страницы по 4К в одном 16К-блоке; `ArmSmmu4KProgramDisabledContext` включает контекст после read-back; строгая `ArmSmmu4KAttachStreams` на этом телефоне даёт `Busy`
(она ждёт `S2CR == FAULT` ровно, а чтение даёт `0x200ff`), поэтому привязка потока сделана вручную в `surya_gpu_core.c`.

---------------------------------------------------------------------------------------------------------------------------------

## 6. Остальные направления (не GPU)
1. **Лаги/стабильность (приоритет высокий):** cpufreq (сейчас частоты как оставил ABL; эталон `hakios.cpufreq.c`, источник частот на surya — проверить по DT), нестабильность 8 ядер, планировщик
   (A55/A76 в одном «однородном» кластере XNU). Рисует сейчас **CPU** (QuartzCore CPU renderer) — главная причина лагов; полное лечение — G6.
2. **Датчики** через ADSP (см. §1.1) → публикация IOHIDEvent. **Камеры** (CCI/CSIPHY/IFE + софт-ISP). Эталоны: `hakios.adsp.c`, `hakios.camera.c`. Какие модули стоят физически — проверить зондированием.
3. **Звук/микрофон/Wi-Fi/Bluetooth/модем/вибромотор/батарея/зарядка** — не начато (в HakiOS есть драйверы; у surya батарея сейчас «статическая заглушка 100%»).
4. **Уборка:** отозвать выданный GitHub-токен (он есть только в истории чата, не в репозитории); `origin` на хакинтоше указывает на оригинал — при желании переключить на форк; удалить `~/xcode-unpack`, `~/Downloads/Xcode_15.4.xip`;
   в корне репозитория лежат посторонние файлы `platform-tools-latest-darwin.zip`, `surya-fastboot-vars.txt` (не наши, в git не добавлять).

## 7. Поправки к старым заметкам (`NOTES.md`)
- Старые записи утверждали «Tianma panel» по захваченным bootargs. **Для телефона владельца это неверно: у него Huaxing** (форк так и назван). Прошивка Tianma грузилась только потому, что драйвер унаследован от другого варианта.
- Старые значения ID регистров SMMU (`ID0=0x40016605`) относятся к другому экземпляру; здесь `0x48016605`.
- Заметка в `docs/gpu-plan.md` про бит чётности PKT7 исправлена (15, не 7).
- `GBIF_QOS@0x44` и `RBBM_GBIF_HALT@0x58` у A618 — не читаемые регистры (маркер `0xdeafbead`), не «ошибка».

## 8. Окружение и доступы
- **Хакинтош** (macOS 15.8, Intel i5-13400F, имя `iMacPro-tilt`): рабочая среда, пользователь `t1lt`; Xcode_15.4, Python 3.12, platform-tools в `~/platform-tools`. **Телефон — прямо в порт материнской платы.**
  Git: `git push fork main` (учётные данные владельца в связке ключей, `osxkeychain`).
- **Windows-ПК владельца** (раньше основная среда): в `C:\Users\chel\ios-surya` лежат старые артефакты (`research/`), там же прежние образы. Работа оттуда не ведётся.
- **Linux-хост** `burmalda@192.168.1.112` (в локальной сети владельца): clang/aarch64-gcc/dtc/mkbootimg, рабочая копия `~/surya-smp` (клон форка с локальной правкой `shim/build.sh`), старая сборка `~/surya-build`
  (там `live/` с evidence для ADT). Доступ — по ключу владельца; с хакинтоша ключа у меня нет. Нужен в основном для пересборки шима (если понадобится менять `shim/`).
- Папка `research/` (git-ignored): `macos-bundle/`, `images/` (все образы `boot-*.img`), `kernel-local/` (последнее локальное ядро). Прежний дамп телефона `live-surya-android/` (дерево устройства, `/proc/iomem`, прошивки)
  **остался на Windows** — на хакинтоше его нет; при необходимости снять заново `tools/pull-surya-inventory.sh` (телефон в Android/recovery, adb).
- Скрипты: `tools/build-kernel-macos.sh`, `tools/make-boot-image.sh`, `tools/pull-surya-inventory.sh`, `tools/validate-repo.py`. Тесты: `python3 -m unittest discover -s tests` (на хакинтоше 3 пропуска — нет файлов Windows-дампа).

## 9. Быстрая шпаргалка
```bash
cd ~/ios-surya
python3 -m unittest discover -s tests && python3 tools/validate-repo.py          # проверка перед коммитом
git add … && git -c user.name="Yar1klamer" -c user.email="yarnick.ps4@gmail.com" commit -m "…" && git push fork main
bash tools/build-kernel-macos.sh > ~/surya-buildN.log 2>&1                        # ~12 мин, результат research/kernel-local/
bash tools/make-boot-image.sh research/kernel-local/kernel.development.surya gpu-core2 research/images/boot-X.img
fastboot devices                                                                   # телефон в fastboot, напрямую в порт
fastboot -s <серийник> boot research/images/boot-X.img                            # ТОЛЬКО после «грузи» владельца
```
Фото экрана → разбор строк `SURYA …` → запись в `WORKLOG.md` (сверху) → коммит/пуш → следующий патч.
