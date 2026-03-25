import os
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """
    Initialize Firebase with support for both local and Cloud Run environments.
    - Local: Uses firebase_key.json file
    - Cloud Run: Uses Application Default Credentials (ADC)
    """
    if firebase_admin._apps:
        return firebase_admin.get_app()

    # Check if running on Cloud Run or with explicit credentials path
    firebase_key_path = os.environ.get("FIREBASE_KEY_PATH", "../firebase_key.json")

    # Try to use service account file first (local development)
    if os.path.exists(firebase_key_path):
        print(f"✅ Firebase: Using service account file: {firebase_key_path}")
        cred = credentials.Certificate(firebase_key_path)
        return firebase_admin.initialize_app(cred)

    # Fall back to Application Default Credentials (Cloud Run)
    try:
        print("✅ Firebase: Using Application Default Credentials (Cloud Run)")
        cred = credentials.ApplicationDefault()
        project_id = os.environ.get("GOOGLE_PROJECT_ID", "faqsmartbuddy-490910")
        return firebase_admin.initialize_app(cred, {'projectId': project_id})
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        raise Exception(
            "Firebase credentials not found. "
            "Set FIREBASE_KEY_PATH for local dev or ensure Cloud Run has proper permissions."
        )

# Initialize Firebase
firebase_app = initialize_firebase()
db = firestore.client(app=firebase_app)