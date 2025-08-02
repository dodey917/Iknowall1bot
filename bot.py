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

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.response_cache = {}
        self.cache_expiry = timedelta(hours=1)
        self.initialize_service()

    def initialize_service(self):
        """Initialize Google Docs API service"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
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

            # Check cache first
            cache_key = hash(question_lower)
            if cache_key in self.response_cache:
                cached = self.response_cache[cache_key]
                if datetime.now() - cached['timestamp'] <= self.cache_expiry:
                    logger.debug(f"Don see this question before: {question_lower[:50]}...")
                    return cached['response']

            # Find best match
            answer = self._find_best_match(question_lower, similarity_threshold)
            if not answer and self.refresh_qa_pairs():
                answer = self._find_best_match(question_lower, similarity_threshold)

            # Add Naija flavor to responses
            if not answer:
                answer = "I no sabi answer to that question. Try ask am another way."
            else:
                answer = self._naija_flavor(answer)

            # Cache the response
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
    if user.id not in [12345678, 87654321]:  # Replace with admin IDs
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
    main()        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.response_cache = {}
        self.cache_expiry = timedelta(hours=1)
        self.initialize_service()

    def initialize_service(self):
        """Initialize Google Docs API service"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
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

            # Check cache first
            cache_key = hash(question_lower)
            if cache_key in self.response_cache:
                cached = self.response_cache[cache_key]
                if datetime.now() - cached['timestamp'] <= self.cache_expiry:
                    logger.debug(f"Don see this question before: {question_lower[:50]}...")
                    return cached['response']

            # Find best match
            answer = self._find_best_match(question_lower, similarity_threshold)
            if not answer and self.refresh_qa_pairs():
                answer = self._find_best_match(question_lower, similarity_threshold)

            # Add Naija flavor to responses
            if not answer:
                answer = self._naija_flavor("I no sabi answer to that question. Try ask am another way.")
            else:
                answer = self._naija_flavor(answer)

            # Cache the response
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
    if user.id not in [7697559889, 6089861817]:  # Replace with admin IDs
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
    def initialize_service(self):
        credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
        self.service = build('docs', 'v1', credentials=credentials)
        
    def get_content_hash(self, content):
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def refresh_qa_pairs(self, force=False):
        try:
            if not self.service:
                self.initialize_service()
                
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True
                
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            content = ""
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content += para_elem['textRun']['content']
            
            new_hash = self.get_content_hash(content)
            if not force and self.content_hash == new_hash:
                self.last_refresh = datetime.now()
                return True
            
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
            
            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Refreshed Q&A pairs. Found {len(self.qa_pairs)} questions.")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing Q&A: {e}")
            return False

    def get_answer(self, question):
        answer = self._get_cached_answer(question)
        if answer:
            return answer
        
        if self.refresh_qa_pairs():
            return self._get_cached_answer(question)
        return "Abeg no vex, my brain no dey work well well now. Try again abeg."

    def _get_cached_answer(self, question):
        question_lower = question.lower().strip()
        
        for q, a in self.qa_pairs:
            if question_lower == q:
                return a
        
        for q, a in self.qa_pairs:
            if question_lower in q or q in question_lower:
                return a
        
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

