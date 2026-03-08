import os
import requests
from dotenv import load_dotenv
load_dotenv()

HF_API_KEY = os.getenv("HF_API_KEY")

def generate_image(prompt):
    os.makedirs("static/images", exist_ok=True)

    filename = prompt.replace(" ", "_") + ".png"
    output_path = f"static/images/{filename}"

    if os.path.exists(output_path):
        return "/" + output_path

    # HuggingFace Stable Diffusion model
    url = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"

    headers = {"Authorization": f"Bearer {HF_API_KEY}"}

    payload = {"inputs": f"Educational diagram illustration of {prompt}, science style"}

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        print("❌ HF Error:", response.text)
        return "/static/images/default.png"

    with open(output_path, "wb") as f:
        f.write(response.content)

    return "/" + output_path