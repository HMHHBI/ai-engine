from google import genai
from google.api_core.exceptions import TooManyRequests, ResourceExhausted
import time


class GeminiProvider:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)

    def generate(self, contents):
        for i in range(2):
            try:
                res = self.client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=contents
                )

                if res.text:
                    return res.text

            except (TooManyRequests, ResourceExhausted):
                time.sleep(1.5 * (i + 1))

            except Exception as e:
                print("Gemini error:", e)
                time.sleep(1)

        return None

    def generate_title(self, prompt):
        contents = [{
            "role": "user",
            "parts": [{
                "text": f"Create a short title (3-4 words): {prompt}"
            }]
        }]
        return self.generate(contents)