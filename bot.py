import os
import json
import re
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GoogleDocsClient:
    def __init__(self):
        try:
            # Try to load from environment variable first
            service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            if service_account_json:
                self.creds = service_account.Credentials.from_service_account_info(
                    json.loads(service_account_json),
                    scopes=['https://www.googleapis.com/auth/documents.readonly']
                )
            else:
                # Fall back to service account file if environment variable not set
                self.creds = service_account.Credentials.from_service_account_file(
                    'service_account.json',
                    scopes=['https://www.googleapis.com/auth/documents.readonly']
                )
            
            self.service = build('docs', 'v1', credentials=self.creds)
            logger.info("Google Docs client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Docs client: {e}")
            raise

    def find_answer(self, question):
        try:
            doc = self.service.documents().get(documentId=os.getenv('GOOGLE_DOC_ID')).execute()
            content = self._extract_text(doc)
            
            # Find Q&A pairs
            qa_pairs = re.findall(r'Q:\s*(.*?)\s*A:\s*(.*?)(?=\nQ:|$)', content, re.DOTALL)
            
            # Find best matching question
            question_lower = question.lower()
            for q, a in qa_pairs:
                if question_lower in q.lower() or q.lower() in question_lower:
                    return a.strip()
            return "I'm not sure about that. Could you ask differently?"
        except Exception as e:
            logger.error(f"Error finding answer: {e}")
            return "Sorry, I'm having trouble accessing the information."

    def _extract_text(self, doc):
        text = []
        for elem in doc.get('body', {}).get('content', []):
            if 'paragraph' in elem:
                for para_elem in elem['paragraph']['elements']:
                    if 'textRun' in para_elem:
                        text.append(para_elem['textRun']['content'])
        return ''.join(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        answer = docs_client.find_answer(update.message.text)
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("Sorry, I encountered an error processing your request.")

def main():
    # Verify required environment variables
    required_vars = ['BOT_TOKEN', 'GOOGLE_DOC_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return

    try:
        global docs_client
        docs_client = GoogleDocsClient()
        
        app = ApplicationBuilder().token(os.getenv('BOT_TOKEN')).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Starting bot in polling mode (Background Worker)...")
        app.run_polling()
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")

if __name__ == '__main__':
    main()
