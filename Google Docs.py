from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import json

def get_google_docs_service():
    """Initialize and return the Google Docs service with credentials from env var."""
    google_credentials = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
    credentials = service_account.Credentials.from_service_account_info(google_credentials)
    return build('docs', 'v1', credentials=credentials)

def fetch_qa_pairs_from_doc(doc_id):
    """
    Fetch Q&A pairs from Google Doc in the format:
    Q: question text
    A: answer text
    
    Returns a list of tuples (question, answer)
    """
    try:
        service = get_google_docs_service()
        doc = service.documents().get(documentId=doc_id).execute()
        content = doc.get('body', {}).get('content', [])
        
        # Extract all text from the document
        full_text = ""
        for element in content:
            if 'paragraph' in element:
                for para_elem in element['paragraph']['elements']:
                    if 'textRun' in para_elem:
                        full_text += para_elem['textRun']['content']
        
        # Parse Q&A pairs
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
        
        return qa_pairs
    
    except Exception as e:
        print(f"Error accessing Google Doc: {e}")
        return []

def get_answer_for_question(doc_id, question):
    """
    Find the best matching answer for a question from the Google Doc.
    Returns the answer text or None if no match found.
    """
    qa_pairs = fetch_qa_pairs_from_doc(doc_id)
    if not qa_pairs:
        return None
    
    best_match = None
    best_score = 0
    question_lower = question.lower()
    
    for q, a in qa_pairs:
        q_lower = q.lower()
        # Simple matching - improve this with more sophisticated NLP if needed
        if question_lower in q_lower or q_lower in question_lower:
            score = len(set(question_lower.split()) & set(q_lower.split()))
            if score > best_score:
                best_score = score
                best_match = a
    
    return best_match
