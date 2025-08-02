import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
import time
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
ADMIN_IDS = [7697559889, 6089861817]

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.response_cache = {}
        self.cache_expiry = timedelta(hours=24)
        self.initialize_service()

    def initialize_service(self):
        """Initialize Google Docs API service"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
                )
                self.service = build('docs', 'v1', credentials=credentials)
                logger.info("Google Docs service don setup!")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"E don burst! No fit connect to Google Docs after {max_retries} tries: {e}")
                    raise
                logger.warning(f"De try again to connect (try {attempt + 1})...")
                time.sleep(2 ** attempt)

    def _clean_cache(self):
        """Remove expired cache entries"""
        now = datetime.now()
        expired_keys = [k for k, v in self.response_cache.items() if now - v['timestamp'] > self.cache_expiry]
        for key in expired_keys:
            del self.response_cache[key]

    def get_content_hash(self, content):
        """Generate hash for document content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def parse_qa_pairs(self, content):
        """Parse Q&A pairs"""
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
        """Refresh Q&A pairs"""
        try:
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True

            logger.info("De refresh the Q&A pairs from Google Doc...")
            doc = self.service.documents().get(documentId=os.getenv('GOOGLE_DOC_ID')).execute()
            
            content = []
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content.append(para_elem['textRun']['content'])
            full_content = '\n'.join(content)

            new_hash = self.get_content_hash(full_content)
            if not force and self.content_hash == new_hash:
                logger.debug("No new tin for Google Doc")
                self.last_refresh = datetime.now()
                return True

            new_pairs = self.parse_qa_pairs(full_content)
            if not new_pairs:
                logger.warning("No Q&A pairs inside this doc o!")
                return False

            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Don refresh {len(self.qa_pairs)} Q&A pairs")
            return True

        except Exception as e:
            logger.error(f"Error don happen for refresh Q&A pairs: {str(e)}", exc_info=True)
            return False

    def get_answer(self, question, similarity_threshold=0.6):
        """Get answer with Naija flavor"""
        try:
            self._clean_cache()
            
            question_lower = question.lower().strip()
            if not question_lower:
                return "Abeg ask question jare!"

            # Check cache first - ensures single response per question
            cache_key = hash(question_lower)
            if cache_key in self.response_cache:
                return self.response_cache[cache_key]['response']

            # Find best match
            answer = self._find_best_match(question_lower, similarity_threshold)
            if not answer and self.refresh_qa_pairs():
                answer = self._find_best_match(question_lower, similarity_threshold)

            # Add Naija flavor to responses
            if not answer:
                answer = "I no sabi answer to that question. Try ask am another way."
            else:
                answer = self._naija_flavor(answer)

            # Cache the response for 24 hours
            self.response_cache[cache_key] = {
                'response': answer,
                'timestamp': datetime.now()
            }

            return answer

        except Exception as e:
            logger.error(f"Wahala don happen: {str(e)}", exc_info=True)
            return "E don be! My brain no dey work now. Try again small time."

    def _find_best_match(self, question_lower, similarity_threshold):
        """Find best matching answer"""
        best_match = None
        highest_score = 0

        for q, a in self.qa_pairs:
            # Exact match
            if question_lower == q:
                return a

            # Similarity score
            similarity = SequenceMatcher(None, question_lower, q).ratio()
            if similarity > highest_score and similarity >= similarity_threshold:
                highest_score = similarity
                best_match = a

        return best_match if highest_score >= similarity_threshold else None

    def _naija_flavor(self, text):
        """Add Naija pidgin flavor to responses"""
        phrases = {
            "hello": "How you dey!",
            "hi": "Wetin dey happen!",
            "thank you": "No wahala!",
            "thanks": "I dey appreciate!",
            "sorry": "No vex!",
            "please": "Abeg!",
            "help": "I go help you!",
            "what's up": "How body!",
            "how are you": "How you dey feel today?"
        }
        
        # Convert specific phrases
        for eng, naija in phrases.items():
            if eng.lower() in text.lower():
                return naija
        
        # Add general Naija flavor
        if "?" in text:
            return text.replace("?", " abi?")
        
        return f"{text}... no be so?"

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
import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
import time
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
ADMIN_IDS = [7697559889, 6089861817]

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.response_cache = {}
        self.cache_expiry = timedelta(hours=24)
        self.initialize_service()

    def initialize_service(self):
        """Initialize Google Docs API service"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
                )
                self.service = build('docs', 'v1', credentials=credentials)
                logger.info("Google Docs service don setup!")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"E don burst! No fit connect to Google Docs after {max_retries} tries: {e}")
                    raise
                logger.warning(f"De try again to connect (try {attempt + 1})...")
                time.sleep(2 ** attempt)

    def _clean_cache(self):
        """Remove expired cache entries"""
        now = datetime.now()
        expired_keys = [k for k, v in self.response_cache.items() if now - v['timestamp'] > self.cache_expiry]
        for key in expired_keys:
            del self.response_cache[key]

    def get_content_hash(self, content):
        """Generate hash for document content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def parse_qa_pairs(self, content):
        """Parse Q&A pairs"""
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
        """Refresh Q&A pairs"""
        try:
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True

            logger.info("De refresh the Q&A pairs from Google Doc...")
            doc = self.service.documents().get(documentId=os.getenv('GOOGLE_DOC_ID')).execute()
            
            content = []
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content.append(para_elem['textRun']['content'])
            full_content = '\n'.join(content)

            new_hash = self.get_content_hash(full_content)
            if not force and self.content_hash == new_hash:
                logger.debug("No new tin for Google Doc")
                self.last_refresh = datetime.now()
                return True

            new_pairs = self.parse_qa_pairs(full_content)
            if not new_pairs:
                logger.warning("No Q&A pairs inside this doc o!")
                return False

            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Don refresh {len(self.qa_pairs)} Q&A pairs")
            return True

        except Exception as e:
            logger.error(f"Error don happen for refresh Q&A pairs: {str(e)}", exc_info=True)
            return False

    def get_answer(self, question, similarity_threshold=0.6):
        """Get answer with Naija flavor"""
        try:
            self._clean_cache()
            
            question_lower = question.lower().strip()
            if not question_lower:
                return "Abeg ask question jare!"

            # Check cache first - ensures single response per question
            cache_key = hash(question_lower)
            if cache_key in self.response_cache:
                return self.response_cache[cache_key]['response']

            # Find best match
            answer = self._find_best_match(question_lower, similarity_threshold)
            if not answer and self.refresh_qa_pairs():
                answer = self._find_best_match(question_lower, similarity_threshold)

            # Add Naija flavor to responses
            if not answer:
                answer = "I no sabi answer to that question. Try ask am another way."
            else:
                answer = self._naija_flavor(answer)

            # Cache the response for 24 hours
            self.response_cache[cache_key] = {
                'response': answer,
                'timestamp': datetime.now()
            }

            return answer

        except Exception as e:
            logger.error(f"Wahala don happen: {str(e)}", exc_info=True)
            return "E don be! My brain no dey work now. Try again small time."

    def _find_best_match(self, question_lower, similarity_threshold):
        """Find best matching answer"""
        best_match = None
        highest_score = 0

        for q, a in self.qa_pairs:
            # Exact match
            if question_lower == q:
                return a

            # Similarity score
            similarity = SequenceMatcher(None, question_lower, q).ratio()
            if similarity > highest_score and similarity >= similarity_threshold:
                highest_score = similarity
                best_match = a

        return best_match if highest_score >= similarity_threshold else None

    def _naija_flavor(self, text):
        """Add Naija pidgin flavor to responses"""
        phrases = {
            "hello": "How you dey!",
            "hi": "Wetin dey happen!",
            "thank you": "No wahala!",
            "thanks": "I dey appreciate!",
            "sorry": "No vex!",
            "please": "Abeg!",
            "help": "I go help you!",
            "what's up": "How body!",
            "how are you": "How you dey feel today?"
        }
        
        # Convert specific phrases
        for eng, naija in phrases.items():
            if eng.lower() in text.lower():
                return naija
        
        # Add general Naija flavor
        if "?" in text:
            return text.replace("?", " abi?")
        
        return f"{text}... no be so?"

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
