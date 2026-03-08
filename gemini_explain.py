import ollama

def explain_topic(topic, level):
    try:
        # Ensure Ollama app is open in your system tray
        response = ollama.chat(model='gemma3:1b', messages=[
            {
                'role': 'user',
                'content': f"Explain {topic} for a {level} level student. Include 1) Definition 2) Working 3) Applications.",
            },
        ])
        return response['message']['content']
    except Exception as e:
        print(f"Ollama Error: {e}")
        return "Ollama is not running. Please open the Ollama app."

# --- Simple test block (Runs only if you play this file directly) ---
if __name__ == "__main__":
    test_topic = "Internal Combustion Engine"
    print(f"Testing Ollama with topic: {test_topic}...")
    print(explain_topic(test_topic))