"""Патчи для claude-code-telegram v1.6.0 (запускать ПОСЛЕ uv tool install).

Применяет патчи (идемпотентно — повторный запуск ничего не ломает):
  P3       message.py: claude_response = None (фикс "cannot access local variable")
  P4.1     message.py: handle_voice — старт таймера + время распознавания
  P4.2     message.py: handle_voice — итоговая строка времени после ответа Claude
  IMG      image_handler.py: скриншоты — сохранение фото в _tg_images + просьба прочитать
  MENU     orchestrator.py: русские описания команд в выпадающем меню Telegram
  ENV      loader.py: убрать TELEGRAM_BOT_TOKEN из os.environ после загрузки —
           иначе headless-claude, запущенный ботом, наследует токен, его подбирает
           Telegram-плагин Claude Code (bun server.ts) → второй поллер → 409 и
           перезапись меню тремя английскими командами в scope all_private_chats
  RU-*     command.py/auth.py/message.py: русские тексты — приветствие /start,
           кнопки, справка /help, сообщение авторизации, плашка голосового
  FILE     message.py handle_document: живой прогресс («что Claude сейчас
           делает») через on_stream + таймер «Файл обработан за Xс»
  MODEL    command.py/orchestrator.py: команда /model — смена модели Claude
           на лету (sonnet/opus/fable/haiku или точный ID), до перезапуска
  SESSIONS command.py/orchestrator.py: команда /sessions — список последних
           сессий Claude Code с описанием первого сообщения и датой

Запуск: <бот-python> patch_bot.py [--root <site-packages>]
По умолчанию root = реальный site-packages установки uv tool.
ВАЖНО: запускать в ОБЫЧНОМ терминале пользователя (не из сессии Claude) —
иначе правки уйдут в MSIX copy-on-write копию и реальный бот их не увидит.
"""

import py_compile
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if "--root" in sys.argv:
    ROOT = Path(sys.argv[sys.argv.index("--root") + 1])
else:
    ROOT = (
        Path.home()
        / "AppData/Roaming/uv/tools/claude-code-telegram/Lib/site-packages"
    )

MSG = ROOT / "src" / "bot" / "handlers" / "message.py"
IMG = ROOT / "src" / "bot" / "features" / "image_handler.py"
ORCH = ROOT / "src" / "bot" / "orchestrator.py"
LOADER = ROOT / "src" / "config" / "loader.py"
CMD = ROOT / "src" / "bot" / "handlers" / "command.py"
AUTHMW = ROOT / "src" / "bot" / "middleware" / "auth.py"
MCPSRV = ROOT / "src" / "mcp" / "telegram_server.py"
SDKINT = ROOT / "src" / "claude" / "sdk_integration.py"

