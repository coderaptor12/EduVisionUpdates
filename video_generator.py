import torch
from diffusers import LTXVideoPipeline
from diffusers.utils import export_to_video

# Optimization: Load model once to save time
device = "cuda" if torch.cuda.is_available() else "cpu"
pipe = LTXVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.float16)
pipe.to(device)

# Enable memory savings to hit that 1-minute target
pipe.enable_model_cpu_offload()

def generate_local_ltx_video(topic):
    prompt = f"Educational 3D animation of {topic}, high quality, smooth motion, 24fps."
    
    # ⚡ Generation settings for < 60 seconds
    video_frames = pipe(
        prompt=prompt,
        num_inference_steps=25, # Lower steps = faster speed
        num_frames=24,          # 1 second of high-quality motion
        height=512,
        width=512,
        guidance_scale=3.5,
    ).frames[0]

    output_path = f"static/videos/{topic.replace(' ', '_')}.mp4"
    export_to_video(video_frames, output_path, fps=24)
    return f"/{output_path}"