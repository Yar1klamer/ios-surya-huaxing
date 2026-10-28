# План GPU (Adreno 618, SM7150) — surya

Составлен 2026-10-28. Опирается на то, что подтверждено на этом телефоне (NOTES.md, фото владельца) и на
HakiOS (`bsd/dev/hakios.adreno.c`, Adreno 642L: тот же подход «шаги с boot-arg и логом до обращения к железу»).
Наблюдения отделены от гипотез. Ни один шаг не включается без явного boot-arg.

## Где мы сейчас (G0, подтверждено на железе)
- GMU: прошивка `a618_gmu.bin` загружена, `BABEFACE` пройден, рукопожатие OOB6 с ACK, **GX GDSC включён**.
- GPUCC, голосование HLOS1 для SMMU (`gpu_cc_hlos1_vote_gpu_smmu_clk`, 0x5000), три GCC-клока SMMU.
- SMMUv2: ID0/ID1/ID2 прочитаны, контекстный банк 0 активирован (SCTLR bit 0), поток 0 привязан (S2CR0), таблицы
  страниц 4K построены и обходятся независимо (UniXNU ArmSmmu4K).
- Не сделано: ядро 3D (CP/SQE), secure mode (zap-шейдер), прерывания, userclient, любые команды GPU.
- Рисует сейчас CPU (QuartzCore CPU renderer + копия в framebuffer). Это главная вероятная причина лагов UI.

## Этапы
Каждый этап — отдельный диагностический профиль с boot-arg (`suryagpu=N` выполняет шаги 1..N и останавливается), печатает
«что трону» до обращения и «что нашёл» после. Чтения идут раньше записей. Откат: при неудаче остаёмся на CPU-рендере.

| Этап | Цель | Что делаем | Критерий успеха | Риск |
|---|---|---|---|---|
| **G1** | Прочитать 3D-ядро после включения GX | Только чтения: RBBM (статус/идентификация), SECVID_TRUST, GBIF/VBIF, счётчики клоков. Сверка смещений с Linux `a6xx.xml` и Xiaomi KGSL | Регистры читаются, не зависание; видно, в secure mode ядро или нет | низкий (чтения при включённом GX) |
| **G2** | Выйти из secure mode | zap-шейдер `a615_zap.{mdt,b00..b02}` через SCM/PAS (авторизация в TrustZone). Альтернатива, если TZ не принимает: проверить, не оставил ли загрузчик ядро несекурным | `RBBM_SECVID_TRUST_CNTL` показывает несекурный режим, регистры CP доступны на запись | **высокий**: TZ/гипервизор могут молча перезагрузить (в HakiOS так и было) |
| **G3** | Первая команда GPU | Микрокод SQE `a630_sqe.fw` в память, видимую через SMMU CB0; кольцо (RB), CP_ME_CNTL, CP_ME_INIT, затем `CP_MEM_WRITE` магического слова | Слово появилось в памяти, rptr продвинулся | средний |
| **G4** | Прерывания, fence, hang-recovery | GPU SPI из DT на GICv3 XNU, timestamp-fence (`CACHE_FLUSH_TS`), детект зависания, сброс через GMU | Команда завершается по прерыванию, зависание не вешает систему | средний |
| **G5** | Сервис в ядре и userclient | IOKit-сервис (по образцу HakiosGPU): выделение буфера, отображение в SMMU (iova), submit, ожидание fence; тестовая утилита в userland | Тест из userland выполняет команду и читает результат | средний |
| **G6** | Графика в userland | Mesa freedreno/turnip (a618 поддерживается) с бэкендом под XNU вместо KGSL ioctl; GLES-композитинг QuartzCore вместо CPU; обмен буферами с IOSurface | SpringBoard рисует на GPU, UI заметно быстрее | **высокий и самый объёмный** |
| **G7** | Питание и частоты | DVFS через GMU (GPU_SET), idle-suspend, терморежим | GPU не греет в простое, частота следует нагрузке | средний |

Видимое пользователю ускорение появляется только на G6. G3 — первый «зелёный» результат в логе (команда исполнилась).

## Параллельная дорожка: лаги и стабильность (не GPU)
- **cpufreq:** сейчас частоты ядер остаются как оставил ABL. Образец: HakiOS `hakios.cpufreq.c`; источник частот на surya проверить по DT.
- **8 ядер:** нестабильны (наблюдение владельца), основной образ — 6 ядер. Гипотеза: A55 и A76 в одном однородном кластере XNU, нет cpufreq.
  Не проверено; собрать лог сбоя.

## Принципы безопасности
- Не писать в PMIC/TZ/XPU-защищённые области вслепую; запись только после чтения и сверки с Linux/Xiaomi.
- Каждый шаг пишет в консоль до обращения (чтобы после тихой перезагрузки было видно, где остановились), как в HakiOS (`adreno_pause`).
- Образец размеров/смещений: Linux `drivers/gpu/drm/msm/adreno/a6xx_gmu.c`, `registers/adreno/a6xx.xml`, Xiaomi `adreno_a6xx.c` (surya-q-oss).
- Хакинтош понадобится к G3: правок ядра будет много; локальная сборка на macOS заметно ускоряет цикл.

