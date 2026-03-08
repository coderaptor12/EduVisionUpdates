# scene_splitter.py
# splits explanation text into individual scene sentences

def split_into_scenes(text):
    # split by dot + remove empty parts + strip spaces
    raw_scenes = text.split(".")
    scenes = [s.strip() for s in raw_scenes if s.strip() != ""]
    return scenes

# test
if __name__ == "__main__":
    explanation = "Light enters through cornea. Lens focuses image. Retina converts signals. Brain forms vision."
    print(split_into_scenes(explanation))
