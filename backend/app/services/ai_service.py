import random
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
    # HELPER: SMART CHUNKING (Naya Function)
    # -------------------------
    def get_relevant_context(self, question, full_text, chunk_size=3000):
        if not full_text:
            return ""
    
        # 1. User ke sawal ko saaf karein aur chote words (the, what, is) nikaal dein
        ignore_words = {"what", "is", "the", "according", "to", "document", "framework", "of"}
        keywords = [word.lower().strip("?,.") for word in question.split() 
                if word.lower() not in ignore_words and len(word) > 2]
    
        # Agar koi keyword nahi mila (e.g. user sifr "Hi" kahe), toh pehla chunk bhej dein
        if not keywords:
            return full_text[:chunk_size]

        # 2. Text ko chunks mein split karein
        chunks = [full_text[i:i + chunk_size] for i in range(0, len(full_text), chunk_size)]
    
        scored_chunks = []
        for chunk in chunks:
            chunk_lower = chunk.lower()
            # Score calculation: Kitne keywords match ho rahe hain
            score = sum(1 for kw in keywords if kw in chunk_lower)
            scored_chunks.append((score, chunk))
    
        # 3. Sort by score and pick top chunks
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
    
        # Sifr woh chunks jin ka score > 0 ho
        relevant = [c[1] for c in scored_chunks[:3] if c[0] > 0]
    
        # 🛑 Crucial Fix: Agar koi match na miley toh pehle 2 chunks (Intro/Table of Contents) bhej dein
        if not relevant:
            return "\n---\n".join(chunks[:2])
        
        return "\n---\n".join(relevant)

    def _fallback(self):
        return random.choice([
            "AI is busy, please try again.",
            "Temporary issue, retry in a moment.",
            "Couldn't process your request right now."
        ])
    
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
    # MAIN FUNCTION (UPDATED)
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

        # 3. LIMIT & PROCESS HISTORY
        processed_history = ""
        if history:
            limited_history = history[-4:]
            for msg in limited_history:
                if isinstance(msg, str):
                    processed_history += f"USER: {msg}\n"
                else:
                    role = getattr(msg, 'role', 'user').upper()
                    content = getattr(msg, 'content', str(msg))
                    if "app.db.models" not in content: # Clean junk
                        processed_history += f"{role}: {content}\n"
                
        # 4. SMART PDF CONTEXT (UPDATED LOGIC)
        # Ab hum poora text bhejney ke bajaye sirf relevant chunk nikal rahe hain
        relevant_context = self.get_relevant_context(prompt, file_context)
            
        # 5. CACHE
        cache_key = f"{user_id}:{prompt}:{task}:{len(history or [])}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # 6. BUILD CONTENT (Strict Context)
        combined_text = f"""
        {instruction}
    
        CRITICAL RULES:
        1. Use the [DOCUMENT CONTEXT] below to answer the user.
        2. If the answer isn't there, say you can't find it in the document.
        3. Keep it professional and concise.

        [DOCUMENT CONTEXT]:
        {relevant_context}

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
                    image_parts.append({"text": f"[Referencing image]: {img}"})
                else:
                    image_parts.append({
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": img
                        }
                    })
            image_parts.append({"text": f"Question based on doc and images: {prompt}"})
            contents = [{"role": "user", "parts": image_parts}]

        # 8. CALL AI
        try:
            # Debugging logs terminal mein dekhne ke liye
            print(f"DEBUG - Full Context Size: {len(file_context)} chars")
            print(f"DEBUG - Sent Context Size: {len(relevant_context)} chars")
            
            result = self.provider.generate(contents)
            if not result:
                result = self._mock_response(prompt)
        
            self.cache.set(cache_key, result)
            return result
        except Exception as e:
            print(f"AI Service Error: {e}")
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                return "🕒 Quota exhausted. Please wait a few seconds."
            return "❌ AI is currently unavailable."
        
    # -------------------------
    # TITLE GENERATION
    # -------------------------
    def generate_chat_title(self, prompt: str):
        result = self.provider.generate_title(prompt)
        return result if result else prompt[:25] + "..."