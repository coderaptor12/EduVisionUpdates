import os
import time
import requests
import io
import re
import base64
from flask_sqlalchemy import SQLAlchemy
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from gtts import gTTS 
from dotenv import load_dotenv
from sqlalchemy import exc, text
from fpdf import FPDF, XPos, YPos 

# Google API Imports for YouTube Commenting
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Load Environment Variables
load_dotenv()
# This is CRITICAL for local testing of Google OAuth
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'eduvision_secure_7788')

# --- MAIL CONFIGURATION ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER') 
raw_pass = os.getenv('EMAIL_PASS', '')
# Clean up spaces from the app password if the user copied it with spaces
app.config['MAIL_PASSWORD'] = raw_pass.replace(" ", "") if raw_pass else ""
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('EMAIL_USER')

mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Database Configuration
db_path = os.path.join(os.path.dirname(__file__), 'eduvision.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_view'

# --- API & OAUTH CONFIGURATION ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
FAL_KEY = os.getenv("FAL_KEY", "") 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") 
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "") 

# Google OAuth2 Settings
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
YT_SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(255), nullable=True)
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
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

# --- DATABASE MIGRATION LOGIC ---

def migrate_db():
    """Ensures database columns match the code without wiping data."""
    with app.app_context():
        # Add yt_credentials if missing
        try:
            db.session.execute(text("SELECT yt_credentials FROM user LIMIT 1"))
        except Exception:
            print("MIGRATION: Adding yt_credentials to user table...")
            db.session.execute(text("ALTER TABLE user ADD COLUMN yt_credentials TEXT"))
            db.session.commit()
        
        # Add notes if missing
        try:
            db.session.execute(text("SELECT notes FROM lesson LIMIT 1"))
        except Exception:
            print("MIGRATION: Adding notes to lesson table...")
            db.session.execute(text("ALTER TABLE lesson ADD COLUMN notes TEXT DEFAULT ''"))
            db.session.commit()

# --- EMAIL LOGIC ---

def send_verification_email(user_email, username):
    token = s.dumps(user_email, salt='email-confirm')
    link = url_for('confirm_email', token=token, _external=True)
    print(f"\n--- [MAIL] Verification Link for {username}: {link} ---\n")
    try:
        msg = Message(
            'Verify Your EduVision Account', 
            recipients=[user_email],
            sender=app.config['MAIL_USERNAME']
        )
        msg.body = f"Hi {username},\n\nWelcome to EduVision AI Lab. Please verify your account by clicking the link below:\n{link}\n\nIf you did not create this account, please ignore this email."
        mail.send(msg)
        return True
    except Exception as e:
        print(f"SMTP SEND ERROR (Verification): {e}")
        return False

def send_reset_email(user_email):
    token = s.dumps(user_email, salt='password-reset')
    link = url_for('reset_password', token=token, _external=True)
    print(f"\n--- [MAIL] Password Reset Link for {user_email}: {link} ---\n")
    try:
        msg = Message(
            'Password Reset - EduVision', 
            recipients=[user_email],
            sender=app.config['MAIL_USERNAME']
        )
        msg.body = f"A password reset was requested for your EduVision account. Set a new password here:\n{link}\n\nThis link will expire in 1 hour."
        mail.send(msg)
        return True
    except Exception as e:
        print(f"SMTP SEND ERROR (Reset): {e}")
        return False

# --- YOUTUBE OAUTH FLOW ---

