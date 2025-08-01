import os
import json
import re
import asyncio
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
            service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            if not service_account_json:
                raise ValueError("Missing service account credentials")
            
            self.creds = service_account.Credentials.from_service_account_info(
                json.loads(service_account_json),
                scopes=['https://www.googleapis.com/auth/documents.readonly']
            )
            self.service = build('docs', 'v1', credentials=self.creds)
        except Exception as e:
            logger.error(f"Google Docs init failed: {e}")
            raise

    def find_answer(self, question):
        try:
            doc = self.service.documents().get(documentId=os.getenv('GOOGLE_DOC_ID')).execute()
            content = self._extract_text(doc)
            qa_pairs = re.findall(r'Q:\s*(.*?)\s*A:\s*(.*?)(?=\nQ:|$)', content, re.DOTALL)
            
            question_lower = question.lower()
            for q, a in qa_pairs:
                if question_lower in q.lower() or q.lower() in question_lower:
                    return a.strip()
            return "I'm not sure about that. Could you ask differently?"
        except Exception as e:
            logger.error(f"Error finding answer: {e}")
            return "Sorry, I'm having trouble accessing the information right now."

    def _extract_text(self, doc):
        return ''.join(
            para_elem['textRun']['content']
            for elem in doc.get('body', {}).get('content', [])
            if 'paragraph' in elem
            for para_elem in elem['paragraph']['elements']
            if 'textRun' in para_elem
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await asyncio.sleep(1)
        answer = docs_client.find_answer(update.message.text)
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("Sorry, I encountered an error.")

def main():
    # Verify environment variables
    required_vars = ['BOT_TOKEN', 'GOOGLE_DOC_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON']
    if missing := [var for var in required_vars if not os.getenv(var)]:
        logger.error(f"Missing variables: {', '.join(missing)}")
        return

    try:
        global docs_client
        docs_client = GoogleDocsClient()
        
        app = ApplicationBuilder() \
            .token(os.getenv('BOT_TOKEN')) \
            .post_init(post_init) \
            .build()
            
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Webhook or polling based on environment
        if os.getenv('RENDER'):
            app.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv('PORT', 10000)),
                webhook_url=os.getenv('WEBHOOK_URL')
            )
        else:
            app.run_polling()
            
    except Exception as e:
        logger.error(f"Bot failed: {e}")

async def post_init(app):
    if os.getenv('RENDER'):
        await app.bot.set_webhook(os.getenv('WEBHOOK_URL'))

if __name__ == '__main__':
    main()
