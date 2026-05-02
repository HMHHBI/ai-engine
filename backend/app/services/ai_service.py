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

        # 3. LIMIT & PROCESS HISTORY (Fixing AttributeError)
        processed_history = ""
        if history:
            # Last 8 messages pick karein
            limited_history = history[-4:]
            for msg in limited_history:
                # Check karein ke msg string hai ya object
                if isinstance(msg, str):
                    processed_history += f"USER: {msg}\n"
                else:
                    # Agar object hai toh attributes safely access karein
                    role = getattr(msg, 'role', 'user').upper()
                    content = getattr(msg, 'content', str(msg))
                    processed_history += f"{role}: {content}\n"
                
        # 4. BUILD PDF CONTEXT
        pdf_section = ""
        if file_context:
            pdf_section = f"\n[DOCUMENT CONTEXT]:\n{file_context}\n"
        short_context = file_context[:50000] if file_context else ""
            
        # 5. CACHE
        cache_key = f"{user_id}:{prompt}:{task}:{len(history or [])}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # 6. BUILD CONTENT (Gemini style)
        # Instruction + PDF + History ko combine kar rahe hain
        combined_text = f"""
        {instruction}
    
        CRITICAL RULES:
        1. Answer the USER QUESTION using ONLY the [DOCUMENT    CONTEXT] below.
        2. Ignore any technical debugging or Python objects mentioned in [CHAT HISTORY].
        3. If the answer is not in the document, say: "I'm sorry, I can't find that in the uploaded document."

        [DOCUMENT CONTEXT]:
        {short_context}

        [CHAT HISTORY]:
        {processed_history}

        USER QUESTION: {prompt}
        """

        contents = [{
            "role": "user",
            "parts": [{"text": combined_text}]
        }]

        # 7. IMAGE SUPPORT
        if image_data and isinstance(image_data, list):
            image_parts = []
            for img in image_data:
                if img.startswith('http'):
                    image_parts.append({"text": f"[Image Ref]: {img}"})
                else:
                    image_parts.append({
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": img
                        }
                    })

            image_parts.append({"text": f"Question: {prompt or 'Explain these images.'}"})
            contents = [{"role": "user", "parts": image_parts}]

         # 8. CALL AI with FALLBACK & CACHE
        try:
            # ai_service.py mein generate call se pehle:
            print(f"DEBUG - PDF Context Length: {len(file_context)}") 
            print(f"DEBUG - Combined Text: {combined_text[:500]}...") # Shuru ka thora sa text
            result = self.provider.generate(contents)
            if not result:
                result = self._mock_response(prompt)
        
            self.cache.set(cache_key, result)
            return result
        except Exception as e:
            print(f"AI Service Error: {e}")
            # Quota check ke liye specific message
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                return "🕒 Quota exhausted. Please wait a few seconds before trying again."
            return "❌ AI is currently unavailable."

    # -------------------------
    # TITLE GENERATION
    # -------------------------
    def generate_chat_title(self, prompt: str):
        result = self.provider.generate_title(prompt)
        return result if result else prompt[:25] + "..."