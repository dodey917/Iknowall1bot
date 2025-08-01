import os
import json
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

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress Google API cache warning
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

class GoogleDocsClient:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
        self.service = self._authenticate()
    
    def _authenticate(self):
        # Try both environment variable and file-based authentication
        try:
            # First try getting credentials from environment variable
            service_account_info = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            if service_account_info:
                creds = service_account.Credentials.from_service_account_info(
                    json.loads(service_account_info),
                    scopes=self.SCOPES
                )
                return build('docs', 'v1', credentials=creds)
            
            # Fall back to service account file if environment variable not set
            if os.path.exists('service_account.json'):
                creds = service_account.Credentials.from_service_account_file(
                    'service_account.json',
                    scopes=self.SCOPES
                )
                return build('docs', 'v1', credentials=creds)
            
            raise ValueError("No Google service account credentials found")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

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
            return "Sorry, I couldn't fetch the document content right now."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Welcome to the Google Docs Bot!\n\n"
        "Send me any message and I'll respond with content from my linked Google Doc."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc_content = docs_client.get_document_content(os.getenv('GOOGLE_DOC_ID'))
        await update.message.reply_text(doc_content[:4000])  # Telegram has 4096 char limit
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("Sorry, I encountered an error processing your request.")

def main():
    # Verify required environment variables
    required_vars = ['BOT_TOKEN', 'GOOGLE_DOC_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.info("Please set these in your Render.com environment settings")
        return

    try:
        global docs_client
        docs_client = GoogleDocsClient()
        
        application = ApplicationBuilder().token(os.getenv('BOT_TOKEN')).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Bot is starting...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")

if __name__ == '__main__':
    main()
