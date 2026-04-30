import urllib.parse, re

def generate_image(prompt: str):
    """
    Generates a high-quality image based on a text description.
    Args:
        prompt: A detailed description of the image to generate.
    Returns:
        A dictionary containing the image URL.
    """
    print(f"🎨 [IMAGE TOOL] Generating: {prompt}")
    
    # URL encode the prompt taake spaces aur special characters masla na karein
    encoded_prompt = urllib.parse.quote(prompt)
    
    # Pollinations AI URL
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
    
    # AI ko hamesha dictionary return karein
    return {"url": image_url}