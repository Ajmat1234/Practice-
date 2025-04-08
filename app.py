from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai
import os
import asyncio

app = FastAPI()

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

class Message(BaseModel):
    message: str

@app.post("/chat")
async def chat(msg: Message):
    try:
        response = await asyncio.wait_for(
            openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": msg.message}]
            ),
            timeout=55  # Increased timeout
        )
        reply = response.choices[0].message.content.strip()
        return {"reply": reply}
    except asyncio.TimeoutError:
        return {"reply": "सर्वर बहुत व्यस्त है। कृपया थोड़ी देर बाद प्रयास करें।"}
    except Exception as e:
        return {"reply": f"त्रुटि: {str(e)}"}

# Dummy call endpoint
@app.get("/ping")
def ping():
    return {"status": "awake"}
