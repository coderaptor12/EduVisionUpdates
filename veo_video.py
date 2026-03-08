import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Initialize the Google GenAI Client
# Ensure you have GOOGLE_API_KEY in your .env file
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_veo_video(topic, explanation):
    try:
        print(f"🚀 Veo 3.1 is crafting a movie for: {topic}")
        
        # Use the 'Fast' model to save your free credits
        model_id = "veo-3.1-fast-generate-preview"
        
        # Create the prompt
        prompt = f"Educational 3D animation about {topic}. {explanation}. Clear, high-quality, professional lighting."

        # Start the generation
        operation = client.models.generate_videos(
            model=model_id,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                duration_seconds=8, # Choice of 4, 6, or 8
                aspect_ratio="16:9",
                resolution="720p"    # 720p uses fewer credits than 1080p
            )
        )

        # Wait for the video to finish (Polling)
        while not operation.done:
            print("⏳ AI is animating... please wait.")
            time.sleep(10)
            operation = client.operations.get(operation)

        # Get the result
        generated_video = operation.result.generated_videos[0]
        
        # The API returns a cloud URI, we need to download/save it
        video_filename = f"static/videos/video_{int(time.time())}.mp4"
        os.makedirs("static/videos", exist_ok=True)
        
        # Save the video locally
        client.files.download(file=generated_video.video, path=video_filename)
        
        print(f"✅ Video saved to: {video_filename}")
        return f"/{video_filename}" # Return path for the HTML

    except Exception as e:
        print(f"❌ Veo Error: {e}")
        return ""