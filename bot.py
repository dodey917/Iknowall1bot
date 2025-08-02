import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
import json
from datetime import datetime, timedelta

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID')
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
RENDER = os.getenv('RENDER', 'false').lower() == 'true'

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to store cached responses and last update time
cached_responses = {}
last_update_time = None
CACHE_EXPIRY_HOURS = 1  # Refresh cache every hour

# Initialize Google Docs service
def init_google_docs():
    try:
        # Parse the credentials from the environment variable
        creds_json = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
        credentials = service_account.Credentials.from_service_account_info(creds_json)
        service = build('docs', 'v1', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Error initializing Google Docs service: {e}")
        raise

# Fetch and parse the Google Doc
async def fetch_responses():
    global cached_responses, last_update_time
    
    # Check if cache is still valid
    if last_update_time and datetime.now() - last_update_time < timedelta(hours=CACHE_EXPIRY_HOURS):
        return cached_responses
    
    try:
        service = init_google_docs()
        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        doc_content = doc.get('body', {}).get('content', [])
        
        responses = {}
        current_question = None
        current_answer = []
        
        for element in doc_content:
            if 'paragraph' in element:
                for paragraph_element in element['paragraph']['elements']:
                    if 'textRun' in paragraph_element:
                        text = paragraph_element['textRun']['content'].strip()
                        
                        # Check if this is a question
                        if text.lower().startswith('q:'):
                            # If we have a current question, save it before starting new one
                            if current_question:
                                responses[current_question.lower()] = ' '.join(current_answer).strip()
                            
                            current_question = text[2:].strip()
                            current_answer = []
                        # Check if this is an answer
                        elif text.lower().startswith('a:'):
                            current_answer.append(text[2:].strip())
        
        # Add the last question-answer pair if it exists
        if current_question:
            responses[current_question.lower()] = ' '.join(current_answer).strip()
        
        # Update cache
        cached_responses = responses
        last_update_time = datetime.now()
        logger.info(f"Updated responses cache with {len(responses)} Q&A pairs")
        
        return responses
    except HttpError as error:
        logger.error(f"An error occurred: {error}")
        return cached_responses  # Return cached version if available
    except Exception as e:
        logger.error(f"Unexpected error fetching responses: {e}")
        return cached_responses  # Return cached version if available

# Find the best matching response
async def find_best_response(user_message, responses):
    user_message = user_message.lower().strip()
    
    # First try exact match
    if user_message in responses:
        return responses[user_message]
    
    # Then try partial matches
    for question, answer in responses.items():
        if question in user_message or user_message in question:
            return answer
    
    # If no direct match, try to find keywords and combine answers
    keywords = [
        'who', 'what', 'when', 'where', 'why', 'how',
        'are you', 'can you', 'will you', 'do you',
        'is it', 'am i', 'should i', 'life', 'fact'
    ]
    
    found_answers = []
    for keyword in keywords:
        if keyword in user_message:
            for q, a in responses.items():
                if keyword in q:
                    found_answers.append(a)
    
    if found_answers:
        # Combine the answers with some Nigerian flavor
        combined = "Abeg, no vex. From wetin I sabi: \n\n" + "\n\n".join(found_answers[:3])
        return combined + "\n\nNo be me talk am, na life show us."
    
    # Default response if nothing matches
    return "Ah-ah! I no fit find answer for your question for my database. Na wa o! Life hard sha."

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Wetin you want? I Know All dey here to tell you raw truth about life. "
        "Ask me anything, but no expect sugar-coated lies. "
        f"\n\nCreated by Arewa Michael"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id
    
    logger.info(f"Received message from user {user_id}: {user_message}")
    
    # Fetch responses from Google Doc (with caching)
    responses = await fetch_responses()
    
    # Get the best response
    response = await find_best_response(user_message, responses)
    
    # Send the response
    await update.message.reply_text(response)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and hasattr(update, 'message'):
        await update.message.reply_text(
            "Abeg, something scatter! Try again small time. "
            "Na life just show us pepper."
        )

def main():
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Start the bot
    if RENDER:
        # Production with webhook
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
        logger.info("Bot running in production mode with webhook")
    else:
        # Development with polling
        application.run_polling()
        logger.info("Bot running in development mode with polling")

if __name__ == '__main__':
    main()