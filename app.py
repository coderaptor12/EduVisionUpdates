import os
import time
import requests
import io
import re
import base64
import json
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from gtts import gTTS 
from dotenv import load_dotenv
from sqlalchemy import exc, text, inspect
from fpdf import FPDF, XPos, YPos 

# Import your YouTube Transcription Logic
try:
    from vedio_summary import get_summary
except ImportError:
    # Fallback if file is missing during initial setup
    def get_summary(url): return "Transcription module not found.", ""

# Google API Imports
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

load_dotenv()
# This is CRITICAL for local testing of Google OAuth
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'eduvision_secure_7788')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Database Persistence for Render
if os.path.exists('/data'):
    db_path = '/data/eduvision.db'
else:
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'eduvision.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_view'

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
YT_SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(255), nullable=True)
    security_answer = db.Column(db.String(255), nullable=True)
    is_verified = db.Column(db.Boolean, default=False) 
    is_premium = db.Column(db.Boolean, default=False)
    daily_quota = db.Column(db.Integer, default=5)
    video_count = db.Column(db.Integer, default=0)
    yt_credentials = db.Column(db.Text, nullable=True) 
    lessons = db.relationship('Lesson', backref='user', lazy=True)

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(255))
    explanation = db.Column(db.Text)
    video_path = db.Column(db.String(500)) 
    image_path = db.Column(db.Text)        
    audio_path = db.Column(db.String(500)) 
    youtube_id = db.Column(db.String(100)) 
    notes = db.Column(db.Text, default="") 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- DATABASE INITIALIZATION ---
def init_db():
    with app.app_context():
        db.create_all()
        # Add columns if they are missing (Self-healing migration)
        inspector = inspect(db.engine)
        user_cols = [c['name'] for c in inspector.get_columns('user')]
        if 'security_answer' not in user_cols:
            db.session.execute(text("ALTER TABLE user ADD COLUMN security_answer TEXT"))
            db.session.commit()

init_db()

# --- AI LOGIC (GROQ & GEMINI ONLY - NO OLLAMA) ---

def call_cloud_ai(prompt):
    """Orchestrates AI generation using Groq as primary and Gemini as secondary."""
    # 1. Try Groq (Llama 3.3 is extremely fast)
    if GROQ_API_KEY:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=15
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Groq API Error: {e}")

    # 2. Fallback to Gemini
    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            response = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15
            )
            if response.status_code == 200:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")

    return "AI generation is currently unavailable. Please check your API keys."

def generate_ai_explanation(topic, level):
    prompt = f"Act as a professional tutor. Explain the topic '{topic}' in depth for a {level} student. Use formatting and bullet points."
    return call_cloud_ai(prompt)

def generate_video_summary(transcript):
    prompt = (
        "You are an expert educational summarizer. Based on the following video transcript, "
        "provide a concise summary. Structure it with a 2-sentence overview followed by "
        "5 key bullet points highlighting the most important facts.\n\n"
        f"Transcript: {transcript[:5000]}"
    )
    return call_cloud_ai(prompt)

def extract_yt_id(url):
    """Extracts YouTube ID from any valid YouTube URL."""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else "dQw4w9WgXcQ"

# --- ROUTES ---

@app.route("/")
@login_required
def main_dashboard():
    return render_template("index.html", user=current_user, has_youtube=bool(current_user.yt_credentials))

@app.route('/explain', methods=['POST'])
@login_required
def process_ai_lesson():
    if not current_user.is_premium and current_user.video_count >= current_user.daily_quota:
        return jsonify({"status": "error", "message": "Daily quota reached. Upgrade to Pro."})
    
    input_text = request.form.get("topic")
    mode = request.form.get("mode", "text")
    level = request.form.get("level", "College")
    
    topic = input_text
    yt_id = "dQw4w9WgXcQ" 
    explanation = ""

    if mode == "summary":
        yt_id = extract_yt_id(input_text)
        logger.info(f"Summarizing Video ID: {yt_id}")
        
        # get_summary from vedio_summary.py handles audio and transcription
        # We capture the transcript and summarize it using Cloud AI instead of Ollama
        result, transcript = get_summary(input_text)
        
        if transcript:
            explanation = generate_video_summary(transcript)
        else:
            explanation = result # This will be the error message from the module
        
        topic = f"Video Summary: {yt_id}"
    else:
        explanation = generate_ai_explanation(topic, level)

    img_url = f"https://api.dicebear.com/7.x/identicon/svg?seed={topic}"
    
    new_l = Lesson(topic=topic, explanation=explanation, video_path="unavailable", image_path=img_url, youtube_id=yt_id, user_id=current_user.id)
    current_user.video_count += 1
    db.session.add(new_l)
    db.session.commit()
    
    return jsonify({
        "status": "success", "id": new_l.id, "topic": topic, "explanation": explanation, 
        "image": img_url, "video": "unavailable", "youtube_id": yt_id, 
        "video_count": current_user.video_count, "quota": current_user.daily_quota
    })

