import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import hashlib

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8270027311:AAH5xcgSuyrfNEadhx7TM2TGYYQ3BWZpFDU')
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID', '14zSSmCznz4emYyq4BG5rO1oCS3Wqz8t8nt3omKb8ZQY')
ADMIN_IDS = [6089861817, 5584801763, 7697559889]  # Add your admin IDs here
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "telegrambotproject-467718",
    "private_key_id": "5b431873ee9223575ccc22b8b7713cda61251c8",
    "private_key": os.getenv('GOOGLE_PRIVATE_KEY', '''-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC9bPLe0Vy/ucZp
6jbSV12fLwayGoA6nGGUfKFcoMnx+yffFBmpQM+8cWzNnt/GADGEgXjNLtmBgO6H
7XLlr//20L5fFIUOrgul+iyyFNJaVcKBZXeEL2SzSTe8HOl8QwcvVSNKvB/j6PVI
T+NF/WTXb4Y2HcDF+vwJ/+ANw/sN9fRH9/yN8Dl7JdTvHhS1NF/PbiW9M7hYYAxQ
ZFBnJroA59xUn2h7zJgSugXxR9MucvJUD6KvvEwYtfxxjc4/Ps1A3dEMVkMeAMD/
btBWtF81arBEDB3kX8CQ9mafsNSwHKnFdIBHrZ2MYl76o9djK/q8GJoZP+0Sg3rb
um70Vj3LAgMBAAECggEAVsNKUyjONLsg2G6BAcMmjLz7ciSVS0NJpruXJVg4Z2/E
iXcpcc7P196UGXKFyKlaBPlQnZqx4ZFusC/girgco65lJCO/9kNd7n4ybrb+yoWx
e5dAMPmMRFpq/uy3PUVuSw3SBm84pCmV/7MnxG0V/V+Ft8/U9lnJi8L5mxSDL5cI
KdHz+uoZw3p5ywS7GpU4rDJaQ4hKCXGoZhYtyKb/VFEaRDVpXKYhAWYYoUOBeVTf
F45KK/PPYhttJilKvYrB87ftqlXsiBC8LdX3t4DTcG98BZVfqG6rpbsG5nC2bpms
wYhSOrbQYqR7gLpRx2m5fFuHIjOT6iQh+3no6GRmkQKBgQDtaHGwMKP/+rgwZl5y
8o+wSBkbkmpPvr3vI/uNBcyYJSAWToMU9cbX24UZ9mBILDRjxbW5OL17xFT6X/jJ
SD2RikJ5CwHjd5dkfDIif0b3sGEF0UOZ3LkK0D0ku/z3AaQ9/9Drl7Mp+FQSbFqD
R7ap16eZyFuwzSv7SCwcU6zq7QKBgQDMQo2iX2UfCJ8ypxZlm68C2rH+S/2sVWBC
qmrPowM/N+6+FNmjp3UZIoZiETaPJXaD8X0M8K0VxF1UikCq6rYe/HiSKlY1VUfG
cf3hj6Y2GK/6rDepdA8g91Ul1g+Ny4ic73gfgDp9L41MzSQSrlo9YQwMbajgyFW0
1HTjasTclwKBgQDS/EZFIgUt4iC9Cs0XdNAUBw8hPM70Tfy4QY82NhgsgpnwmRfP
kdmETpgMibPpkDeDD9s/X9it3L70wEP2hhgJdwk6T3j/MXI/IEzh8aEdUQf4xpBA
djORE52zPspCrpfLbcS7C1dzjjkRInCSSTJh4MEXX0N1bfGPYQWqqwZ6xQKBgD4R
v05nJKhgi1fuFE0+GNmKMWpwFx7mNsErXhfIlnUAfyj91wD3IwtHRYTJbEXlgXUo
zfI/tKkXqbDF7k7B0iPqXo00FkxQpOX1v8tqRnzL1bYb3TI+FVbUMei0ereA8PuX
fW49HgjqiUqcT+jpWHysX+fq7tWXqwuvP/HXgQjzAoGAW70TyML/govGwPiHyruW
itVBQFysnnmx2oju143gqPbbI9n2aMFiC0coY88L8+V6RCZSfK+9axiTtefhnBSr
cde22p+RE3ngXxRo5mkTpF8g4LY26RdpNQd3nLUzNtdcEdUW5phk2ok15Ndfwtk2
J4FY9B/6tiL60ATPH10xtAU=
-----END PRIVATE KEY-----'''),
    "client_email": "bot-access@telegrambotproject-467718.iam.gserviceaccount.com",
    "client_id": "100285639770680397909",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/bot-access%40telegrambotproject-467718.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GoogleDocService:
    def __init__(self):
        self.credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=['https://www.googleapis.com/auth/documents.readonly']
        )
        self.service = build('docs', 'v1', credentials=self.credentials)
        self.qa_pairs = {}
        self.last_doc_hash = ""

    def get_document_content(self):
        try:
            document = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            content = []
            for elem in document.get('body', {}).get('content', []):
                if 'paragraph' in elem:
                    for para_elem in elem.get('paragraph', {}).get('elements', []):
                        if 'textRun' in para_elem:
                            content.append(para_elem.get('textRun', {}).get('content', ''))
            return ''.join(content)
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            return None

    def parse_content(self, content):
        pairs = {}
        current_q = None
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Q:'):
                current_q = line[2:].strip().lower()
            elif line.startswith('A:') and current_q:
                pairs[current_q] = line[2:].strip()
                current_q = None
        return pairs

    def check_for_updates(self):
        content = self.get_document_content()
        if content is None:
            return False
        
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        if content_hash != self.last_doc_hash:
            self.last_doc_hash = content_hash
            new_pairs = self.parse_content(content)
            if new_pairs != self.qa_pairs:
                self.qa_pairs = new_pairs
                logger.info("QA pairs updated from Google Doc")
                return True
        return False

    def get_response(self, user_message):
        user_message = user_message.lower().strip()
        
        # Check for direct matches first
        if user_message in self.qa_pairs:
            return self.qa_pairs[user_message]
        
        # Try to find partial matches
        for question, answer in self.qa_pairs.items():
            if question in user_message or any(word in user_message for word in question.split()):
                return answer
        
        # If no match found, return default response
        if self.qa_pairs:
            responses = list(self.qa_pairs.values())
            return "Abeg, no waste my time. " + " ".join(responses[:2])[:200] + "..."
        return "Wetin you dey talk? No understand your grammar. Try ask am another way."

# Initialize Google Doc service
doc_service = GoogleDocService()
doc_service.check_for_updates()  # Initial load

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Abeg wetin you want? Na me be 'I Know All'.\n"
        f"Creator na Arewa Michael. Ask me anything, but no expect sweet talk."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Wetin you want?\n"
        "Just ask me anything, but no waste my time.\n"
        "I go answer you based on wetin dey Google Doc.\n"
        "No expect motivational talk - I dey talk raw truth."
    )
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check for doc updates on each message (simple alternative to job queue)
    if doc_service.check_for_updates():
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text="📝 Google Doc content has been updated. Bot responses refreshed."
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    response = doc_service.get_response(update.message.text)
    await update.message.reply_text(response)

def main():
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
