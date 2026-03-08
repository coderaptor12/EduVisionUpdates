from moviepy import ImageClip, vfx

def generate_scenes(image_path, output_path, duration=8):
    clip = ImageClip(image_path).with_duration(duration)
    clip = clip.resized((1280, 720))

    # Zoom effect
    clip = clip.with_effects([vfx.Resize(lambda t: 1 + 0.03*t)])

    # Fade in/out
    clip = clip.with_effects([vfx.FadeIn(1), vfx.FadeOut(1)])

    clip.write_videofile(output_path, fps=24, codec="libx264")

    print("✅ Animated video created:", output_path)
