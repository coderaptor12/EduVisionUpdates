from moviepy import ImageClip, CompositeVideoClip

def scene_generator(image_path="static/images/human_eye.png", 
                    output_path="static/videos/output_scene.mp4",
                    duration=5):

    image_clip = ImageClip(image_path).set_duration(duration)
    video = CompositeVideoClip([image_clip])

    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    print(f"Video created: {output_path}")
