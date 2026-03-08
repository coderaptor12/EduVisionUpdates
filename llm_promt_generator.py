import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_visual_prompt(topic, explanation):
    if not topic or not explanation:
        return "Please provide both topic and explanation."

    prompt = f"""
Explain the topic below in simple educational language
suitable for diploma-level students.

Topic: {topic}
Explanation: {explanation}

Create a clear visual explanation prompt.
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.0-pro",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error generating explanation: {e}"