@app.route('/auth/google')
@login_required
def authorize_google():
    if not GOOGLE_CLIENT_ID:
        flash("Google Client ID not set in .env")
        return redirect(url_for('main_dashboard'))
    flow = Flow.from_client_config(
        {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=YT_SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
     # THE FIX: Store the state AND the code_verifier in the session
    session['state'] = state
    session['code_verifier'] = flow.code_verifier
    return redirect(authorization_url)

@app.route('/oauth2callback')
@login_required
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_config(
        {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=YT_SCOPES, state=state
    )
     # THE FIX: Restore the code_verifier from the session
    flow.code_verifier = session.get('code_verifier')
    
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    current_user.yt_credentials = json.dumps({
        'token': credentials.token, 'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
        'client_secret': credentials.client_secret, 'scopes': credentials.scopes
    })
    db.session.commit()
    flash("YouTube Connected!")
    return redirect(url_for('main_dashboard'))

# --- AUTH ROUTES ---

@app.route("/login", methods=['GET', 'POST'])
def login_view():
    if current_user.is_authenticated: return redirect(url_for('main_dashboard'))
    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        p = request.form.get('password', '').strip()
        user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
        if user and user.password == p:
            if not user.is_verified:
                send_verification_email(user.email, user.username)
                flash("Email not verified. Check your inbox (or terminal).")
                return redirect(url_for('login_view'))
            login_user(user, remember=True)
            return redirect(url_for('main_dashboard'))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register_view():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        e = request.form.get('email', '').strip()
        p = request.form.get('password', '').strip()

        if not u or not e or not p:
            flash("All fields are required.")
            return redirect(url_for('register_view'))

        if User.query.filter_by(username=u).first():
            flash("Username already taken.")
            return redirect(url_for('register_view'))
        if User.query.filter_by(email=e).first():
            flash("An account with this email already exists.")
            return redirect(url_for('register_view'))

        try:
            new_user = User(username=u, email=e, password=p, is_verified=False)
            db.session.add(new_user)
            db.session.commit()
            
            email_sent = send_verification_email(e, u)
            if email_sent:
                flash("Account created! Verify your email to login.")
            else:
                flash("Account created! (Verification email failed, check terminal for link).")
                
            return redirect(url_for('login_view'))
        except Exception as err:
            db.session.rollback()
            flash(f"Error during registration: {str(err)}")
            return redirect(url_for('register_view'))

    return render_template("register.html")

@app.route('/confirm_email/<token>')
def confirm_email(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_verified = True
            db.session.commit()
            flash("Email verified successfully!")
    except:
        flash("The verification link is invalid or has expired.")
    return redirect(url_for('login_view'))

@app.route("/forgot_password", methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if user:
            if send_reset_email(email):
                flash("Reset link sent to your email.")
            else:
                flash("Failed to send email. Check terminal for the link.")
        else:
            flash("If that email is registered, a link has been sent.")
        return redirect(url_for('login_view'))
    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = s.loads(token, salt='password-reset', max_age=3600)
    except:
        flash("Invalid or expired reset link.")
        return redirect(url_for('login_view'))
    
    if request.method == 'POST':
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = request.form.get('password').strip()
            db.session.commit()
            flash("Password updated successfully!")
            return redirect(url_for('login_view'))
    return render_template("reset_password_form.html", token=token)

# --- PAYMENT & CHECKOUT ROUTES ---

@app.route("/checkout")
@login_required
def checkout():
    """Renders the secure payment page. Uses payment.html."""
    amount = request.args.get('amount', 149)
    return render_template("payment.html", amount=amount, upi_id="eduvision@bank")

@app.route("/api/payment/verify", methods=['POST'])
@login_required
def verify_payment():
    """Simulates payment verification and upgrades user to Premium."""
    current_user.is_premium = True
    current_user.daily_quota = 20
    db.session.commit()
    return jsonify({"status": "success", "message": "Account upgraded to Elite Pro!"})

# --- ADMIN & STATS ROUTES ---

@app.route("/admin/stats")
@login_required
def admin_stats():
    """Professional dashboard to see how many users are registered and active."""
    users = User.query.all()
    total_lessons = Lesson.query.count()
    
    html = f"""
    <div style="font-family: sans-serif; padding: 40px; background: #0f172a; color: #fff; min-height: 100vh;">
        <h1 style="color: #10b981; font-size: 36px; margin-bottom: 10px;">EduVision Admin Dashboard</h1>
        <p style="color: #94a3b8; margin-bottom: 30px;">Broker Analytics: Monitoring {len(users)} researchers.</p>
        
        <div style="display: flex; gap: 20px; margin-bottom: 40px;">
            <div style="background: #1e293b; padding: 20px; border-radius: 12px; flex: 1; border: 1px solid #334155;">
                <h3 style="color: #94a3b8; text-transform: uppercase; font-size: 10px; margin: 0;">Total Users</h3>
                <p style="font-size: 32px; font-weight: bold; margin: 10px 0;">{len(users)}</p>
            </div>
            <div style="background: #1e293b; padding: 20px; border-radius: 12px; flex: 1; border: 1px solid #334155;">
                <h3 style="color: #94a3b8; text-transform: uppercase; font-size: 10px; margin: 0;">Total Lessons</h3>
                <p style="font-size: 32px; font-weight: bold; margin: 10px 0;">{total_lessons}</p>
            </div>
        </div>

        <table style="width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden;">
            <thead>
                <tr style="background: #334155; text-align: left;">
                    <th style="padding: 15px;">ID</th>
                    <th style="padding: 15px;">Username</th>
                    <th style="padding: 15px;">Email</th>
                    <th style="padding: 15px;">Plan</th>
                    <th style="padding: 15px;">Usage</th>
                </tr>
            </thead>
            <tbody>
    """
    for u in users:
        plan = "<span style='color: #10b981;'>Elite</span>" if u.is_premium else "Starter"
        html += f"""
                <tr style="border-bottom: 1px solid #334155;">
                    <td style="padding: 15px;">{u.id}</td>
                    <td style="padding: 15px;">{u.username}</td>
                    <td style="padding: 15px;">{u.email}</td>
                    <td style="padding: 15px;">{plan}</td>
                    <td style="padding: 15px;">{u.video_count}/{u.daily_quota}</td>
                </tr>
        """
    html += """
            </tbody>
        </table>
    </div>
    """
    return html

# --- CORE AI LAB ROUTES ---

@app.route("/")
@login_required
def main_dashboard():
    """Passes user and the 'has_youtube' boolean to the index template."""
    return render_template(
        "index.html", 
        user=current_user,
        has_youtube=bool(current_user.yt_credentials)
    )

@app.route('/explain', methods=['POST'])
@login_required
def process_ai_lesson():
    if not current_user.is_premium and current_user.video_count >= current_user.daily_quota:
        return jsonify({"status": "error", "message": "Quota exceeded. Upgrade to Pro."})
    
    topic = request.form.get("topic")
    mode = request.form.get("mode", "text")
    
    # Simulate AI generation
    explanation = f"Detailed analysis of {topic}..."
    yt_id = "dQw4w9WgXcQ" 
    img_url = f"https://api.dicebear.com/7.x/identicon/svg?seed={topic}"
    vid_url = "unavailable"
    
    new_l = Lesson(topic=topic, explanation=explanation, video_path=vid_url, image_path=img_url, youtube_id=yt_id, user_id=current_user.id)
    current_user.video_count += 1
    db.session.add(new_l)
    db.session.commit()
    
    return jsonify({
        "status": "success", "id": new_l.id, "topic": topic, "explanation": explanation, 
        "image": img_url, "video": vid_url, "youtube_id": yt_id, 
        "video_count": current_user.video_count
    })

@app.route('/get_history')
@login_required
def get_history():
    lessons = Lesson.query.filter_by(user_id=current_user.id).order_by(Lesson.id.desc()).all()
    return jsonify([{"id": l.id, "topic": l.topic, "explanation": l.explanation, "image": l.image_path, "video": l.video_path, "youtube_id": l.youtube_id, "notes": l.notes} for l in lessons])

@app.route('/save_notes/<int:lesson_id>', methods=['POST'])
@login_required
def save_notes(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    lesson.notes = request.json.get('notes', "")
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/download_pdf/<int:lesson_id>')
@login_required
def download_pdf(lesson_id):
    """Generates a PDF report containing the explanation and image."""
    lesson = Lesson.query.get_or_404(lesson_id)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 20, f"Lab Report: {lesson.topic}", ln=True, align="C")
    
    if lesson.image_path:
        try:
            img_res = requests.get(lesson.image_path, timeout=5)
            if img_res.status_code == 200:
                img_data = io.BytesIO(img_res.content)
                pdf.image(img_data, x=10, y=40, w=190)
                pdf.set_y(160)
        except:
            pdf.set_y(40)

    pdf.set_font("Helvetica", "", 12)
    clean_text = lesson.explanation.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, clean_text)
    
    filename = f"EduVision_{lesson.topic.replace(' ', '_')}.pdf"
    return send_file(io.BytesIO(pdf.output()), mimetype='application/pdf', as_attachment=True, download_name=filename)

@app.route("/debug/reset_db")
def reset_database():
    db.drop_all()
    db.create_all()
    return "Database Wiped and Recreated."

@app.route("/logout")
@login_required
def logout_user_session():
    logout_user()
    return redirect(url_for('login_view'))

if __name__ == "__main__":
    migrate_db()
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
