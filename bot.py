"""
Telegram Bot — Google Sheets Logger
Every incoming message is appended to a Google Sheet with timestamp,
user info, and message text. Runs in webhook mode for production use.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID: str = os.environ["SPREADSHEET_ID"]
WORKSHEET_NAME: str = os.getenv("WORKSHEET_NAME", "Logs")

WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")        # e.g. https://yourdomain.com
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

SCOPES: list[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ---------------------------------------------------------------------------
# Google Sheets client
# ---------------------------------------------------------------------------

class SheetsLogger:
    """Append rows to a Google Sheet using a service account."""

    def __init__(self, credentials_file: str, spreadsheet_id: str, worksheet_name: str) -> None:
        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._sheet = self._client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        self._ensure_header()

    def _ensure_header(self) -> None:
        """Add header row if the sheet is empty."""
        if not self._sheet.row_values(1):
            self._sheet.append_row(
                ["Timestamp (UTC)", "User ID", "Username", "First Name", "Message"],
                value_input_option="USER_ENTERED",
            )
            logger.info("Header row created in Google Sheet.")

    def log(
        self,
        user_id: int,
        username: str,
        first_name: str,
        message: str,
    ) -> None:
        """Append a single message row to the sheet."""
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._sheet.append_row(
            [timestamp, str(user_id), username or "", first_name or "", message],
            value_input_option="USER_ENTERED",
        )
        logger.info("Logged message from @%s (id=%d)", username, user_id)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

sheets_logger = SheetsLogger(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID, WORKSHEET_NAME)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message on /start."""
    await update.message.reply_text(
        "Hello! Every message you send will be logged to Google Sheets automatically."
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log every text message to Google Sheets and confirm to user."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text

    try:
        sheets_logger.log(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
            message=text,
        )
        await update.message.reply_text("Logged to Google Sheets.")
    except Exception as exc:
        logger.error("Failed to log message: %s", exc)
        await update.message.reply_text("Could not save your message. Please try again.")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return basic bot status on /status."""
    await update.message.reply_text(
        f"Bot is running.\nSheet ID: {SPREADSHEET_ID}\nWorksheet: {WORKSHEET_NAME}"
    )


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    return app


# ---------------------------------------------------------------------------
# Entry point — webhook mode (production) or polling (local dev)
# ---------------------------------------------------------------------------

def main() -> None:
    app = build_app()

    if WEBHOOK_URL:
        logger.info("Starting in webhook mode on port %d", WEBHOOK_PORT)
        app.run_webhook(
            listen="0.0.0.0",
            port=WEBHOOK_PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}",
            secret_token=WEBHOOK_SECRET or None,
        )
    else:
        logger.info("Starting in polling mode (local dev)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