# --- OAUTH & YOUTUBE SYNC ---

@app.route('/auth/google')
@login_required
def auth_google():
    if not GOOGLE_CLIENT_ID:
        flash("Google Client ID not set in .env")
        return redirect(url_for('main_dashboard'))
    flow = Flow.from_client_config(
        {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=YT_SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'], session['code_verifier'] = state, flow.code_verifier
    return redirect(auth_url)

@app.route('/oauth2callback')
@login_required
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_config(
        {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=YT_SCOPES, state=state
    )
    flow.code_verifier = session.get('code_verifier')
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    flow.fetch_token(authorization_response=request.url)
    current_user.yt_credentials = flow.credentials.to_json()
    db.session.commit()
    flash("YouTube Connected!")
    return redirect(url_for('main_dashboard'))

@app.route('/sync_to_youtube/<int:lesson_id>', methods=['POST'])
@login_required
def sync_to_youtube(lesson_id):
    if not current_user.yt_credentials:
        return jsonify({"status": "error", "message": "YouTube not connected."})
    
    lesson = Lesson.query.get_or_404(lesson_id)
    if not lesson.notes:
        return jsonify({"status": "error", "message": "No research notes found to sync."})

    try:
        creds = Credentials.from_authorized_user_info(json.loads(current_user.yt_credentials))
        youtube = build('youtube', 'v3', credentials=creds)
        
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": lesson.youtube_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": f"EduVision Lab Notes: {lesson.notes}"
                        }
                    }
                }
            }
        ).execute()
        
        return jsonify({"status": "success", "message": "Notes posted to YouTube!"})
    except Exception as e:
        logger.error(f"YouTube Sync Error: {e}")
        return jsonify({"status": "error", "message": "Failed to post comment. Token may have expired."})

# --- AUTH & SYSTEM ROUTES ---

@app.route("/login", methods=['GET', 'POST'])
def login_view():
    if current_user.is_authenticated: return redirect(url_for('main_dashboard'))
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        user = User.query.filter_by(username=u).first()
        if user and user.password == p:
            login_user(user, remember=True)
            return redirect(url_for('main_dashboard'))
        flash("Invalid credentials.")
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register_view():
    if request.method == 'POST':
        u, p, a = request.form.get('username'), request.form.get('password'), request.form.get('security_answer')
        if User.query.filter_by(username=u).first():
            flash("Username already exists.")
            return redirect(url_for('register_view'))
        
        new_user = User(username=u, password=p, security_answer=a, is_verified=True)
        db.session.add(new_user)
        db.session.commit()
        flash("Account created! Please login.")
        return redirect(url_for('login_view'))
    return render_template("register.html")

@app.route('/get_history')
@login_required
def get_history():
    lessons = Lesson.query.filter_by(user_id=current_user.id).order_by(Lesson.id.desc()).all()
    return jsonify([{"id": l.id, "topic": l.topic, "explanation": l.explanation, "image": l.image_path, "video": l.video_path, "youtube_id": l.youtube_id, "notes": l.notes} for l in lessons])

@app.route('/save_notes/<int:lesson_id>', methods=['POST'])
@login_required
def save_notes(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if lesson.user_id != current_user.id: return jsonify({"status": "error"}), 403
    lesson.notes = request.json.get('notes', "")
    db.session.commit()
    return jsonify({"status": "success"})

@app.route("/logout")
@login_required
def logout_user_session():
    logout_user()
    return redirect(url_for('login_view'))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
