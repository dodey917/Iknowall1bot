import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from datetime import datetime, timedelta

# Load environment variables with validation
def load_env_vars():
    required_vars = ['BOT_TOKEN', 'GOOGLE_DOC_ID', 'GOOGLE_CREDENTIALS_JSON']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    return {
        'BOT_TOKEN': os.getenv('BOT_TOKEN'),
        'GOOGLE_DOC_ID': os.getenv('GOOGLE_DOC_ID'),
        'GOOGLE_CREDENTIALS_JSON': json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON')),
        'ADMIN_IDS': [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(",") if id.strip()],
        'PORT': int(os.getenv('PORT', 10000)),
        'WEBHOOK_URL': os.getenv('WEBHOOK_URL'),
        'RENDER': os.getenv('RENDER', 'false').lower() == 'true'
    }

# Initialize with error handling
try:
    config = load_env_vars()
except Exception as e:
    logging.error(f"Configuration error: {e}")
    raise

# Rest of your bot code remains the same, using config['BOT_TOKEN'] etc.
# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Global variables for caching
cached_responses = {}
last_update_time = None
CACHE_EXPIRY_MINUTES = 30  # Refresh cache every 30 minutes

# Initialize Google Docs service
def init_google_docs():
    try:
        creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
        credentials = service_account.Credentials.from_service_account_info(creds_json)
        service = build("docs", "v1", credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Error initializing Google Docs service: {e}")
        raise

# Fetch and parse the Google Doc
async def fetch_responses(force_refresh=False):
    global cached_responses, last_update_time

    # Check if cache is still valid
    if (
        not force_refresh
        and last_update_time
        and datetime.now() - last_update_time < timedelta(minutes=CACHE_EXPIRY_MINUTES)
    ):
        return cached_responses

    try:
        service = init_google_docs()
        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        doc_content = doc.get("body", {}).get("content", [])

        responses = {}
        current_question = None
        current_answer = []

        for element in doc_content:
            if "paragraph" in element:
                for paragraph_element in element["paragraph"]["elements"]:
                    if "textRun" in paragraph_element:
                        text = paragraph_element["textRun"]["content"].strip()

                        # Check if this is a question
                        if text.lower().startswith("q:"):
                            # Save previous question if exists
                            if current_question:
                                responses[current_question.lower()] = " ".join(current_answer).strip()
                            current_question = text[2:].strip()
                            current_answer = []
                        # Check if this is an answer
                        elif text.lower().startswith("a:"):
                            current_answer.append(text[2:].strip())

        # Add the last question-answer pair if exists
        if current_question:
            responses[current_question.lower()] = " ".join(current_answer).strip()

        # Update cache
        cached_responses = responses
        last_update_time = datetime.now()
        logger.info(f"Updated responses cache with {len(responses)} Q&A pairs")

        return responses
    except HttpError as error:
        logger.error(f"An error occurred: {error}")
        return cached_responses if not force_refresh else {}
    except Exception as e:
        logger.error(f"Unexpected error fetching responses: {e}")
        return cached_responses if not force_refresh else {}

# Find the best matching response
async def get_response(user_message):
    user_message = user_message.lower().strip()
    responses = await fetch_responses()

    # First try exact match
    if user_message in responses:
        return responses[user_message]

    # Then try partial matches
    for question, answer in responses.items():
        if question in user_message or user_message in question:
            return answer

    # If no match, return a mixed English/Pidgin response
    return "I no sabi answer to that one. Check your question or ask something else."

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Hey {user.first_name}! I Know All dey here to tell you raw truth about life. "
        "Ask me anything, but no expect sugar-coated lies.\n\n"
        "Created by Arewa Michael"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    response = await get_response(user_message)
    await update.message.reply_text(response)

async def refresh_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await fetch_responses(force_refresh=True)
        await update.message.reply_text("Cache don refresh! Bot don update with latest info from Google Doc.")
    else:
        await update.message.reply_text("You no be admin. You no get power to do this one.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and hasattr(update, "message"):
        await update.message.reply_text(
            "Something scatter! Try again small time. Na life just show us pepper."
        )

def main():
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("refresh", refresh_cache))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    # Start the bot
    if RENDER:
        # Run in webhook mode for Render background worker
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            secret_token="RENDER_WEBHOOK_SECRET",
        )
        logger.info("Bot running in production mode with webhook")
    else:
        # Run in polling mode for local development
        application.run_polling()
        logger.info("Bot running in development mode with polling")

if __name__ == "__main__":
    # Initial cache load
    import asyncio
    asyncio.run(fetch_responses(force_refresh=True))
    main()