# Telegram Bot Handlers with Naija Pidgin responses
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wetin you want? Make I help you abi you just dey disturb me?")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Abeg which kain help you want?\n\n"
        "Wetin I fit do:\n"
        "/start - Make I abuse you\n"
        "/help - See wetin I fit do\n"
        "/refresh - If you be ogbonge admin, make I refresh my brain\n\n"
        "Just yarn your matter make I see if I fit answer am!"
    )
    await update.message.reply_text(help_text)

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in [7697559889, 6089861817]:
        await update.message.reply_text("Ode! Who you be? You no be admin, comot for here!")
        return
    
    if qa_system.refresh_qa_pairs(force=True):
        await update.message.reply_text("Okay okay, I don refresh my brain small. Hope say e better now?")
    else:
        await update.message.reply_text("Chai! Something scatter. My brain no gree refresh. Try again abeg.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ['group', 'supergroup']:
        if not update.message.text.startswith('@your_bot_username'):
            return
    
    question = update.message.text
    if update.message.chat.type in ['group', 'supergroup']:
        question = question.replace('@your_bot_username', '').strip()
    
    last_question = context.chat_data.get('last_question')
    last_answer = context.chat_data.get('last_answer')
    
    if question == last_question and last_answer:
        return
    
    answer = qa_system.get_answer(question)
    
    if not answer:
        responses = [
            "Abeg comot for here! I no know wetin you dey talk.",
            "Na which kain question be this? I no get answer for your mumu question.",
            "You dey whine me abi? Ask better question!",
            "Chai! Your question too taya me. No fit answer am.",
            "Na only God know answer to this your question. Go ask Pastor."
        ]
        answer = responses[hash(question) % len(responses)]
    
    context.chat_data['last_question'] = question
    context.chat_data['last_answer'] = answer
    
    await update.message.reply_text(answer)

def main():
    try:
        logger.info("Starting bot...")
        
        if not qa_system.refresh_qa_pairs(force=True):
            logger.error("Failed to initialize Google Docs connection")
            return
        
        app = Application.builder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("refresh", refresh_command))
        
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
    def initialize_service(self):
        credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
        self.service = build('docs', 'v1', credentials=credentials)
        
    def get_content_hash(self, content):
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def refresh_qa_pairs(self, force=False):
        try:
            if not self.service:
                self.initialize_service()
                
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True
                
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            content = ""
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content += para_elem['textRun']['content']
            
            new_hash = self.get_content_hash(content)
            if not force and self.content_hash == new_hash:
                self.last_refresh = datetime.now()
                return True
            
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
            
            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Refreshed Q&A pairs. Found {len(self.qa_pairs)} questions.")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing Q&A: {e}")
            return False

    def get_answer(self, question):
        answer = self._get_cached_answer(question)
        if answer:
            return answer
        
        if self.refresh_qa_pairs():
            return self._get_cached_answer(question)
        return "Abeg no vex, my brain no dey work well well now. Try again later abeg."

    def _get_cached_answer(self, question):
        question_lower = question.lower().strip()
        
        for q, a in self.qa_pairs:
            if question_lower == q:
                return a
        
        for q, a in self.qa_pairs:
            if question_lower in q or q in question_lower:
                return a
        
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

# Telegram Bot Handlers with Naija Pidgin responses
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wetin you want? Make I help you abi you just dey disturb me?")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Abeg which kain help you want?\n\n"
        "Wetin I fit do:\n"
        "/start - Make I abuse you\n"
        "/help - See wetin I fit do\n"
        "/refresh - If you be ogbonge admin, make I refresh my brain\n\n"
        "Just yarn your matter make I see if I fit answer am!"
    )
    await update.message.reply_text(help_text)

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in [7697559889, 6089861817]:
        await update.message.reply_text("Ode! Who you be? You no be admin, comot for here!")
        return
    
    if qa_system.refresh_qa_pairs(force=True):
        await update.message.reply_text("Okay okay, I don refresh my brain small. Hope say e better now?")
    else:
        await update.message.reply_text("Chai! Something scatter. My brain no gree refresh. Try again abeg.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ['group', 'supergroup']:
        if not update.message.text.startswith('@your_bot_username'):
            return
    
    question = update.message.text
    if update.message.chat.type in ['group', 'supergroup']:
        question = question.replace('@your_bot_username', '').strip()
    
    last_question = context.chat_data.get('last_question')
    last_answer = context.chat_data.get('last_answer')
    
    if question == last_question and last_answer:
        return
    
    answer = qa_system.get_answer(question)
    
    if not answer:
        responses = [
            "Abeg comot for here! I no know wetin you dey talk.",
            "Na which kain question be this? I no get answer for your mumu question.",
            "You dey whine me abi? Ask better question!",
            "Chai! Your question too taya me. No fit answer am.",
            "Na only God know answer to this your question. Go ask Pastor."
        ]
        answer = responses[hash(question) % len(responses)]
    
    context.chat_data['last_question'] = question
    context.chat_data['last_answer'] = answer
    
    await update.message.reply_text(answer)

def main():
    try:
        logger.info("Starting bot...")
        
        if not qa_system.refresh_qa_pairs(force=True):
            logger.error("Failed to initialize Google Docs connection")
            return
        
        app = Application.builder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("refresh", refresh_command))
        
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
                    current_a = line[1:].strip()
            
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
    await update.message.reply_text("Hello! I be I Know All 📚 E be like say you don jam correct plug. Run your matter now!")

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
 Ask
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
