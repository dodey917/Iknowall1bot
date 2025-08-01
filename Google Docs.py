class GoogleDocQA:
    def __init__(self):
        self.service = None
        self.qa_pairs = []
        self.last_refresh = 0
        
    def initialize_service(self):
        """Initialize the Google Docs API service"""
        credentials = service_account.Credentials.from_service_account_info(GOOGLE_CREDENTIALS)
        self.service = build('docs', 'v1', credentials=credentials)
        
    def refresh_qa_pairs(self):
        """Fetch and parse Q&A pairs from Google Doc"""
        try:
            if not self.service:
                self.initialize_service()
                
            # Fetch document content
            doc = self.service.documents().get(documentId=GOOGLE_DOC_ID).execute()
            content = doc.get('body', {}).get('content', [])
            
            # Extract all text
            full_text = ""
            for element in content:
                if 'paragraph' in element:
                    for para_elem in element['paragraph']['elements']:
                        if 'textRun' in para_elem:
                            full_text += para_elem['textRun']['content']
            
            # Parse Q&A pairs
            self.qa_pairs = []
            current_q = None
            current_a = None
            
            for line in full_text.split('\n'):
                line = line.strip()
                if line.startswith('Q:'):
                    if current_q and current_a:  # Save previous pair
                        self.qa_pairs.append((current_q.lower(), current_a))
                    current_q = line[2:].strip()  # Remove 'Q:' prefix
                    current_a = None
                elif line.startswith('A:'):
                    current_a = line[2:].strip()  # Remove 'A:' prefix
            
            # Add the last pair if exists
            if current_q and current_a:
                self.qa_pairs.append((current_q.lower(), current_a))
                
            logger.info(f"Refreshed Q&A pairs. Found {len(self.qa_pairs)} questions.")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing Q&A from Google Doc: {e}")
            return False
    
    def get_answer(self, question):
        """Find the best answer for a question"""
        if not self.qa_pairs:
            if not self.refresh_qa_pairs():
                return "⚠️ Sorry, I can't access my knowledge base right now."
        
        question_lower = question.lower().strip()
        
        # 1. Try exact match first
        for q, a in self.qa_pairs:
            if question_lower == q:
                return a
        
        # 2. Try question contains user's query or vice versa
        for q, a in self.qa_pairs:
            if question_lower in q or q in question_lower:
                return a
        
        # 3. Try word similarity
        question_words = set(question_lower.split())
        best_match = None
        best_score = 0
        
        for q, a in self.qa_pairs:
            q_words = set(q.split())
            common_words = question_words & q_words
            score = len(common_words)
            
            # Prioritize matches with more question words matched
            if score > best_score and score >= len(question_words)/2:
                best_score = score
                best_match = a
        
        return best_match if best_match else "🤔 I don't have an answer for that. Try rephrasing your question."
