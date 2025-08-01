import os
import json
import re
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Initialize Google Docs client
class GoogleDocsClient:
    def __init__(self):
        # Get service account info from environment variable
        service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            raise ValueError("Google service account credentials not found in environment variables")
            
        self.creds = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=['https://www.googleapis.com/auth/documents.readonly']
        )
        self.service = build('docs', 'v1', credentials=self.creds)
    
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
            print(f"Error finding answer: {e}")
            return "Sorry, I'm having trouble accessing the information right now."

    def _extract_text(self, doc):
        text = []
        for elem in doc.get('body', {}).get('content', []):
            if 'paragraph' in elem:
                for para_elem in elem['paragraph']['elements']:
                    if 'textRun' in para_elem:
                        text.append(para_elem['textRun']['content'])
        return ''.join(text)

# Initialize client
docs_client = GoogleDocsClient()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await asyncio.sleep(1)  # Simulate typing delay
    
    answer = docs_client.find_answer(user_question)
    await update.message.reply_text(answer)

def main():
    # Verify required environment variables
    required_vars = ['BOT_TOKEN', 'GOOGLE_DOC_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your Render.com environment settings")
        return

    try:
        app = ApplicationBuilder().token(os.getenv('BOT_TOKEN')).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("Bot is starting...")
        app.run_polling()
    except Exception as e:
        print(f"Bot failed to start: {e}")

if __name__ == '__main__':
    main()
