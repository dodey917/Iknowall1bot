import os
import json
import logging
import hashlib
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
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
ADMIN_IDS = {7697559889, 6089861817}

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.initialize_service()
        self.answered_messages = set()  # Track answered messages
        self.message_ttl = timedelta(hours=1)  # How long to remember answered messages

    def initialize_service(self):
        """Initialize Google Docs API service with automatic retry"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
                self.service = build('docs', 'v1', credentials=credentials)
                logger.info("Google Docs service initialized successfully")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to initialize Google Docs service after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Retrying Google Docs initialization (attempt {attempt + 1})...")
                time.sleep(2 ** attempt)

    def get_content_hash(self, content):
        """Generate stable hash of document content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def parse_qa_pairs(self, content):
        """Parse Q&A pairs with improved line handling"""
        qa_pairs = []
        current_q = current_a = None
        buffer = []

        def flush_buffer():
            nonlocal current_q, current_a, buffer
            if buffer:
                text = ' '.join(buffer).strip()
                if current_q is None and text.startswith('Q:'):
                    current_q = text[2:].strip()
                elif current_q is not None and text.startswith('A:'):
                    current_a = text[2:].strip()
                buffer = []

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                flush_buffer()
                continue

            if line.startswith(('Q:', 'A:')) and buffer:
                flush_buffer()

            buffer.append(line)

        flush_buffer()

        if current_q and current_a:
            qa_pairs.append((current_q.lower(), current_a))

        return qa_pairs

    def refresh_qa_pairs(self, force=False):
        """Refresh Q&A pairs with enhanced error handling"""
        try:
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True

            logger.info("Refreshing Q&A pairs from Google Doc...")
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            
            content = []
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content.append(para_elem['textRun']['content'])
            full_content = '\n'.join(content)

            new_hash = self.get_content_hash(full_content)
            if not force and self.content_hash == new_hash:
                logger.debug("No changes detected in Google Doc")
                self.last_refresh = datetime.now()
                return True

            new_pairs = self.parse_qa_pairs(full_content)
            if not new_pairs:
                logger.warning("No Q&A pairs found in document")
                return False

            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Successfully refreshed {len(self.qa_pairs)} Q&A pairs")
            return True

        except Exception as e:
            logger.error(f"Error refreshing Q&A pairs: {str(e)}", exc_info=True)
            return False

    def get_answer(self, question, similarity_threshold=0.6):
        """Get answer with intelligent matching"""
        try:
            question_lower = question.lower().strip()
            if not question_lower:
                return "Please ask a question."

            answer = self._find_best_match(question_lower, similarity_threshold)
            if answer:
                return answer

            if self.refresh_qa_pairs():
                answer = self._find_best_match(question_lower, similarity_threshold)
                if answer:
                    return answer

            return "I couldn't find an answer to that question. Try rephrasing or ask about something else."

        except Exception as e:
            logger.error(f"Error finding answer: {str(e)}", exc_info=True)
            return "I'm having trouble accessing my knowledge base right now. Please try again later."

    def _find_best_match(self, question_lower, similarity_threshold):
        """Find best matching answer with similarity scoring"""
        best_match = None
        highest_score = 0

        for q, a in self.qa_pairs:
            if question_lower == q:
                return a

            similarity = SequenceMatcher(None, question_lower, q).ratio()
            if similarity > highest_score and similarity >= similarity_threshold:
                highest_score = similarity
                best_match = a

        return best_match if highest_score >= similarity_threshold else None

    def clean_answered_messages(self):
        """Clean up old message records"""
        now = datetime.now()
        self.answered_messages = {
            msg_id: timestamp 
            for msg_id, timestamp in self.answered_messages.items()
            if now - timestamp < self.message_ttl
        }

# Initialize the Q&A system
qa_system = GoogleDocQA()

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Q&A bot. Ask me anything from my knowledge base!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 I'm a Q&A bot powered by Google Docs!\n\n"
        "Available commands:\n"
        "/start - Welcome message\n"
        "/help - This help message\n"
        "/refresh - Admin: Force refresh knowledge base\n\n"
        "Just ask me any question and I'll try to answer it!"
    )
    await update.message.reply_text(help_text)

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to force refresh the knowledge base"""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 This command is for admins only")
        return
    
    if qa_system.refresh_qa_pairs(force=True):
        await update.message.reply_text("✅ Knowledge base refreshed successfully!")
    else:
        await update.message.reply_text("⚠️ Failed to refresh knowledge base")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Clean up old message records periodically
    if len(qa_system.answered_messages) > 100:
        qa_system.clean_answered_messages()

    # Check if we've already answered this message
    message_id = update.message.message_id
    if message_id in qa_system.answered_messages:
        return
    
    # Handle group mentions
    if update.message.chat.type in ['group', 'supergroup']:
        if not (update.message.text and update.message.text.startswith('@' + context.bot.username)):
            return
    
    answer = qa_system.get_answer(update.message.text)
    if not answer:
        answer = "🤔 I don't have an answer for that. Try rephrasing your question."
    
    await update.message.reply_text(answer)
    qa_system.answered_messages[message_id] = datetime.now()

def main():
    try:
        logger.info("Starting bot...")
        
        if not qa_system.refresh_qa_pairs(force=True):
            logger.error("Failed to initialize Google Docs connection")
            return
        
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Command handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("refresh", refresh_command))
        
        # Message handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Polling...")
        app.run_polling(
            poll_interval=3,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Conflict as e:
        logger.error("Another bot instance is already running. Exiting.")
    except Exception as e:
        logger.error(f"Bot crashed with error: {e}")
    finally:
        logger.info("Bot stopped")

if __name__ == "__main__":
    main()
