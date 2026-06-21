"""Shared persistent reply-keyboard used by both classic and agentic modes.

The keyboard is "always on the bottom" — buttons stay visible while the user
types. Tapping a button sends its label as a regular text message; text
handlers intercept these labels BEFORE forwarding to Claude so they don't
leak as prompts.
"""

from telegram import ReplyKeyboardRemove

# Button labels kept for backward compatibility: the text-interception logic
# still recognises these strings if an old client sends them, but the
# persistent keyboard itself is disabled — the actions live as slash commands
# (/stop, /new, /status) in the bot's "/" menu instead.
BTN_STOP = "⏹ Стоп"
BTN_NEW = "\U0001f504 Новый"  # 🔄 Новый
BTN_STATUS = "\U0001f4ca Статус"  # 📊 Статус

QUICK_ACTION_BUTTONS = {BTN_STOP, BTN_NEW, BTN_STATUS}

# Previously a persistent ReplyKeyboardMarkup with Стоп/Новый/Статус buttons.
# Replaced with ReplyKeyboardRemove so every message that used to attach the
# keyboard now clears it — no bottom panel, commands stay in the "/" menu.
MAIN_REPLY_KEYBOARD = ReplyKeyboardRemove()
