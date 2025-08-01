import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID')

class GoogleDocsClient:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
        self.service_account_file = 'service_account.json'
        self.service = self._authenticate()
    
    def _authenticate(self):
        creds = service_account.Credentials.from_service_account_file(
            self.service_account_file, scopes=self.SCOPES)
        return build('docs', 'v1', credentials=creds)
    
    def get_document_content(self, document_id):
        try:
            document = self.service.documents().get(documentId=document_id).execute()
            content = []
            for elem in document.get('body', {}).get('content', []):
                if 'paragraph' in elem:
                    for para_elem in elem['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content.append(para_elem['textRun']['content'])
            return ''.join(content)
        except Exception as e:
            logger.error(f"Error fetching Google Doc: {e}")
            return "Sorry, I couldn't fetch the document content."

# Initialize Google Docs client
docs_client = GoogleDocsClient()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Welcome to the Google Docs Bot!\n\n"
        "Send me any message and I'll respond with content from my linked Google Doc."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    logger.info(f"User message: {user_message}")
    
    doc_content = docs_client.get_document_content(GOOGLE_DOC_ID)
    await update.message.reply_text(doc_content[:4000])  # Telegram has 4096 char limit

def main():
    # Validate environment variables
    if not TELEGRAM_TOKEN or not GOOGLE_DOC_ID:
        raise ValueError("Missing required environment variables")
    
    # Create and configure bot
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
