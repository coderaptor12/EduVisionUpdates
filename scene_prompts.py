def get_scene_prompts(topic, explanation):
    """
    Return 4 scene prompts for images + subtitles
    """

    scene_texts = [
        f"Today we will learn: {topic}",
        f"Concept: {topic} explained simply",
        "Step by Step working process",
        "Conclusion and real-life application"
    ]

    scene_prompts = [
        f"Cartoon teacher explaining {topic} on classroom board, Byjus style animation, colorful, high quality",
        f"Illustration of {topic}, simple science diagram, cartoon style, Byjus animation style",
        f"Step by step working process of {topic}, infographic, educational cartoon",
        f"Real life example of {topic}, students learning, cartoon style"
    ]

    return scene_prompts, scene_texts
