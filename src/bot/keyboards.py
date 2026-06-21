"""Shared persistent reply-keyboard used by both classic and agentic modes.

The keyboard is "always on the bottom" — buttons stay visible while the user
types. Tapping a button sends its label as a regular text message; text
handlers intercept these labels BEFORE forwarding to Claude so they don't
leak as prompts.
"""

from telegram import KeyboardButton, ReplyKeyboardMarkup

# Button labels (these texts must match exactly to be intercepted).
BTN_STOP = "⏹ Стоп"
BTN_NEW = "\U0001f504 Новый"  # 🔄 Новый
BTN_STATUS = "\U0001f4ca Статус"  # 📊 Статус

QUICK_ACTION_BUTTONS = {BTN_STOP, BTN_NEW, BTN_STATUS}

MAIN_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_STOP), KeyboardButton(BTN_NEW), KeyboardButton(BTN_STATUS)]],
    resize_keyboard=True,
    is_persistent=True,
)