# (имя, файл, маркер-уже-применён, найти, заменить)
PATCHES = [
    (
        "P3 claude_response=None",
        MSG,
        "claude_response = None",
        r'''        # Run Claude command
        try:
            claude_response = await claude_integration.run_command(
                prompt=message_text,''',
        r'''        # Run Claude command
        claude_response = None
        try:
            claude_response = await claude_integration.run_command(
                prompt=message_text,''',
    ),
    (
        "P4.1 voice timer start",
        MSG,
        "_t0 = _time.perf_counter()",
        r'''    try:
        progress_msg = await update.message.reply_text(
            "🎙️ Transcribing voice message...", parse_mode="HTML"
        )

        voice = update.message.voice
        processed_voice = await voice_handler.process_voice_message(
            voice, update.message.caption
        )

        await progress_msg.edit_text(
            "🤖 Processing transcription with Claude...", parse_mode="HTML"
        )''',
        r'''    try:
        import time as _time
        _t0 = _time.perf_counter()
        progress_msg = await update.message.reply_text(
            "🎙️ Transcribing voice message...", parse_mode="HTML"
        )

        voice = update.message.voice
        processed_voice = await voice_handler.process_voice_message(
            voice, update.message.caption
        )

        _t_voice = _time.perf_counter() - _t0
        await progress_msg.edit_text(
            f"🎙️ Распознано за {_t_voice:.1f}с\n🤖 Обрабатываю в Claude…",
            parse_mode="HTML",
        )
        _t1 = _time.perf_counter()''',
    ),
    (
        "P4.2 voice timer summary",
        MSG,
        "_t_claude = _time.perf_counter() - _t1",
        r'''            await progress_msg.delete()

            for i, message in enumerate(formatted_messages):
                await update.message.reply_text(
                    message.text,
                    parse_mode=message.parse_mode,
                    reply_markup=message.reply_markup,
                    reply_to_message_id=(update.message.message_id if i == 0 else None),
                )
                if i < len(formatted_messages) - 1:
                    await asyncio.sleep(0.5)''',
        r'''            _t_claude = _time.perf_counter() - _t1
            _t_total = _time.perf_counter() - _t0
            await progress_msg.edit_text(
                f"⏱ Распознавание: {_t_voice:.1f}с · Claude: {_t_claude:.1f}с · всего: {_t_total:.1f}с",
                parse_mode="HTML",
            )

            for i, message in enumerate(formatted_messages):
                await update.message.reply_text(
                    message.text,
                    parse_mode=message.parse_mode,
                    reply_markup=message.reply_markup,
                    reply_to_message_id=(update.message.message_id if i == 0 else None),
                )
                if i < len(formatted_messages) - 1:
                    await asyncio.sleep(0.5)''',
    ),
    (
        "IMG screenshots via Read",
        IMG,
        "_tg_images",
        r'''        return ProcessedImage(''',
        r'''        import time as _t
        _dir = self.config.approved_directory / "_tg_images"
        _dir.mkdir(parents=True, exist_ok=True)
        _ip = _dir / ("img_" + str(int(_t.time() * 1000)) + ".jpg")
        _ip.write_bytes(bytes(image_bytes))
        prompt = prompt + "\n\nAn image was saved at: " + str(_ip) + ". Use the Read tool to open that file and respond about the image (describe / analyze / help). Answer any question written in the caption."

        return ProcessedImage(''',
    ),
    (
        "MENU русские описания команд",
        ORCH,
        "Запустить бота и показать справку",
        r'''            commands = [
                BotCommand("start", "Start bot and show help"),
                BotCommand("help", "Show available commands"),
                BotCommand("new", "Clear context and start fresh session"),
                BotCommand("continue", "Explicitly continue last session"),
                BotCommand("end", "End current session and clear context"),
                BotCommand("ls", "List files in current directory"),
                BotCommand("cd", "Change directory (resumes project session)"),
                BotCommand("pwd", "Show current directory"),
                BotCommand("projects", "Show all projects"),
                BotCommand("status", "Show session status"),
                BotCommand("export", "Export current session"),
                BotCommand("actions", "Show quick actions"),
                BotCommand("git", "Git repository commands"),
                BotCommand("restart", "Restart the bot"),
            ]''',
        r'''            commands = [
                BotCommand("start", "Запустить бота и показать справку"),
                BotCommand("help", "Справка по всем командам"),
                BotCommand("new", "Новый диалог (очистить контекст)"),
                BotCommand("continue", "Продолжить прошлый диалог"),
                BotCommand("end", "Завершить диалог и очистить контекст"),
                BotCommand("ls", "Файлы в текущей папке"),
                BotCommand("cd", "Сменить папку: cd <путь>"),
                BotCommand("pwd", "Показать текущую папку"),
                BotCommand("projects", "Список проектов"),
                BotCommand("status", "Статус сессии и расход"),
                BotCommand("export", "Выгрузить текущий диалог"),
                BotCommand("actions", "Быстрые действия"),
                BotCommand("git", "Команды git-репозитория"),
                BotCommand("restart", "Перезапустить бота"),
            ]''',
    ),
    (
        "ENV не отдавать токен дочерним claude",
        LOADER,
        'os.environ.pop("TELEGRAM_BOT_TOKEN", None)',
        r'''        # Apply environment-specific overrides
        settings = _apply_environment_overrides(settings, env)''',
        r'''        # Apply environment-specific overrides
        settings = _apply_environment_overrides(settings, env)

        # Токен уже считан в Settings. Убираем его из окружения, чтобы
        # дочерние claude-процессы (и Telegram-плагин Claude Code в них)
        # не начали поллить этот же токен -> 409 Conflict.
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)''',
    ),
    (
        "RU-START приветствие /start",
        CMD,
        "Это Claude Code в Telegram",
        r'''    welcome_message = (
        f"👋 Welcome to Claude Code Telegram Bot, {escape_html(user.first_name)}!\n\n"
        f"🤖 I help you access Claude Code remotely through Telegram.\n\n"
        f"<b>Available Commands:</b>\n"
        f"• <code>/help</code> - Show detailed help\n"
        f"• <code>/new</code> - Start a new Claude session\n"
        f"• <code>/ls</code> - List files in current directory\n"
        f"• <code>/cd &lt;dir&gt;</code> - Change directory\n"
        f"• <code>/projects</code> - Show available projects\n"
        f"• <code>/status</code> - Show session status\n"
        f"• <code>/actions</code> - Show quick actions\n"
        f"• <code>/git</code> - Git repository commands\n\n"
        f"<b>Quick Start:</b>\n"
        f"1. Use <code>/projects</code> to see available projects\n"
        f"2. Use <code>/cd &lt;project&gt;</code> to navigate to a project\n"
        f"3. Send any message to start coding with Claude!\n\n"
        f"🔒 Your access is secured and all actions are logged.\n"
        f"📊 Use <code>/status</code> to check your usage limits."
        f"{sync_section}"
    )''',
        r'''    welcome_message = (
        f"👋 Привет, {escape_html(user.first_name)}! Это Claude Code в Telegram.\n\n"
        f"🤖 Я даю удалённый доступ к Claude Code прямо из чата.\n\n"
        f"<b>Основные команды:</b>\n"
        f"• <code>/help</code> - Подробная справка\n"
        f"• <code>/new</code> - Новый диалог с Claude\n"
        f"• <code>/ls</code> - Файлы в текущей папке\n"
        f"• <code>/cd &lt;папка&gt;</code> - Сменить папку\n"
        f"• <code>/projects</code> - Список проектов\n"
        f"• <code>/status</code> - Статус сессии\n"
        f"• <code>/actions</code> - Быстрые действия\n"
        f"• <code>/git</code> - Команды git\n\n"
        f"<b>Быстрый старт:</b>\n"
        f"1. <code>/projects</code> - посмотреть проекты\n"
        f"2. <code>/cd &lt;проект&gt;</code> - перейти в проект\n"
        f"3. Напиши любое сообщение - и Claude возьмётся за дело!\n\n"
        f"🔒 Доступ защищён, все действия логируются.\n"
        f"📊 <code>/status</code> - проверить лимиты."
        f"{sync_section}"
    )''',
    ),
    (
        "RU-BTNS кнопки под /start",
        CMD,
        '"📁 Проекты"',
        r'''    keyboard = [
        [
            InlineKeyboardButton(
                "📁 Show Projects", callback_data="action:show_projects"
            ),
            InlineKeyboardButton("❓ Get Help", callback_data="action:help"),
        ],
        [
            InlineKeyboardButton("🆕 New Session", callback_data="action:new_session"),
            InlineKeyboardButton("📊 Check Status", callback_data="action:status"),
        ],
    ]''',
        r'''    keyboard = [
        [
            InlineKeyboardButton(
                "📁 Проекты", callback_data="action:show_projects"
            ),
            InlineKeyboardButton("❓ Справка", callback_data="action:help"),
        ],
        [
            InlineKeyboardButton("🆕 Новый диалог", callback_data="action:new_session"),
            InlineKeyboardButton("📊 Статус", callback_data="action:status"),
        ],
    ]''',
    ),
    (
        "RU-HELP справка /help",
        CMD,
        "Справка по Claude Code Telegram Bot",
        r'''    help_text = (
        "🤖 <b>Claude Code Telegram Bot Help</b>\n\n"
        "<b>Navigation Commands:</b>\n"
        "• <code>/ls</code> - List files and directories\n"
        "• <code>/cd &lt;directory&gt;</code> - Change to directory\n"
        "• <code>/pwd</code> - Show current directory\n"
        "• <code>/projects</code> - Show available projects\n\n"
        "<b>Session Commands:</b>\n"
        "• <code>/new</code> - Clear context and start a fresh session\n"
        "• <code>/continue [message]</code> - Explicitly continue last session\n"
        "• <code>/end</code> - End current session and clear context\n"
        "• <code>/status</code> - Show session and usage status\n"
        "• <code>/export</code> - Export session history\n"
        "• <code>/actions</code> - Show context-aware quick actions\n"
        "• <code>/git</code> - Git repository information\n\n"
        "<b>Session Behavior:</b>\n"
        "• Sessions are automatically maintained per project directory\n"
        "• Switching directories with <code>/cd</code> resumes the session for that project\n"
        "• Use <code>/new</code> or <code>/end</code> to explicitly clear session context\n"
        "• Sessions persist across bot restarts\n\n"
        "<b>Usage Examples:</b>\n"
        "• <code>cd myproject</code> - Enter project directory\n"
        "• <code>ls</code> - See what's in current directory\n"
        "• <code>Create a simple Python script</code> - Ask Claude to code\n"
        "• Send a file to have Claude review it\n\n"
        "<b>File Operations:</b>\n"
        "• Send text files (.py, .js, .md, etc.) for review\n"
        "• Claude can read, modify, and create files\n"
        "• All file operations are within your approved directory\n\n"
        "<b>Security Features:</b>\n"
        "• 🔒 Path traversal protection\n"
        "• ⏱️ Rate limiting to prevent abuse\n"
        "• 📊 Usage tracking and limits\n"
        "• 🛡️ Input validation and sanitization\n\n"
        "<b>Tips:</b>\n"
        "• Use specific, clear requests for best results\n"
        "• Check <code>/status</code> to monitor your usage\n"
        "• Use quick action buttons when available\n"
        "• File uploads are automatically processed by Claude\n\n"
        "Need more help? Contact your administrator."
    )''',
        r'''    help_text = (
        "🤖 <b>Справка по Claude Code Telegram Bot</b>\n\n"
        "<b>Навигация:</b>\n"
        "• <code>/ls</code> - Файлы и папки\n"
        "• <code>/cd &lt;папка&gt;</code> - Перейти в папку\n"
        "• <code>/pwd</code> - Текущая папка\n"
        "• <code>/projects</code> - Список проектов\n\n"
        "<b>Сессии:</b>\n"
        "• <code>/new</code> - Новый диалог (очистить контекст)\n"
        "• <code>/continue [сообщение]</code> - Продолжить прошлый диалог\n"
        "• <code>/end</code> - Завершить диалог и очистить контекст\n"
        "• <code>/status</code> - Статус сессии и расход\n"
        "• <code>/export</code> - Выгрузить историю диалога\n"
        "• <code>/actions</code> - Быстрые действия\n"
        "• <code>/git</code> - Информация о git-репозитории\n\n"
        "<b>Как работают сессии:</b>\n"
        "• На каждую папку проекта - своя сессия, она ведётся автоматически\n"
        "• <code>/cd</code> в папку проекта продолжает его сессию\n"
        "• <code>/new</code> или <code>/end</code> - явно очистить контекст\n"
        "• Сессии переживают перезапуск бота\n\n"
        "<b>Примеры:</b>\n"
        "• <code>cd myproject</code> - зайти в папку проекта\n"
        "• <code>ls</code> - что лежит в текущей папке\n"
        "• <code>Напиши скрипт на Python</code> - задача для Claude\n"
        "• Пришли файл - Claude его разберёт\n\n"
        "<b>Файлы:</b>\n"
        "• Присылай текстовые файлы (.py, .xlsx, .md и т.п.) на разбор\n"
        "• Claude умеет читать, менять и создавать файлы\n"
        "• Все операции - только внутри разрешённой папки\n\n"
        "<b>Безопасность:</b>\n"
        "• 🔒 Защита от выхода за пределы папки\n"
        "• ⏱️ Ограничение частоты запросов\n"
        "• 📊 Учёт и лимиты использования\n"
        "• 🛡️ Проверка и очистка ввода\n\n"
        "<b>Советы:</b>\n"
        "• Формулируй задачу конкретно - результат будет лучше\n"
        "• <code>/status</code> - следить за расходом\n"
        "• Пользуйся кнопками быстрых действий\n"
        "• Голосовые тоже понимаю - просто наговори задачу\n\n"
        "Нужна помощь? Напиши администратору бота."
    )''',
    ),
    (
        "RU-AUTH сообщение авторизации",
        AUTHMW,
        "Доступ подтверждён",
        r'''                f"🔓 Welcome! You are now authenticated.\n"
                f"Session started at {datetime.now(UTC).strftime('%H:%M:%S UTC')}"''',
        r'''                f"🔓 Доступ подтверждён.\n"
                f"Сессия начата в {datetime.now(UTC).strftime('%H:%M:%S UTC')}"''',
    ),
    (
        "RU-VOICE плашка распознавания",
        MSG,
        "Распознаю голосовое",
        r'''            "🎙️ Transcribing voice message...", parse_mode="HTML"''',
        r'''            "🎙️ Распознаю голосовое…", parse_mode="HTML"''',
    ),
    (
        "FILE-1 плашка + старт таймера",
        MSG,
        "Разбираю файл в Claude",
        r'''        # Create a new progress message for Claude processing
        claude_progress_msg = await update.message.reply_text(
            "🤖 Processing file with Claude...", parse_mode="HTML"
        )''',
        r'''        # Create a new progress message for Claude processing
        import time as _time
        _t0 = _time.perf_counter()
        claude_progress_msg = await update.message.reply_text(
            "🤖 Разбираю файл в Claude…", parse_mode="HTML"
        )''',
    ),
    (
        "FILE-2 живой прогресс через on_stream",
        MSG,
        "_doc_stream",
        r'''        # Process with Claude
        try:
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
            )''',
        r'''        # Process with Claude
        async def _doc_stream(update_obj):
            try:
                progress_text = await _format_progress_update(update_obj)
                if progress_text:
                    await claude_progress_msg.edit_text(
                        progress_text, parse_mode="HTML"
                    )
            except Exception as e:
                logger.warning("Failed to update progress message", error=str(e))

        try:
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=_doc_stream,
            )''',
    ),
    (
        "FILE-3 итоговый таймер",
        MSG,
        "Файл обработан за",
        r'''            # Delete progress message
            await claude_progress_msg.delete()

            # Send responses
            for i, message in enumerate(formatted_messages):''',
        r'''            # Delete progress message
            _t_total = _time.perf_counter() - _t0
            await claude_progress_msg.edit_text(
                f"⏱ Файл обработан за {_t_total:.1f}с",
                parse_mode="HTML",
            )

            # Send responses
            for i, message in enumerate(formatted_messages):''',
    ),
    (
        "MODEL-1 команда /model в command.py",
        CMD,
        "_MODEL_ALIASES",
        r'''    await update.message.reply_text(help_text, parse_mode="HTML")''',
        r'''    await update.message.reply_text(help_text, parse_mode="HTML")


_MODEL_ALIASES = {
    "sonnet": "sonnet",
    "opus": "claude-opus-4-8",
    "fable": "claude-fable-5",
    "haiku": "haiku",
}


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сменить модель Claude на лету: /model [sonnet|opus|fable|haiku|<id>]."""
    settings: Settings = context.bot_data["settings"]
    args = context.args or []
    current = settings.claude_model or "(по умолчанию CLI)"
    if not args:
        await update.message.reply_text(
            "🧠 <b>Текущая модель:</b> <code>"
            + escape_html(str(current))
            + "</code>\n\n"
            "Сменить: <code>/model sonnet</code> · <code>/model opus</code> · "
            "<code>/model fable</code> · <code>/model haiku</code>\n"
            "Или точный ID: <code>/model claude-fable-5</code>\n\n"
            "⚠️ Действует до перезапуска бота (постоянная настройка - в .env).",
            parse_mode="HTML",
        )
        return
    choice = args[0].strip().lower()
    new_model = _MODEL_ALIASES.get(choice, args[0].strip())
    settings.claude_model = new_model
    await update.message.reply_text(
        "🧠 Модель переключена: <code>"
        + escape_html(new_model)
        + "</code>\nПодействует со следующего сообщения.",
        parse_mode="HTML",
    )''',
    ),
    (
        "MODEL-2 регистрация /model в orchestrator.py",
        ORCH,
        '("model", command.model_command)',
        r'''            ("git", command.git_command),
            ("restart", command.restart_command),
        ]''',
        r'''            ("git", command.git_command),
            ("restart", command.restart_command),
            ("model", command.model_command),
        ]''',
    ),
    (
        "MODEL-3 пункт /model в меню",
        ORCH,
        'BotCommand("model"',
        r'''                BotCommand("git", "Команды git-репозитория"),
                BotCommand("restart", "Перезапустить бота"),''',
        r'''                BotCommand("git", "Команды git-репозитория"),
                BotCommand("model", "Выбрать модель Claude"),
                BotCommand("restart", "Перезапустить бота"),''',
    ),
    # ── RESUME ────────────────────────────────────────────────────────────────
    (
        "RESUME-1 функция resume_command в command.py",
        CMD,
        "async def resume_command",
        r'''    lines.append("\n▶️ Возобновить: <code>/resume &lt;UUID&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")''',
        r'''    lines.append("\n▶️ Возобновить: <code>/resume &lt;UUID&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возобновить сессию по UUID: /resume <uuid>
    Просто записывает UUID в user_data["claude_session_id"] —
    следующее сообщение автоматически продолжит эту сессию."""
    args = context.args or []
    if not args:
        current = context.user_data.get("claude_session_id", "(не задана)")
        await update.message.reply_text(
            "▶️ <b>Возобновление сессии</b>\n\n"
            f"Текущая: <code>{current}</code>\n\n"
            "Укажи UUID: <code>/resume &lt;UUID&gt;</code>\n"
            "Список сессий: /sessions",
            parse_mode="HTML",
        )
        return
    uuid = args[0].strip()
    # Проверка формата UUID (8-4-4-4-12)
    import re as _re
    if not _re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", uuid, _re.I):
        await update.message.reply_text(
            "❌ Неверный формат UUID.\nОжидается: <code>xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</code>",
            parse_mode="HTML",
        )
        return
    context.user_data["claude_session_id"] = uuid
    await update.message.reply_text(
        f"✅ Сессия установлена:\n<code>{uuid}</code>\n\n"
        "Следующее сообщение продолжит этот диалог.",
        parse_mode="HTML",
    )''',
    ),
    (
        "RESUME-2 регистрация /resume в orchestrator.py",
        ORCH,
        '("resume", command.resume_command)',
        r'''            ("sessions", command.sessions_command),
        ]''',
        r'''            ("sessions", command.sessions_command),
            ("resume", command.resume_command),
        ]''',
    ),
    (
        "RESUME-3 пункт /resume в меню",
        ORCH,
        'BotCommand("resume"',
        r'''                BotCommand("sessions", "Список последних сессий"),
                BotCommand("restart", "Перезапустить бота"),''',
        r'''                BotCommand("sessions", "Список последних сессий"),
                BotCommand("resume", "Продолжить сессию по UUID"),
                BotCommand("restart", "Перезапустить бота"),''',
    ),
    # ── SESSIONS ──────────────────────────────────────────────────────────────
    (
        "SESSIONS-1 функция sessions_command в command.py",
        CMD,
        "async def sessions_command",
        r'''    await update.message.reply_text(
        "🧠 Модель переключена: <code>"
        + escape_html(new_model)
        + "</code>\nПодействует со следующего сообщения.",
        parse_mode="HTML",
    )''',
        r'''    await update.message.reply_text(
        "🧠 Модель переключена: <code>"
        + escape_html(new_model)
        + "</code>\nПодействует со следующего сообщения.",
        parse_mode="HTML",
    )


async def sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать последние сессии Claude Code с описанием первого сообщения."""
    import json as _json
    from pathlib import Path as _Path
    from datetime import datetime as _dt

    projects_dir = _Path.home() / ".claude" / "projects"

    # Имена папок: ~/claude-tg/sessions-names.json
    # ({"<slug>": "имя", "<slug>": null} — null скрывает папку).
    _labels = {}
    _names_file = _Path.home() / "claude-tg" / "sessions-names.json"
    try:
        _labels = _json.loads(_names_file.read_text(encoding="utf-8"))
    except Exception:
        pass

    if not projects_dir.exists():
        await update.message.reply_text("❌ Папка сессий не найдена.")
        return

    sessions = []
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        label = _labels.get(proj_dir.name, proj_dir.name[:18])
        if label is None:
            continue   # пропускаем шумные папки
        for jsonl in proj_dir.glob("*.jsonl"):
            mtime = jsonl.stat().st_mtime
            sessions.append((mtime, jsonl, label))

    sessions.sort(key=lambda x: x[0], reverse=True)
    sessions = sessions[:12]

    if not sessions:
        await update.message.reply_text("Сессий не найдено.")
        return

    lines = ["📋 <b>Последние сессии Claude Code:</b>\n"]
    for i, (mtime, path, label) in enumerate(sessions, 1):
        dt_str = _dt.fromtimestamp(mtime).strftime("%d.%m %H:%M")
        uuid = path.stem
        first_msg = ""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = _json.loads(line)
                        if (
                            entry.get("type") == "queue-operation"
                            and entry.get("operation") == "enqueue"
                            and entry.get("content")
                        ):
                            first_msg = entry["content"].replace("\n", " ")[:65]
                            break
                    except Exception:
                        pass
        except Exception:
            pass
        lines.append(
            f"{i}. [{dt_str}] <b>{label}</b>\n"
            f"   {first_msg or '(нет текста)'}\n"
            f"   <code>{uuid}</code>"
        )

    lines.append("\n▶️ Возобновить: <code>/resume &lt;UUID&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")''',
    ),
    (
        "SESSIONS-2 регистрация /sessions в orchestrator.py",
        ORCH,
        '("sessions", command.sessions_command)',
        r'''            ("restart", command.restart_command),
            ("model", command.model_command),''',
        r'''            ("restart", command.restart_command),
            ("model", command.model_command),
            ("sessions", command.sessions_command),''',
    ),
    (
        "SESSIONS-3 пункт /sessions в меню",
        ORCH,
        'BotCommand("sessions"',
        r'''                BotCommand("model", "Выбрать модель Claude"),
                BotCommand("restart", "Перезапустить бота"),''',
        r'''                BotCommand("model", "Выбрать модель Claude"),
                BotCommand("sessions", "Список последних сессий"),
                BotCommand("restart", "Перезапустить бота"),''',
    ),
    # ── OUT: выгрузка файлов (md/txt/любых) в Telegram ───────────────────────
    (
        "OUT-1 MCP-инструмент send_file_to_user",
        MCPSRV,
        "send_file_to_user",
        r'''if __name__ == "__main__":
    mcp.run(transport="stdio")''',
        r'''@mcp.tool()
async def send_file_to_user(file_path: str, caption: str = "") -> str:
    """Send any file (md, txt, csv, xlsx, docx, pdf, ...) to the Telegram user as a document.

    Use this whenever the user asks to export, download or receive content as
    a file (e.g. "выгрузи в md", "пришли файлом", "сохрани в txt и отправь").
    First write the file to disk (UTF-8 for text formats), then call this
    tool with the absolute path.

    Args:
        file_path: Absolute path to the file.
        caption: Optional caption.

    Returns:
        Confirmation string when the file is queued for delivery.
    """
    path = Path(file_path)

    if not path.is_absolute():
        return f"Error: path must be absolute, got '{file_path}'"

    if not path.is_file():
        return f"Error: file not found: {file_path}"

    if path.stat().st_size > 50 * 1024 * 1024:
        return "Error: file exceeds the 50 MB Telegram limit"

    return f"File queued for delivery: {path.name}"


if __name__ == "__main__":
    mcp.run(transport="stdio")''',
    ),
    (
        "STRICT strict_mcp_config — грузить только наш MCP-сервер",
        SDKINT,
        "strict_mcp_config=",
        r'''            # Build Claude Agent options
            options = ClaudeAgentOptions(
                max_turns=self.config.claude_max_turns,''',
        r'''            # Build Claude Agent options
            options = ClaudeAgentOptions(
                # ТОЛЬКО наш telegram-MCP: игнорируем глобальные серверы из
                # ~/.claude.json (patapim-browser и т.п.), которые висли на
                # initialize → "Control request timeout".
                strict_mcp_config=bool(self.config.enable_mcp),
                # Поднимаем лимит буфера парсера потокового JSON с дефолтных
                # 1 МБ до 20 МБ: крупные tool-результаты / чтение больших
                # файлов давали "JSON message exceeded maximum buffer size".
                max_buffer_size=20 * 1024 * 1024,
                max_turns=self.config.claude_max_turns,''',
    ),
    (
        "SENDFILE инструкция в системный промпт",
        SDKINT,
        "ВЫГРУЗКА ФАЙЛОВ ПОЛЬЗОВАТЕЛЮ",
        r'''            base_prompt = (
                f"All file operations must stay within {working_directory}. "
                "Use relative paths."
            )''',
        r'''            base_prompt = (
                f"All file operations must stay within {working_directory}. "
                "Use relative paths."
                "\n\n## ВЫГРУЗКА ФАЙЛОВ ПОЛЬЗОВАТЕЛЮ (Telegram)\n"
                "Ты работаешь как Telegram-бот. Когда пользователь просит "
                "ПРИСЛАТЬ, ВЫГРУЗИТЬ, СКАЧАТЬ или ОТПРАВИТЬ что-либо ФАЙЛОМ "
                "(например: «пришли файлом», «выгрузи в md», «сохрани в txt и "
                "отправь», «скинь файл», «дай excel/csv»), ты ОБЯЗАН:\n"
                "1) сохранить содержимое в файл по АБСОЛЮТНОМУ пути внутри "
                f"{working_directory} инструментом Write (текст — в UTF-8);\n"
                "2) вызвать инструмент send_file_to_user с этим абсолютным "
                "путём (file_path) и кратким caption.\n"
                "НИКОГДА не вставляй содержимое файла код-блоком в чат вместо "
                "реальной отправки — пользователю нужен сам файл-вложение. "
                "Для картинок используй send_image_to_user."
            )'''
    ),
    (
        "OUT-2 перехват send_file_to_user в message.py",
        MSG,
        "__send_file_to_user",
        r'''                    if tc_name == "send_image_to_user" or tc_name.endswith(
                        "__send_image_to_user"
                    ):
                        tc_input = tc.get("input", {})
                        file_path = tc_input.get("file_path", "")
                        caption = tc_input.get("caption", "")
                        img = validate_image_path(
                            file_path, settings.approved_directory, caption
                        )
                        if img:
                            mcp_images.append(img)''',
        r'''                    if tc_name == "send_image_to_user" or tc_name.endswith(
                        "__send_image_to_user"
                    ):
                        tc_input = tc.get("input", {})
                        file_path = tc_input.get("file_path", "")
                        caption = tc_input.get("caption", "")
                        img = validate_image_path(
                            file_path, settings.approved_directory, caption
                        )
                        if img:
                            mcp_images.append(img)
                    elif tc_name == "send_file_to_user" or tc_name.endswith(
                        "__send_file_to_user"
                    ):
                        from pathlib import Path as _Path

                        tc_input = tc.get("input", {})
                        _fp = tc_input.get("file_path", "")
                        try:
                            _p = _Path(_fp).resolve()
                            # только внутри разрешённой папки бота
                            _p.relative_to(
                                settings.approved_directory.resolve()
                            )
                            if (
                                _p.is_file()
                                and _p.stat().st_size <= 50 * 1024 * 1024
                            ):
                                mcp_images.append(
                                    ImageAttachment(
                                        path=_p,
                                        mime_type="application/octet-stream",
                                        original_reference=_fp,
                                    )
                                )
                        except Exception:
                            logger.warning(
                                "send_file_to_user: rejected path", path=_fp
                            )''',
    ),
]


