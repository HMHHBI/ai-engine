import os, re, urllib.parse
from google import genai
from app.core.config import settings
from app.utils.search_tool import get_web_search
from app.utils.image_tool import generate_image

class AIService:
    def __init__(self):
        # Settings se API key uthayen
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.tools_list = [get_web_search, generate_image]

    def generate_chat_title(self, prompt: str): # Title generation method
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=f"Create a short (max 3-4 words) title for a chat starting with: '{prompt}'. Only text."
            )
            return response.text.strip().replace('"', '')
        except:
            return prompt[:25] + "..."

    def process_request(self, prompt: str, history=[], file_context="", image_data=None, task="general"):
        # """
        # Ye main function hai jo chat.py call karega.
        # """
        # prompt_lower = prompt.lower()
        
        # # 1. Image Generation Logic (Fast Bypass)
        # if "image" in prompt_lower or "generate" in prompt_lower:
        #     enhanced = f"Professional photography, high detail, 8k resolution, cinematic lighting, {prompt}"
        #     clean = re.sub(r'[^a-zA-Z0-9\s]', '', enhanced)
        #     encoded = urllib.parse.quote(clean)
        #     return f"![generated_image](https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&model=flux)"

        # 2. System Instructions
        system_instructions = {
            "email": "You are a professional email writer.",
            "blog": "You are a blog writer.",
            "code": "You are a senior software engineer.",
            "general": "You are a helpful assistant who remembers chat history."
        }
        instruction = system_instructions.get(task, system_instructions["general"])
        
        # 3. Building Contents
        contents = []
        history_text = "PREVIOUS CONVERSATION HISTORY:\n"
        if file_context:
            history_text += f"DOCUMENT CONTEXT: {file_context}\n"
        
        for msg in history:
            history_text += f"{msg.role.upper()}: {msg.content}\n"
        
        contents.append({
            "role": "user", 
            "parts": [{"text": f"Instruction: {instruction}\n\n{history_text}\n\nKeep history in mind."}]
        })
        
        contents.append({
            "role": "model", 
            "parts": [{"text": "Understood. I am ready."}]
        })

        # 4. User Input (Text + Images)
        if image_data and isinstance(image_data, list):
            image_parts = []
            for img in image_data:
                image_parts.append({"inline_data": {"mime_type": "image/png", "data": img}})
            image_parts.append({"text": f"Current Question: {prompt if prompt else 'Explain these images.'}"})
            contents.append({"role": "user", "parts": image_parts})
        else:
            contents.append({"role": "user", "parts": [{"text": f"Current Question: {prompt}"}]})

        # 5. API Call
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite", # Updated to stable flash
                contents=contents
            )
            return response.text if response.text else "I couldn't generate a response."
        except Exception as e:
            if "429" in str(e):
                return "⚠️ Too many requests. Please slow down."
            return f"AI Error: {str(e)}"
