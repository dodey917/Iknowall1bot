# I Know All Telegram Bot

A Telegram bot that fetches responses from a Google Doc and responds in Nigerian slang with a negative/factual tone.

## Features

- Fetches Q&A pairs from a Google Doc
- Responds in Nigerian Pidgin English
- Caches responses for performance
- Automatically refreshes cache periodically
- Deployable to Render.com

## Setup

1. Clone this repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Unix/MacOS: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file with your credentials (use the template)
6. Run the bot: `python app.py`

## Deployment to Render.com

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set the following environment variables:
   - `BOT_TOKEN`
   - `GOOGLE_CREDENTIALS_JSON`
   - `GOOGLE_DOC_ID`
   - `PORT` (10000)
   - `RENDER` (true)
   - `WEBHOOK_URL` (your Render URL)
4. Set the build command: `pip install -r requirements.txt`
5. Set the start command: `python app.py`

## Google Docs Format

The Google Doc should contain Q&A pairs in this format:
Q: hello
A: Wetin you want? Life no balance!

Q: how are you
A: How I go be? Na so so suffer dey worry person.
```

Created by Arewa Michael