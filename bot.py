from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hello! I fetch content from Google Docs.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # This will be where you integrate Google Docs
    doc_content = await fetch_from_google_docs()  # Note the async/await
    await update.message.reply_text(doc_content)

def main() -> None:
    application = ApplicationBuilder().token("YOUR_TELEGRAM_TOKEN").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()
