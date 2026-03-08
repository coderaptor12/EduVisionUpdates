import os
import requests
import yt_dlp
import whisper
import torch
import ssl
import gc
import time

# Bypass SSL certificate verification for model downloading
ssl._create_default_https_context = ssl._create_unverified_context

# Initialize Whisper globally on CPU to save VRAM for Ollama
print("--- Initializing AI Listening Model (Whisper) ---")
device = "cpu" 
try:
    # 'tiny' is recommended for 8GB RAM systems
    model_whisper = whisper.load_model("tiny", device=device)
except Exception as e:
    print(f"Error loading Whisper: {e}")

def download_audio_locally(url):
    """Downloads audio from any YouTube URL and converts to MP3 using FFmpeg"""
    # Use timestamp to prevent file permission errors if multiple people use it
    timestamp = int(time.time())
    output_base = f"temp_audio_{timestamp}"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_base,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'quiet': True,
        'no_warnings': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return f"{output_base}.mp3"

def get_summary(video_url):
    """
    Downloads, transcribes, and summarizes a YouTube video.
    Returns a tuple: (summary_text, transcript_text)
    """
    if not video_url:
        return "Error: No URL provided.", ""

    audio_path = None
    try:
        # Cleanup memory
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # STEP 1: Download Audio
        print(f"\n[1/3] Processing: {video_url}")
        audio_path = download_audio_locally(video_url)
        
        # STEP 2: AI Transcription
        print("[2/3] AI is transcribing audio...")
        result = model_whisper.transcribe(audio_path, fp16=False)
        transcript_text = result['text']
        
        # Immediate cleanup of audio file
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

        # STEP 3: Summarize via Ollama
        print("[3/3] Generating summary via Ollama...")
        
        trimmed_text = transcript_text[:3000] # Keep context small for speed
        
        prompt = (
            "Summarize this transcript for a student. "
            "Give a 2-sentence overview and 5 bullet points.\n\n"
            f"Transcript: {trimmed_text}"
        )

        model_name = "tinyllama" 
        
        try:
            response = requests.post("http://localhost:11434/api/generate", 
                json={
                    "model": model_name, 
                    "prompt": prompt, 
                    "stream": False,
                    "options": { "num_ctx": 2048 }
                }, timeout=120)
            
            resp_data = response.json()
            
            if "error" in resp_data:
                return f"Ollama Error: {resp_data['error']}", transcript_text

            ai_summary = resp_data.get('response')
            return ai_summary, transcript_text

        except requests.exceptions.ConnectionError:
            return "Connection Error: Ensure Ollama is running on your PC.", transcript_text

    except Exception as e:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        return f"Summary Failed: {str(e)}", ""