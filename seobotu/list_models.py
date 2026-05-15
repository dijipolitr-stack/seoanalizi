from google import genai
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)
models = client.models.list_models()
for m in models:
    if "generateContent" in m.supported_actions:
        print(m.name)
