# WORKLOG — iOS 16 на Poco X3 NFC (surya)

Рабочий журнал. Новые записи сверху. Наблюдения (проверено на железе/CI) отделены от гипотез.
Подробный технический журнал прежних агентов — `NOTES.md`.

## Цели владельца (2026-10-27)
Довести порт до максимума: лаги, все ядра, GPU, ядро как у sweet, датчики, камера и остальное.
Источники: `dipa-studio/ios-sweet` (база), `oosexgang/hackios-xnu-kernel` (HakiOS, POCO X5 Pro: GPU через Mesa,
звук, Wi-Fi, камеры, 8 ядер). Клоны лежат в `research/` (в git не попадают).

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
