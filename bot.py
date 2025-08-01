from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

def start(update: Update, context: CallbackContext):
    update.message.reply_text('Hello! I fetch content from Google Docs.')

def handle_message(update: Update, context: CallbackContext):
    # This will be where you integrate Google Docs
    doc_content = fetch_from_google_docs()  # You'll implement this
    update.message.reply_text(doc_content)

def main():
    updater = Updater("YOUR_TELEGRAM_TOKEN", use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
