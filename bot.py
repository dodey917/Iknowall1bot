import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
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

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)  # Check for updates every 5 minutes

    def initialize_service(self):
        """Initialize the Google Docs API service"""
        credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
        self.service = build('docs', 'v1', credentials=credentials)
        
    def get_content_hash(self, content):
        """Generate a hash of the document content to detect changes"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def refresh_qa_pairs(self, force=False):
        """Refresh Q&A pairs if document changed or forced"""
        try:
            if not self.service:
                self.initialize_service()
                
            # Skip refresh if not needed
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True
                
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            content = ""
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content += para_elem['textRun']['content']
            
            # Check if content changed
            new_hash = self.get_content_hash(content)
            if not force and self.content_hash == new_hash:
                self.last_refresh = datetime.now()
                return True  # No changes detected
            
            # Parse Q&A pairs
            new_pairs = []
            current_q = current_a = None
            
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Q:'):
                    if current_q and current_a:
                        new_pairs.append((current_q.lower(), current_a))
                    current_q = line[2:].strip()
                    current_a = None
                elif line.startswith('A:'):
                    current_a = line[2:].strip()
            
            if current_q and current_a:
                new_pairs.append((current_q.lower(), current_a))
            
            # Update only if parsing succeeded
            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Refreshed Q&A pairs. Found {len(self.qa_pairs)} questions.")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing Q&A: {e}")
            return False

    def get_answer(self, question):
        """Get answer with automatic refresh check"""
        # First try with current data
        answer = self._get_cached_answer(question)
        if answer:
            return answer
        
        # If no answer found, refresh and try again
        if self.refresh_qa_pairs():
            return self._get_cached_answer(question)
        return "⚠️ Couldn't refresh knowledge base. Please try again later."

    def _get_cached_answer(self, question):
        """Internal method to get answer from cached data"""
        question_lower = question.lower().strip()
        
        # 1. Try exact match first
        for q, a in self.qa_pairs:
            if question_lower == q:
                return a
        
        # 2. Try question contains user's query or vice versa
        for q, a in self.qa_pairs:
            if question_lower in q or q in question_lower:
                return a
        
        # 3. Try word similarity
        question_words = set(question_lower.split())
        best_match = None
        best_score = 0
        
        for q, a in self.qa_pairs:
            q_words = set(q.split())
            common_words = question_words & q_words
            score = len(common_words)
            
            if score > best_score and score >= len(question_words)/2:
                best_score = score
                best_match = a
        
        return best_match if best_match else None

# Initialize the Q&A system
qa_system = GoogleDocQA()

# Telegram Bot Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Q&A bot. Ask me anything from my knowledge base!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 E be like say you don jam correct plug. Run your matter now\n\n"
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
    if user.id not in [7697559889, 6089861817]:  # Replace with your admin user IDs
        await update.message.reply_text("🚫 This command is for admins only")
        return
    
    if qa_system.refresh_qa_pairs(force=True):
        await update.message.reply_text("✅ Knowledge base refreshed successfully!")
    else:
        await update.message.reply_text("⚠️ Failed to refresh knowledge base")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ['group', 'supergroup']:
        if not update.message.text.startswith('@your_bot_username'):
            return
    
    answer = qa_system.get_answer(update.message.text)
    if not answer:
        answer = "🤔 I don't have an answer for that. Try rephrasing your question."
    await update.message.reply_text(answer)

def main():
    try:
        logger.info("Starting bot...")
        
        # Initialize and test Google Docs connection
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
