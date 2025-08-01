import os
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
        self.last_refresh = 0
        
    def initialize_service(self):
        credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
        self.service = build('docs', 'v1', credentials=credentials)
        
    def refresh_qa_pairs(self):
        try:
            if not self.service:
                self.initialize_service()
                
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            content = doc.get('body', {}).get('content', [])
            
            full_text = ""
            for element in content:
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            full_text += para_elem['textRun']['content']
            
            self.qa_pairs = []
            current_q = None
            current_a = None
            
            for line in full_text.split('\n'):
                line = line.strip()
                if line.startswith('Q:'):
                    if current_q and current_a:  # Save previous pair
                        self.qa_pairs.append((current_q.lower(), current_a))
                    current_q = line[2:].strip()  # Remove 'Q:'
                    current_a = None
                elif line.startswith('A:'):
                    current_a = line[2:].strip()  # Remove 'A:'
            
            # Add the last pair if exists
            if current_q and current_a:
                self.qa_pairs.append((current_q.lower(), current_a))
                
            logger.info(f"Refreshed Q&A pairs. Found {len(self.qa_pairs)} questions.")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing Q&A from Google Doc: {e}")
            return False
    
    def get_answer(self, question):
        if not self.qa_pairs:
            if not self.refresh_qa_pairs():
                return "Sorry, I can't access my knowledge base right now."
        
        question_lower = question.lower()
        
        # First try exact matches
        for q, a in self.qa_pairs:
            if question_lower == q:
                return a
        
        # Then try partial matches
        for q, a in self.qa_pairs:
            if question_lower in q or q in question_lower:
                return a
        
        # Finally try word overlap
        question_words = set(question_lower.split())
        best_match = None
        best_score = 0
        
        for q, a in self.qa_pairs:
            q_words = set(q.split())
            score = len(question_words & q_words)
            if score > best_score:
                best_score = score
                best_match = a
        
        if best_match:
            return best_match
            
        return "I don't know the answer to that question. Try asking something else!"

# Initialize the Q&A system
qa_system = GoogleDocQA()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your Q&A bot. Ask me anything from my knowledge base!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "I'm a Q&A bot powered by Google Docs!\n\n"
        "Available commands:\n"
        "/start - Welcome message\n"
        "/help - This help message\n\n"
        "Just ask me a question and I'll try to answer it from my knowledge base!"
    )
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ['group', 'supergroup']:
        if not update.message.text.startswith('@your_bot_username'):
            return
    
    answer = qa_system.get_answer(update.message.text)
    await update.message.reply_text(answer)

def main():
    try:
        logger.info("Starting bot...")
        
        # Initialize and test Google Docs connection
        if not qa_system.refresh_qa_pairs():
            logger.error("Failed to initialize Google Docs connection")
            return
        
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Command handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        
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