## Источники
HakiOS `oosexgang/hackios-xnu-kernel` (лицензия: ядро APSL 2.0, остальное MIT), Linux `msm/adreno`, MiCode Xiaomi_Kernel_OpenSource (`surya-q-oss`),
UniXNU (ArmSmmu4K, NativeAdrenoABI — A740-специфичный, A6xx не переносится), Mesa `docs.mesa3d.org/drivers/freedreno.html`.

## G3 — конкретика (разобрано 2026-10-28 по Linux `a6xx_gpu.c` и `registers/adreno/a6xx.xml`, `adreno_pm4.xml`)

Подтверждено на железе до G3: GX включён, RBBM читается, TrustZone авторизует zap (G2). Порядок Linux `a6xx_hw_init`, урезанный до необходимого:

1. Снять GBIF-halt: `GBIF_HALT`(0xf114)=0, `RBBM_GBIF_HALT`(0x58)=0 (A618 — не A630, у неё есть GBIF). `RBBM_SECVID_TSB_CNTL`(0x3e00c)=0,
   `RBBM_SECVID_TSB_TRUSTED_BASE`(0x3e000, 64 бита)=0, `..._SIZE`(0x3e008)=0.
2. 64-битная адресация блоков (=1): `CP`(0x2108) `VSC`(0x3004) `GRAS`(0x21804) `RB`(0x23814) `PC`(0x27804) `HLSQ`(0x2f814) `VFD`(0x29804)
   `VPC`(0x25804) `UCHE`(0x3800) `SP`(0x2b804) `TPL1`(0x2d804) `RBBM_SECVID_TSB`(0x3e040) `_ADDR_MODE_CNTL`.
3. Прочее: `RBBM_VBIF_CLIENT_QOS_CNTL`(0x40)=3, `RBBM_PERFCTR_GPU_BUSY_MASKED`(0x142c)=0xffffffff, `UCHE_WRITE_RANGE_MAX`(0x3814)/`TRAP_BASE`(0x3824)/`WRITE_THRU_BASE`(0x381c)
   (64 бита; база = uche_trap_base), `UCHE_GMEM_RANGE_MIN/MAX`(0x382c/0x3834)=0x100000/…, `UCHE_FILTER_CNTL`(0x3860)=0x804, `UCHE_CACHE_WAYS`(0x385c)=4,
   `CP_ROQ_THRESHOLDS_2/1`(0x2308/0x2304)=0x010000c0/0x8040362c, `CP_MEM_POOL_SIZE`(0x230c)=128, `CP_AHB_CNTL`(0x2634)=1, `RBBM_PERFCTR_CNTL`(0x1400)=1,
   `RBBM_INTERFACE_HANG_INT_CNTL`(0x7c)=(1<<30)|0x1fffff, `UCHE_CLIENT_PF`(0x3864)=0x81. (HWCG, UBWC, CP_PROTECT пока пропускаем.)
4. Микрокод и кольцо: `CP_SQE_INSTR_BASE`(0x2058, 64 бита)=IOVA SQE (`a630_sqe.fw`), `CP_RB_BASE`(0x2000, 64 бита)=IOVA кольца, `CP_RB_CNTL`(0x2008)=default
   (| NO_UPDATE если нет RPTR-shadow), `CP_RB_RPTR_ADDR`(0x2010, 64 бита) при shadow. Старт: `CP_SQE_CNTL`(0x2020)=1.
5. Первая команда: PKT7 `CP_ME_INIT`(0x48), 8 слов: 0x2f, 0x3, 0x20000000, 0,0,0,0,0; запись wptr в `CP_RB_WPTR`(0x201c); ждать `rptr==wptr` и RBBM_STATUS idle.
6. Выход из secure mode: после загрузки zap (G2, но НЕ отдавать обратно) — PKT7 `CP_SET_SECURE_MODE`(0x66) со словом 0; затем тест: PKT7 `CP_MEM_WRITE`(0x3d) в нашу страницу.
   Заголовок PKT7: `(7<<28) | count | parity(count)<<15 | (opcode&0x7f)<<16 | parity(opcode)<<23` (исправлено: у Linux `PKT7`, бит чётности счётчика — 15, не 7).
- Все обращения GPU к памяти (микрокод, кольцо, цель записи) идут через SMMU CB0: нужны таблицы с этими страницами и привязка потока 0
  (на этом телефоне S2CR0 читается 0x200ff, библиотека требует ровно FAULT: привязку делаем отдельно с read-back).
- Порядок проверок на железе: **G3a** только регистры шагов 1–3 (запись и read-back, без CP), **G3b** SMMU + микрокод + кольцо + `CP_ME_INIT`,
  **G3c** zap остаётся авторизованным, `CP_SET_SECURE_MODE`, `CP_MEM_WRITE`.
