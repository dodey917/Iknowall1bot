import os
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID')
GOOGLE_CREDENTIALS = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))

# Initialize Google Docs service
credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
service = build('docs', 'v1', credentials=credentials)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm a bot that can answer your questions. Just ask me anything!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    I'm a Q&A bot powered by a Google Doc. Here's what you can do:
    
    - Ask me any question that might be in my knowledge base
    - Type /start to see my welcome message
    - Type /help to see this message
    
    My answers come directly from a curated Google Doc!
    """
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_type = update.message.chat.type
    text = update.message.text.strip()
    
    # Skip processing if message is from a group (unless the bot is mentioned)
    if message_type == 'group' or message_type == 'supergroup':
        if not text.startswith('@your_bot_username'):
            return
    
    # Get response from Google Doc
    response = get_response_from_doc(text)
    
    if response:
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("I'm not sure how to answer that. Try asking something else!")

def get_response_from_doc(question):
    try:
        # Get the document content
        doc = service.documents().get(documentId=GOOGLE_DOC_ID).execute()
        content = doc.get('body', {}).get('content', [])
        
        # Extract all text from the document
        full_text = ""
        for element in content:
            if 'paragraph' in element:
                for paragraph_element in element['paragraph']['elements']:
                    if 'textRun' in paragraph_element:
                        full_text += paragraph_element['textRun']['content']
        
        # Split into Q&A pairs
        qa_pairs = []
        current_q = None
        current_a = None
        
        for line in full_text.split('\n'):
            line = line.strip()
            if line.startswith('Q:'):
                if current_q and current_a:  # Save previous pair
                    qa_pairs.append((current_q, current_a))
                current_q = line[2:].strip()  # Remove 'Q:'
                current_a = None
            elif line.startswith('A:'):
                current_a = line[2:].strip()  # Remove 'A:'
        
        # Add the last pair if exists
        if current_q and current_a:
            qa_pairs.append((current_q, current_a))
        
        # Find the best matching question
        best_match = None
        best_score = 0
        question_lower = question.lower()
        
        for q, a in qa_pairs:
            q_lower = q.lower()
            # Simple matching - you could implement more sophisticated matching here
            if question_lower in q_lower or q_lower in question_lower:
                score = len(set(question_lower.split()) & set(q_lower.split()))
                if score > best_score:
                    best_score = score
                    best_match = a
        
        return best_match
    
    except Exception as e:
        print(f"Error accessing Google Doc: {e}")
        return None

if __name__ == '__main__':
    print('Starting bot...')
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    
    # Messages
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    
    # Errors would be handled here
    
    print('Polling...')
    app.run_polling(poll_interval=3)
