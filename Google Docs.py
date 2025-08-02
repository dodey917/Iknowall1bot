import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.initialize_service()

    def initialize_service(self):
        """Initialize Google Docs API service with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
                )
                self.service = build('docs', 'v1', credentials=credentials)
                logger.info("Google Docs service initialized successfully")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to initialize Google Docs service after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Retry {attempt + 1} for Google Docs initialization...")
                time.sleep(2 ** attempt)

    def get_content_hash(self, content):
        """Generate SHA-256 hash of document content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def parse_qa_pairs(self, content):
        """Robust Q&A pair parsing from document content"""
        qa_pairs = []
        current_q = current_a = None
        buffer = []

        def flush_buffer():
            nonlocal current_q, current_a, buffer
            if buffer:
                text = ' '.join(buffer).strip()
                if current_q is None and text.lower().startswith('q:'):
                    current_q = text[2:].strip()
                elif current_q is not None and text.lower().startswith('a:'):
                    current_a = text[2:].strip()
                buffer = []

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                flush_buffer()
                continue

            if line.lower().startswith(('q:', 'a:')) and buffer:
                flush_buffer()

            buffer.append(line)

        flush_buffer()

        if current_q and current_a:
            qa_pairs.append((current_q.lower(), current_a))

        return qa_pairs

    def refresh_qa_pairs(self, force=False):
        """Refresh Q&A pairs from Google Docs with change detection"""
        try:
            # Skip if not forced and within refresh interval
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True

            logger.info("Refreshing Q&A pairs from Google Doc...")
            doc = self.service.documents().get(documentId=os.getenv('GOOGLE_DOC_ID')).execute()
            
            # Extract document content efficiently
            content = []
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content.append(para_elem['textRun']['content'])
            full_content = '\n'.join(content)

            # Check for content changes
            new_hash = self.get_content_hash(full_content)
            if not force and self.content_hash == new_hash:
                logger.debug("No changes detected in Google Doc")
                self.last_refresh = datetime.now()
                return True

            # Parse and update Q&A pairs
            new_pairs = self.parse_qa_pairs(full_content)
            if not new_pairs:
                logger.warning("No Q&A pairs found in document")
                return False

            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Successfully refreshed {len(self.qa_pairs)} Q&A pairs")
            return True

        except HttpError as e:
            logger.error(f"Google Docs API error: {e.resp.status} {e.content.decode('utf-8')}")
            return False
        except Exception as e:
            logger.error(f"Error refreshing Q&A pairs: {str(e)}", exc_info=True)
            return False

    def get_answer(self, question, similarity_threshold=0.6):
        """Find best matching answer with similarity scoring"""
        if not question or not isinstance(question, str):
            return None

        question_lower = question.lower().strip()
        best_match = None
        highest_score = 0

        for q, a in self.qa_pairs:
            # Exact match
            if question_lower == q:
                return a

            # Similarity score
            similarity = SequenceMatcher(None, question_lower, q).ratio()
            if similarity > highest_score and similarity >= similarity_threshold:
                highest_score = similarity
                best_match = a

        return best_match if highest_score >= similarity_threshold else None
