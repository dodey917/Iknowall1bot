import os
import json
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram.error import Conflict
from google_doc import GoogleDocQA  # Import the GoogleDocQA class

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID')
GOOGLE_CREDENTIALS = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))

# Admin user IDs
ADMIN_IDS = [7697559889, 6089861817]

# Initialize the Q&A system
qa_system = GoogleDocQA()

# Telegram Bot Handlers with Naija flavor
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("How you dey my guy! I be your Q&A bot. Ask me anything!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 I be Q&A bot wey dey use Google Docs!\n\n"
        "Wetin I fit do:\n"
        "/start - Welcome message\n"
        "/help - See this message\n"
        "/refresh - For admin to update knowledge\n\n"
        "Just ask me question make I answer you!"
    )
    await update.message.reply_text(help_text)

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to force refresh"""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("Oga, you no get power for this command!")
        return
    
    if qa_system.refresh_qa_pairs(force=True):
        await update.message.reply_text("Knowledge don fresh like new born baby!")
    else:
        await update.message.reply_text("E don burst! No fit update knowledge now.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ['group', 'supergroup']:
        if not update.message.text.startswith('@your_bot_username'):
            return
    
    answer = qa_system.get_answer(update.message.text)
    await update.message.reply_text(answer)

def main():
    try:
        logger.info("Bot don start...")
        
        if not qa_system.refresh_qa_pairs(force=True):
            logger.error("E don burst! No fit connect to Google Docs")
            return
        
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Command handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("refresh", refresh_command))
        
        # Message handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("De run polling...")
        app.run_polling(
            poll_interval=3,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Conflict as e:
        logger.error("Another bot dey run already. I go stop.")
    except Exception as e:
        logger.error(f"Wahala don happen: {e}")
    finally:
        logger.info("Bot don stop")

if __name__ == "__main__":
    main()
