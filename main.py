import os
import io
import traceback
import requests
from aiohttp import web

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext
)
from botbuilder.schema import Activity

from openai import OpenAI

from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes

import azure.cognitiveservices.speech as speechsdk

from dotenv import load_dotenv
load_dotenv()

# -----------------------------
# ENV
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VISION_ENDPOINT = os.getenv("VISION_ENDPOINT")
VISION_KEY = os.getenv("VISION_KEY")
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

# ⚠️ TEST MODE: disable auth for debugging
APP_ID = ""
APP_PASSWORD = ""

# -----------------------------
# CLIENTS
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

vision_client = ComputerVisionClient(
    VISION_ENDPOINT,
    CognitiveServicesCredentials(VISION_KEY)
)

# -----------------------------
# BOT ADAPTER (DEBUG MODE)
# -----------------------------
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

async def on_error(context: TurnContext, error: Exception):
    print("❌ ADAPTER ERROR:")
    traceback.print_exc()
    await context.send_activity("⚠️ Bot error occurred")

adapter.on_turn_error = on_error

# -----------------------------
# GPT
# -----------------------------
def get_gpt_response(prompt):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a food assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return res.choices[0].message.content
    except Exception as e:
        print("GPT ERROR:", e)
        return "GPT failed"

# -----------------------------
# BOT LOGIC (DEBUG HEAVY)
# -----------------------------
async def bot_logic(turn_context: TurnContext):
    print("\n🔥 BOT_LOGIC TRIGGERED")
    print("👉 Activity:", turn_context.activity.text)

    try:
        activity = turn_context.activity

        reply = "default reply"

        if activity.attachments:
            print("📎 Attachment received")

        else:
            user_text = activity.text
            print("💬 User text:", user_text)

            if not user_text:
                reply = "No input received"
            else:
                prompt = f"Suggest 3 foods for: {user_text}"
                reply = get_gpt_response(prompt)

        print("📤 Sending reply...")
        await turn_context.send_activity(reply)
        print("✅ Reply sent")

    except Exception as e:
        print("❌ BOT LOGIC ERROR:")
        traceback.print_exc()
        await turn_context.send_activity("Error in bot logic")

# -----------------------------
# ROUTES
# -----------------------------
async def messages(req: web.Request):
    print("\n📩 REQUEST RECEIVED")

    try:
        body = await req.json()
        print("📦 Payload:", body)

        activity = Activity().deserialize(body)
        auth_header = req.headers.get("Authorization", "")

        print("🔐 Auth header:", auth_header)

        await adapter.process_activity(activity, auth_header, bot_logic)

        print("✅ process_activity completed")

        return web.Response(status=201)

    except Exception as e:
        print("❌ REQUEST ERROR:")
        traceback.print_exc()
        return web.Response(text=str(e), status=500)

async def home(req):
    return web.Response(text="✅ BOT RUNNING (DEBUG MODE)")

# -----------------------------
# APP
# -----------------------------
app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/", home)

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("WEBSITES_PORT", 8000))
    print(f"🚀 Starting bot on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)
