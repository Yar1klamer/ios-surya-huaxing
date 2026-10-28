# Изучение исходников драйверов (2026-10-28, ночь)

Источники (лежат в `research/src/` и `research/a6xx-src/`, в git НЕ попадают; клонируются заново командами ниже):
- `research/src/xiaomi` — `MiCode/Xiaomi_Kernel_OpenSource`, ветка `surya-q-oss`, sparse: `drivers/gpu/msm`, `arch/arm64/boot/dts/qcom`, `drivers/iommu`, `drivers/soc/qcom`, `drivers/cpufreq`, `drivers/devfreq`
  (`git clone --depth 1 --filter=blob:none --sparse -b surya-q-oss https://github.com/MiCode/Xiaomi_Kernel_OpenSource xiaomi && git sparse-checkout set …`). Это драйвер KGSL, реально работающий на нашем телефоне.
- `research/src/hackios` — `oosexgang/hackios-xnu-kernel` (HakiOS, POCO X5 Pro: другой SoC, адреса не копировать).
- `research/a6xx-src` — `a6xx.xml` (Mesa), `a6xx_gpu.c`, `adreno_gpu.c`, `a6xx_catalog.c` (Linux).

## GPU: как KGSL запускает CP на нашем телефоне (adreno_a6xx.c, `a6xx_rb_start`, `a6xx_microcode_load`, `a6xx_send_cp_init`)
Порядок KGSL:
1. `CP_RB_RPTR_ADDR` = адрес скретч-слова; `CP_RB_CNTL` = `A6XX_CP_RB_CNTL_DEFAULT` (**без** NO_UPDATE: GPU сам пишет rptr в память); `CP_RB_BASE`.
2. `a6xx_microcode_load`: `CP_SQE_INSTR_BASE` (LO/HI); затем **загрузка zap-шейдера через PIL (`subsystem_get`) — ДО запуска CP; zap остаётся загруженным** (`zap_handle_ptr`), пока GPU включён.
3. `CP_SQE_CNTL = 1`.
4. `CP_ME_INIT` 11 слов: маска `0x17f`, `3`, `0x20000000`, `0,0` (header dump), `0` (ucode workaround), `2` (operation mode), список pwrup-регистров (lo, hi, 0).
5. `adreno_set_unsecured_mode`: при загруженном zap — пакет `CP_SET_SECURE_MODE 0` через кольцо; иначе запись `RBBM_SECVID_TRUST_CNTL=0`.
6. Перед всем этим в `a6xx_start`: `CP_PROTECT_CNTL=3` и таблица защиты, и др.
Linux (`a6xx_hw_init`) делает то же, но ME_INIT 8 слов (`0x2f,3,0x20000000,0…`), и zap грузит ПОСЛЕ ME_INIT; в комментарии Linux прямо сказано: если zap не загружен, а GPU в secure-режиме, доступ к `RBBM_SECVID_TRUST_CNTL` блокируется «и скоро последует нарушение прав».

### Вывод (подтверждено чтением кода, не запуском)
**Мы запускали CP при ОТОЗВАННОМ zap**: патч 0099 в конце цикла делает `PAS_SHUTDOWN`. В KGSL zap живёт всё время работы CP. Это правдоподобно объясняет сбросы после старта CP (нарушение прав TZ/XPU при работе GPU в secure-режиме без zap) — **гипотеза**, проверяется образом `core2i` (патч 0110: zap остаётся, после ME_INIT идёт `CP_SET_SECURE_MODE 0`).
Другие отличия, учтённые в офлайн-сверке (см. WORKLOG): не программируем `CP_PROTECT`; у A618 в Linux квирк `HAS_CACHED_COHERENT`; микрокод `a630_sqe.fw` (v0x19a) валиден.

## Что ещё лежит в дереве Xiaomi и пригодится
- `drivers/gpu/msm/adreno_a6xx_gmu.c`, `adreno_a6xx.c`: старт/питание GMU, HFI, DCVS (G7).
- `arch/arm64/boot/dts/qcom/sdmmagpie-gpu.dtsi`, `msm-arm-smmu-sm6150.dtsi`: GPU/SMMU узлы (ids, клоки); `sdmmagpie-camera*.dtsi`: камеры (CCI, сенсоры); `sdmmagpie-pm.dtsi`: питание/cpufreq.
- Для лагов и 8 ядер: `drivers/cpufreq`, `drivers/soc/qcom` (cpu bw, `msm_performance`), `sdmmagpie-pm.dtsi`/`sdmmagpie.dtsi` (opp-таблицы CPU) — изучить отдельным заходом.
- Для датчиков: ADSP/SSC (`drivers/soc/qcom`, `sdmmagpie.dtsi` rpmsg-узлы) — не начато.
