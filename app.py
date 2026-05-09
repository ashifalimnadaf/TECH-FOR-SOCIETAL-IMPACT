import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template, request, jsonify, send_from_directory, session
import os
import json
import uuid
from datetime import datetime
import hashlib
from werkzeug.utils import secure_filename
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import re
from collections import Counter

# Configuration & Constants
SERVICE_ACCOUNT_PATH = 'serviceAccountKey.json'
UPLOAD_FOLDER = 'static/uploads'
DATA_DIR = 'data'
GRIEVANCES_FILE = os.path.join(DATA_DIR, 'grievances.json')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Speech to Text Initialization
try:
    import speech_recognition as sr
    HAS_SPEECH = True
    print("SUCCESS: Speech-to-Text (Free Web API) initialized.")
except ImportError:
    print("Speech-to-Text: 'SpeechRecognition' library missing. Run 'pip install SpeechRecognition'.")
    HAS_SPEECH = False

app = Flask(__name__)
app.secret_key = "safevoice_secret_key"

# Firebase Initialization
if os.path.exists(SERVICE_ACCOUNT_PATH):
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        USE_FIREBASE = True
        project_id = json.load(open(SERVICE_ACCOUNT_PATH))['project_id']
        print(f"SUCCESS: Connected to Firebase Database (Project: {project_id})")
    except Exception as e:
        print(f"ERROR: Firebase connection failed: {e}")
        USE_FIREBASE = False
else:
    print("WARNING: serviceAccountKey.json not found. Falling back to local storage.")
    USE_FIREBASE = False

# Local Constants (Fallback)
DATA_DIR = 'data'
GRIEVANCES_FILE = os.path.join(DATA_DIR, 'grievances.json')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def extract_keywords(text):
    if not text: return "General Issue"
    # Simple keyword extraction: remove stop words and take most frequent nouns/verbs
    # For a prototype, let's just take the first few meaningful words
    words = re.findall(r'\w+', text.lower())
    stop_words = {'i', 'the', 'is', 'at', 'which', 'on', 'a', 'this', 'that', 'there', 'my', 'problem', 'issue', 'complaint'}
    meaningful_words = [w for w in words if w not in stop_words and len(w) > 3]
    if not meaningful_words: return text[:30] + "..." if len(text) > 30 else text
    
    counts = Counter(meaningful_words)
    top_keywords = [w for w, c in counts.most_common(2)]
    return " ".join(top_keywords).upper()

def transcribe_audio(file_path):
    if not HAS_SPEECH: return "[Transcription not available]"
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        
        # SpeechRecognition requires .wav files. 
        # If your files are .webm or .mp3, you'd usually need ffmpeg to convert them.
        # For now, let's try reading it as an audio file.
        with sr.AudioFile(file_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            return text
    except Exception as e:
        print(f"Transcription error: {e}")
        # If it's a format issue (e.g. webm), we let the user know
        if "format" in str(e).lower() or "executing ffmpeg" in str(e).lower():
            return "[Audio format requires conversion or was handled by browser]"
        return f"[Transcription Error: {e}]"

def get_grievances():
    if USE_FIREBASE:
        docs = db.collection('grievances').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            # Ensure timestamp is a string for JSON serialization
            if 'timestamp' in data and not isinstance(data['timestamp'], str):
                try:
                    data['timestamp'] = data['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            results.append(data)
        return results
    else:
        if not os.path.exists(GRIEVANCES_FILE): return []
        with open(GRIEVANCES_FILE, 'r') as f:
            return json.load(f)

def save_grievance(grievance):
    if USE_FIREBASE:
        db.collection('grievances').document(grievance['id']).set(grievance)
    else:
        grievances = get_grievances()
        grievances.append(grievance)
        with open(GRIEVANCES_FILE, 'w') as f:
            json.dump(grievances, f, indent=4)

def find_similar_grievances(new_content, location_text):
    if not new_content or len(new_content) < 10:
        return None
    
    all_grievances = get_grievances()
    
    # Filter by location (simple string matching for now)
    # Extract area name if possible, or just exact match
    # For better results, we could use fuzzy matching on location too
    same_loc_grievances = [g for g in all_grievances if location_text.lower() in g.get('location', '').lower() or g.get('location', '').lower() in location_text.lower()]
    
    if not same_loc_grievances:
        return None
        
    contents = [g.get('content', '') for g in same_loc_grievances if g.get('content')]
    if not contents:
        return None
        
    # Add the new content to the list for vectorization
    tfidf = TfidfVectorizer().fit_transform(contents + [new_content])
    
    # Calculate cosine similarity between the last one (new_content) and all others
    similarities = cosine_similarity(tfidf[-1], tfidf[:-1])[0]
    
    if len(similarities) == 0:
        return None
        
    max_idx = np.argmax(similarities)
    max_sim = similarities[max_idx]
    
    if max_sim > 0.4: # Similarity threshold
        return {
            "id": same_loc_grievances[max_idx]['id'],
            "content": same_loc_grievances[max_idx]['content'],
            "type": same_loc_grievances[max_idx].get('type', 'General'),
            "location": same_loc_grievances[max_idx].get('location', 'Unknown'),
            "timestamp": same_loc_grievances[max_idx].get('timestamp', ''),
            "media": same_loc_grievances[max_idx].get('media', []),
            "similarity": float(max_sim)
        }
    
    return None

@app.route('/')
def index():
    return render_template('auth.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/authority')
def authority():
    return render_template('authority.html')

@app.route('/api/auth', methods=['POST'])
def handle_auth():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'user')
    action = data.get('action')

    if USE_FIREBASE:
        user_ref = db.collection('users').document(email)
        user_doc = user_ref.get()

        if action == 'signup':
            if user_doc.exists:
                return jsonify({"success": False, "message": "User already exists"})
            user_ref.set({"email": email, "password": password, "role": role})
            session['user'] = email
            return jsonify({"success": True, "role": role})
        else:
            if not user_doc.exists or user_doc.to_dict()['password'] != password:
                return jsonify({"success": False, "message": "Invalid credentials"})
            session['user'] = email
            return jsonify({"success": True, "role": user_doc.to_dict()['role']})
    else:
        # Simple fallback for local
        session['user'] = email
        return jsonify({"success": True, "role": 'authority' if 'admin' in email else 'user'})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file part"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"})
    
    filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    url = f"/static/uploads/{filename}"
    transcript = ""
    
    # Transcribe if it's an audio file
    if file.filename.endswith(('.wav', '.mp3', '.webm')) or 'audio' in file.content_type:
        transcript = transcribe_audio(filepath)
        
    return jsonify({"success": True, "url": url, "transcript": transcript})

