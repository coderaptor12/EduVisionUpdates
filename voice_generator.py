from gtts import gTTS
import os

def generate_voice(text, topic):
    os.makedirs("static/audio", exist_ok=True)

    filename = topic.replace(" ", "_") + ".mp3"
    path = f"static/audio/{filename}"

    tts = gTTS(text=text, lang="en")
    tts.save(path)

    return "/" + path