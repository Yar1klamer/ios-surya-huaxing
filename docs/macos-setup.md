# Работа на хакинтоше (macOS 15): сборка ядра, образы, fastboot

Зачем: ядро XNU собирается только на macOS. На хакинтоше сборка идёт локально (без очереди GitHub), а `fastboot`, сборка
образа и телефон лежат на одной машине. Контекст проекта — `WORKLOG.md`, `NOTES.md`, `docs/gpu-plan.md`.

## Один раз
1. **Xcode 15.4** (не новее: Xcode 16 ломает `iig`, этому XNU нужна 15.x). Скачать `.xip` со страницы
   https://developer.apple.com/download/all/ (бесплатный Apple ID, вход выполняет владелец), распаковать, переместить в «Программы»,
   запустить один раз и принять лицензию: `sudo xcodebuild -license accept`. На macOS 15 Xcode 15.4 официально не заявлен,
   обычно запускается; если нет — писать, подберём вариант.
2. **Homebrew не нужен** (он больше не поддерживает Intel-Маки). `jq` есть в macOS 15, `cmake` и `ninja` скрипт ставит сам через `pip` в
   свою папку, `fastboot`/`adb` берутся из Google platform-tools (на этом Mac они в `~/platform-tools`).
3. Нужны только `git` и `python3` (уже есть). Установка Kernel Debug Kit при первой сборке просит пароль администратора (`sudo installer`):
   запускайте скрипт сборки в Терминале.
4. **Репозиторий**: `git clone https://github.com/Yar1klamer/ios-surya-huaxing && cd ios-surya-huaxing` (если папка уже есть от оригинального `arbuxiktech/ios-surya`: `git remote add fork https://github.com/Yar1klamer/ios-surya-huaxing.git && git fetch fork && git merge --ff-only fork/main`, пуш — `git push fork main`).
   Для `git push` авторизоваться в GitHub самому (ваши данные; токен, выданный раньше для Windows-сессии, сюда не переносить).
5. **Комплект файлов** (то, чего нет в git: прошивки с телефона, shim, ADT, stock DTB, mkbootimg), 0,9 МБ:
   `scp burmalda@192.168.1.112:macos-bundle.tgz .` (или с флешки, `research/macos-bundle.tgz` на Windows), затем
   `mkdir -p research && tar xzf macos-bundle.tgz -C research` → появится `research/macos-bundle/`. Проверка: `cd research/macos-bundle && shasum -a 256 -c SHA256SUMS`.
6. **Claude Code** в этой папке (тот же репозиторий).

## Сборка ядра и образа
- Ядро: `bash tools/build-kernel-macos.sh` → `research/kernel-local/kernel.development.surya` (первая сборка с нуля, долго; скрипт ещё не проверен на
  вашей машине, при ошибке — прислать последние строки вывода).
- Образ: `tools/make-boot-image.sh research/kernel-local/kernel.development.surya PROFILE out.img` (PROFILE: `gui`, `touch`, `gpu`, `gpu-zap`, `diag`).
  Скрипт проверен на Windows: образ G2 совпал байт в байт с собранным на Linux-хосте.
- Загрузка (временная, ничего не прошивается): телефон в fastboot, `fastboot devices`, `fastboot boot out.img`.
  Если `Unrecognized command boot` — телефон в fastbootd: `fastboot reboot bootloader` и повторить.

## Что НЕ переносить
Токены/пароли, ключ `id_claude_surya`, дампы устройства с серийниками. `research/` в git не попадает.