@app.route('/api/submit', methods=['POST'])
def submit_grievance():
    data = request.json
    grievance_id = f"SV-{str(uuid.uuid4())[:6].upper()}"
    
    new_grievance = {
        "id": grievance_id,
        "type": data.get('type', 'General'),
        "content": data.get('content', ''),
        "media": data.get('media', []), # List of URLs
        "location": data.get('location', 'Unknown'),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Pending",
        "verified": False,
        "verification_count": 0,
        "user_email": session.get('user', 'anonymous'),
        "headline": extract_keywords(data.get('content', '')),
        "transcriptions": data.get('transcriptions', []) # To store transcribed text from audio
    }
    
    save_grievance(new_grievance)
    return jsonify({"success": True, "id": grievance_id})

@app.route('/api/check_similarity', methods=['POST'])
def check_similarity():
    data = request.json
    content = data.get('content', '')
    location = data.get('location', 'Unknown')
    
    similar = find_similar_grievances(content, location)
    if similar:
        return jsonify({"success": True, "similar": similar})
    return jsonify({"success": False})

@app.route('/api/grievances', methods=['GET'])
def list_grievances():
    grievances = get_grievances()
    
    # Privacy protection: Authority should not see user email
    if session.get('role') == 'authority' or request.args.get('role') == 'authority':
        for g in grievances:
            if 'user_email' in g:
                g['user_email'] = "[HIDDEN FOR PRIVACY]"
    
    return jsonify(grievances)

@app.route('/api/vouch', methods=['POST'])
def vouch_grievance():
    gid = request.json.get('id')
    if USE_FIREBASE:
        doc_ref = db.collection('grievances').document(gid)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            new_count = data.get('verification_count', 0) + 1
            doc_ref.update({
                'verification_count': new_count,
                'verified': new_count >= 3
            })
            return jsonify({"success": True})
    else:
        grievances = get_grievances()
        for g in grievances:
            if g['id'] == gid:
                g['verification_count'] = g.get('verification_count', 0) + 1
                g['verified'] = g['verification_count'] >= 3
                break
        with open(GRIEVANCES_FILE, 'w') as f:
            json.dump(grievances, f, indent=4)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/api/update_status', methods=['POST'])
def update_status():
    data = request.json
    gid = data.get('id')
    new_status = data.get('status')
    
    if USE_FIREBASE:
        db.collection('grievances').document(gid).update({"status": new_status})
        return jsonify({"success": True})
    else:
        grievances = get_grievances()
        for g in grievances:
            if g['id'] == gid:
                g['status'] = new_status
                break
        with open(GRIEVANCES_FILE, 'w') as f:
            json.dump(grievances, f, indent=4)
        return jsonify({"success": True})
    return jsonify({"success": False})

if __name__ == '__main__':
    app.run(debug=True, port=5000)

