import os
import asyncio
import edge_tts

VOICE_MAP = {
    "male": "en-IN-PrabhatNeural",
    "female": "en-IN-NeerjaNeural",
    "kids": "en-US-JennyNeural",
}

async def _save_audio(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_scene_audio(scenes, output_folder="static/audio/scenes", voice="female"):
    os.makedirs(output_folder, exist_ok=True)

    voice_name = VOICE_MAP.get(voice, "en-IN-NeerjaNeural")
    audio_files = []

    for i, scene in enumerate(scenes):
        scene_text = scene["text"]

        output_path = os.path.join(output_folder, f"scene_{i+1}.mp3")

        asyncio.run(_save_audio(scene_text, voice_name, output_path))

        audio_files.append(output_path)

    return audio_files