def main() -> int:
    try:
        import importlib.metadata as md

        ver = md.version("claude-code-telegram")
        print(f"Версия бота: {ver}")
        if ver != "1.6.0":
            print("[!] Ожидалась 1.6.0 — якоря могут не совпасть, продолжаю осторожно.")
    except Exception:
        pass

    failed = 0
    # Несколько проходов: патч может зависеть от кода, который создаёт другой
    # патч (например, RESUME цепляется за код из SESSIONS-1) — отложенные
    # применяются на следующем круге.
    pending = list(PATCHES)
    for _pass in (1, 2, 3):
        progressed = False
        deferred = []
        for entry in pending:
            name, path, marker, find, replace = entry
            if not path.exists():
                print(f"[!] {name}: файл не найден: {path}")
                failed += 1
                continue
            text = path.read_text(encoding="utf-8")
            if marker in text:
                print(f"[=] {name}: уже применён, пропускаю")
                continue
            if text.count(find) != 1:
                deferred.append(entry)
                continue
            path.write_text(text.replace(find, replace), encoding="utf-8", newline="\n")
            print(f"[+] {name}: применён")
            progressed = True
        pending = deferred
        if not pending or not progressed:
            break
    for name, path, marker, find, replace in pending:
        print(f"[!] {name}: якорь не найден ни в одном проходе — НЕ применён. Скажи Claude.")
        failed += 1

    for f in (MSG, IMG, ORCH, LOADER, CMD, AUTHMW, MCPSRV, SDKINT):
        if f.exists():
            try:
                py_compile.compile(str(f), doraise=True)
                print(f"[ok] компилируется: {f.name}")
            except py_compile.PyCompileError as e:
                print(f"[!!] НЕ КОМПИЛИРУЕТСЯ {f.name}: {e}")
                failed += 1

    if failed:
        print(f"\nГОТОВО С ОШИБКАМИ: {failed}. Перезапускать бота можно, но скажи Claude.")
        return 1
    print("\nГОТОВО. Запускай Claude-Bot.cmd / Claude-Bot-Wife.cmd.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
