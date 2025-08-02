import hashlib
from datetime import datetime, timedelta
import time
from difflib import SequenceMatcher

class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = datetime.min
        self.content_hash = None
        self.refresh_interval = timedelta(minutes=5)
        self.response_cache = {}  # New cache to track responses
        self.cache_expiry = timedelta(hours=1)  # Cache duration
        self.initialize_service()

    def initialize_service(self):
        """Initialize Google Docs API service with automatic retry"""
        max_retries = 1
        for attempt in range(max_retries):
            try:
                credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
                self.service = build('docs', 'v1', credentials=credentials)
                logger.info("Google Docs service initialized successfully")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to initialize Google Docs service after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Retrying Google Docs initialization (attempt {attempt + 1})...")
                time.sleep(2 ** attempt)

    def _clean_cache(self):
        """Remove expired cache entries"""
        now = datetime.now()
        expired_keys = [k for k, v in self.response_cache.items() if now - v['timestamp'] > self.cache_expiry]
        for key in expired_keys:
            del self.response_cache[key]

    def get_content_hash(self, content):
        """Generate stable hash of document content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def parse_qa_pairs(self, content):
        """Parse Q&A pairs with improved line handling"""
        qa_pairs = []
        current_q = current_a = None
        buffer = []

        def flush_buffer():
            nonlocal current_q, current_a, buffer
            if buffer:
                text = ' '.join(buffer).strip()
                if current_q is None and text.startswith('Q:'):
                    current_q = text[2:].strip()
                elif current_q is not None and text.startswith('A:'):
                    current_a = text[2:].strip()
                buffer = []

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                flush_buffer()
                continue

            if line.startswith(('Q:', 'A:')) and buffer:
                flush_buffer()

            buffer.append(line)

        flush_buffer()

        if current_q and current_a:
            qa_pairs.append((current_q.lower(), current_a))

        return qa_pairs

    def refresh_qa_pairs(self, force=False):
        """Refresh Q&A pairs with enhanced error handling"""
        try:
            if not force and datetime.now() - self.last_refresh < self.refresh_interval:
                return True

            logger.info("Refreshing Q&A pairs from Google Doc...")
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            
            content = []
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            content.append(para_elem['textRun']['content'])
            full_content = '\n'.join(content)

            new_hash = self.get_content_hash(full_content)
            if not force and self.content_hash == new_hash:
                logger.debug("No changes detected in Google Doc")
                self.last_refresh = datetime.now()
                return True

            new_pairs = self.parse_qa_pairs(full_content)
            if not new_pairs:
                logger.warning("No Q&A pairs found in document")
                return False

            self.qa_pairs = new_pairs
            self.content_hash = new_hash
            self.last_refresh = datetime.now()
            logger.info(f"Successfully refreshed {len(self.qa_pairs)} Q&A pairs")
            return True

        except Exception as e:
            logger.error(f"Error refreshing Q&A pairs: {str(e)}", exc_info=True)
            return False

    def get_answer(self, question, similarity_threshold=0.6):
        """Get answer with intelligent matching and response caching"""
        try:
            self._clean_cache()  # Clean up old cache entries first
            
            question_lower = question.lower().strip()
            if not question_lower:
                return "Please ask a question."

            # Check cache first
            cache_key = hash(question_lower)
            if cache_key in self.response_cache:
                cached = self.response_cache[cache_key]
                if datetime.now() - cached['timestamp'] <= self.cache_expiry:
                    logger.debug(f"Returning cached response for: {question_lower[:50]}...")
                    return cached['response']

            # Find best match
            answer = self._find_best_match(question_lower, similarity_threshold)
            if not answer and self.refresh_qa_pairs():
                answer = self._find_best_match(question_lower, similarity_threshold)

            if not answer:
                answer = "I couldn't find an answer to that question. Try rephrasing or ask about something else."

            # Cache the response
            self.response_cache[cache_key] = {
                'response': answer,
                'timestamp': datetime.now()
            }

            return answer

        except Exception as e:
            logger.error(f"Error finding answer: {str(e)}", exc_info=True)
            return "I'm having trouble accessing my knowledge base right now. Please try again later."

    def _find_best_match(self, question_lower, similarity_threshold):
        """Find best matching answer with similarity scoring"""
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
