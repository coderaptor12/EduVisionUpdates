import os
import subprocess

IMAGE_DIR = "static/images"
OUTPUT_DIR = "videos"
OUTPUT_VIDEO = os.path.join(OUTPUT_DIR, "yt_short.mp4")

os.makedirs(OUTPUT_DIR, exist_ok=True)

images = sorted([
    os.path.join(IMAGE_DIR, img)
    for img in os.listdir(IMAGE_DIR)
    if img.lower().endswith((".png", ".jpg", ".jpeg"))
])

if not images:
    raise RuntimeError("No images found")

# Create FFmpeg concat file
list_file = "shorts_images.txt"
with open(list_file, "w") as f:
    for img in images:
        f.write(f"file '{img}'\n")
        f.write("duration 1\n")  # FAST cuts (Shorts style)

ffmpeg_cmd = [
    "ffmpeg",
    "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", list_file,
    "-vf",
    (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.004,1.3)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=24:fps=24"
    ),
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    OUTPUT_VIDEO
]

subprocess.run(ffmpeg_cmd, check=True)
