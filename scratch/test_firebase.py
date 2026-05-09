import firebase_admin
from firebase_admin import credentials, firestore
import os

SERVICE_ACCOUNT_PATH = 'serviceAccountKey.json'

if os.path.exists(SERVICE_ACCOUNT_PATH):
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        # Try to read something or just check if client is initialized
        print("SUCCESS: Connected to Firebase Firestore.")
        # Try a simple write/read to be absolutely sure
        test_ref = db.collection('test_connection').document('status')
        test_ref.set({'connected': True, 'timestamp': firestore.SERVER_TIMESTAMP})
        print("SUCCESS: Data write verified.")
    except Exception as e:
        print(f"ERROR: Failed to connect to Firebase: {e}")
else:
    print("ERROR: serviceAccountKey.json not found.")
