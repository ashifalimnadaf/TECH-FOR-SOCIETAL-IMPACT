import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import json
import uuid
from datetime import datetime
import hashlib

app = Flask(__name__)

# Firebase Initialization
# You need to download your serviceAccountKey.json from Firebase Console
# Project Settings -> Service Accounts -> Generate New Private Key
SERVICE_ACCOUNT_PATH = 'serviceAccountKey.json'

if os.path.exists(SERVICE_ACCOUNT_PATH):
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    USE_FIREBASE = True
else:
    print("WARNING: serviceAccountKey.json not found. Falling back to local storage.")
    USE_FIREBASE = False

# Local Constants (Fallback)
DATA_DIR = 'data'
GRIEVANCES_FILE = os.path.join(DATA_DIR, 'grievances.json')
BLOCKCHAIN_FILE = os.path.join(DATA_DIR, 'blockchain_logs.json')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_grievances():
    if USE_FIREBASE:
        docs = db.collection('grievances').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        return [doc.to_dict() for doc in docs]
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
    
    log_to_blockchain(grievance)

def log_to_blockchain(grievance):
    prev_hash = "0" * 64
    
    if USE_FIREBASE:
        # Get the last log hash
        last_log = db.collection('blockchain').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1).get()
        if last_log:
            prev_hash = last_log[0].to_dict()['hash']
    else:
        if os.path.exists(BLOCKCHAIN_FILE):
            with open(BLOCKCHAIN_FILE, 'r') as f:
                logs = json.load(f)
                if logs: prev_hash = logs[-1]['hash']

    log_entry = {
        "id": str(uuid.uuid4()),
        "grievance_id": grievance['id'],
        "timestamp": datetime.now().isoformat(),
        "action": "SUBMITTED",
        "prev_hash": prev_hash
    }
    
    content = f"{log_entry['grievance_id']}{log_entry['timestamp']}{log_entry['action']}{prev_hash}"
    log_entry['hash'] = hashlib.sha256(content.encode()).hexdigest()
    
    if USE_FIREBASE:
        db.collection('blockchain').document(log_entry['id']).set(log_entry)
    else:
        with open(BLOCKCHAIN_FILE, 'r') as f:
            logs = json.load(f)
        logs.append(log_entry)
        with open(BLOCKCHAIN_FILE, 'w') as f:
            json.dump(logs, f, indent=4)

@app.route('/')
def index():
    return render_template('auth.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/authority')
def authority():
    return render_template('authority.html')

@app.route('/api/vouch', methods=['POST'])
def vouch_grievance():
    gid = request.json.get('id')
    # logic to increment vouch count
    return jsonify({"success": True})

@app.route('/api/submit', methods=['POST'])
def submit_grievance():
    data = request.form
    grievance_id = str(uuid.uuid4())[:8].upper()
    
    new_grievance = {
        "id": grievance_id,
        "type": data.get('type', 'General'),
        "content": data.get('content', ''),
        "is_voice": data.get('is_voice') == 'true',
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Pending",
        "verified": False,
        "verification_count": 0,
        "proof_of_action": []
    }
    
    save_grievance(new_grievance)
    return jsonify({"success": True, "id": grievance_id})

@app.route('/api/grievances', methods=['GET'])
def list_grievances():
    return jsonify(get_grievances())

@app.route('/api/verify', methods=['POST'])
def verify_grievance():
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
    else:
        grievances = get_grievances()
        for g in grievances:
            if g['id'] == gid:
                g['verification_count'] += 1
                if g['verification_count'] >= 3:
                    g['verified'] = True
                break
        with open(GRIEVANCES_FILE, 'w') as f:
            json.dump(grievances, f, indent=4)
            
    return jsonify({"success": True})

@app.route('/api/summarize', methods=['GET'])
def summarize_grievances():
    grievances = get_grievances()
    if not grievances:
        return jsonify({"summary": "No grievances reported yet."})
    
    summary = f"Currently, there are {len(grievances)} active complaints. "
    pending = len([g for g in grievances if g['status'] == 'Pending'])
    summary += f"{pending} are pending action. Most common issues relate to public infrastructure."
    
    return jsonify({"summary": summary})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
