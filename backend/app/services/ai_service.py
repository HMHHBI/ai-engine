from app.core.config import settings
from app.services.providers.gemini_provider import GeminiProvider
from app.services.cache.memory_cache import MemoryCache
from app.services.rate_limit.memory_rate_limiter import MemoryRateLimiter

class AIService:
    def __init__(self):
        self.provider = GeminiProvider(settings.GEMINI_API_KEY)
        self.cache = MemoryCache()
        self.rate_limiter = MemoryRateLimiter()
        

    # -------------------------
    # FALLBACK
    # -------------------------
    def _fallback(self):
        return random.choice([
            "AI is busy, please try again.",
            "Temporary issue, retry in a moment.",
            "Couldn't process your request right now."
        ])
    
    # -------------------------
    # MOCK Response
    # -------------------------
    def _mock_response(self, prompt):
        return f"""Here's a clear answer:
        To make a delicious cake, first decide based on your mood:

        • Chocolate cake → rich and popular  
        • Cream cake → soft and light  
        • Cheese cake → smooth and premium  

        Basic steps:
        1. Mix flour, sugar, eggs, and butter  
        2. Add flavor (chocolate/cheese/cream)  
        3. Bake at 180°C for 30–40 minutes  
        4. Let it cool and decorate  

        Tip: Always use fresh ingredients for better taste.
        """

    # -------------------------
    # MAIN FUNCTION (MERGED)
    # -------------------------
    def process_request(self, user_id, prompt, history=None, file_context="", image_data=None, task="general"):

        # 1. RATE LIMIT
        if not self.rate_limiter.allow(user_id):
            return "⚠️ Too many requests. Try later."

        # 2. SYSTEM INSTRUCTIONS
        system_instructions = {
            "email": "You are a professional email writer.",
            "blog": "You are a blog writer.",
            "code": "You are a senior software engineer.",
            "general": "You are a helpful assistant."
        }

        instruction = system_instructions.get(task, system_instructions["general"])

        # 3. LIMIT HISTORY
        if not history:
            history = []
        else:
            history = history[-8:]
            
        # 4. CACHE
        cache_key = f"{user_id}:{prompt}:{task}:{len(history)}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        history_text = ""
        if file_context:
            history_text += f"DOCUMENT CONTEXT: {file_context}\n"

        for msg in history:
            history_text += f"{msg.role.upper()}: {msg.content}\n"

        # 5. BUILD CONTENT
        contents = [{
            "role": "user",
            "parts": [{
                "text": f"{instruction}\n\n{history_text}\n\nUser: {prompt}"
            }]
        }]

        # 6. IMAGE SUPPORT
        if image_data and isinstance(image_data, list):
            image_parts = []
            for img in image_data:
                image_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": img
                    }
                })

            image_parts.append({"text": f"Current Question: {prompt if prompt else 'Explain these images.'}"})
            contents = [{"role": "user", "parts": image_parts}]

        # 7. CALL AI
        result = self.provider.generate(contents)

        # 8. FALLBACK
        if not result:
            result = self._mock_response(prompt)

        # 9. CACHE SAVE
        self.cache.set(cache_key, result)

        return result

    # -------------------------
    # TITLE GENERATION
    # -------------------------
    def generate_chat_title(self, prompt: str):
        result = self.provider.generate_title(prompt)
        return result if result else prompt[:25] + "..."