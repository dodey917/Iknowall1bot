import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Initialize Google Docs client
class GoogleDocsClient:
    def __init__(self):
        self.creds = service_account.Credentials.from_service_account_info(
            json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')),
            scopes=['https://www.googleapis.com/auth/documents.readonly']
        )
        self.service = build('docs', 'v1', credentials=self.creds)
    
    def find_answer(self, question):
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
    answer = docs_client.find_answer(user_question)
    
    # Typing indicator and slight delay
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await asyncio.sleep(1)  # Simulate typing delay
    
    await update.message.reply_text(answer)

def main():
    app = ApplicationBuilder().token(os.getenv('BOT_TOKEN')).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    import asyncio, json
    main()
