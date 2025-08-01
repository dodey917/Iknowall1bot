from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
SERVICE_ACCOUNT_FILE = 'service-account.json'  # Your downloaded credentials

def fetch_from_google_docs(doc_id):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    
    service = build('docs', 'v1', credentials=creds)
    document = service.documents().get(documentId=doc_id).execute()
    
    # Extract text content
    content = []
    for elem in document.get('body', {}).get('content', []):
        if 'paragraph' in elem:
            for para_elem in elem['paragraph']['elements']:
                if 'textRun' in para_elem:
                    content.append(para_elem['textRun']['content'])
    
    return ''.join(content)
