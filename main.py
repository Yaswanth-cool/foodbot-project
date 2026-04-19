import os
import io
import traceback
import tempfile
import requests
from aiohttp import web

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext
)
from botbuilder.schema import Activity

from openai import OpenAI
from dotenv import load_dotenv

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ⚠️ Disabled for Emulator + Azure App Service demo mode
APP_ID = ""
APP_PASSWORD = ""

VISION_ENDPOINT = os.getenv("VISION_ENDPOINT")
VISION_KEY = os.getenv("VISION_KEY")
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

# -----------------------------
# CLIENTS
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# VISION CLIENT
# -----------------------------
vision_client = None
if VISION_ENDPOINT and VISION_KEY:
    from azure.cognitiveservices.vision.computervision import ComputerVisionClient
    from msrest.authentication import CognitiveServicesCredentials

    vision_client = ComputerVisionClient(
        VISION_ENDPOINT,
        CognitiveServicesCredentials(VISION_KEY)
    )

# -----------------------------
# SPEECH CLIENT
# -----------------------------
speechsdk = None
speech_config = None

if SPEECH_KEY and SPEECH_REGION:
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(
        subscription=SPEECH_KEY,
        region=SPEECH_REGION
    )

# -----------------------------
# BOT ADAPTER
# -----------------------------
adapter = BotFrameworkAdapter(
    BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
)

async def on_error(context: TurnContext, error: Exception):
    print("\n❌ BOT ERROR:")
    traceback.print_exc()
    await context.send_activity("⚠️ Bot error occurred.")

adapter.on_turn_error = on_error

# -----------------------------
# GPT FUNCTION
# -----------------------------
def get_gpt_response(prompt: str) -> str:
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a multimodal food recommendation assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return res.choices[0].message.content
    except Exception as e:
        print("GPT ERROR:", e)
        return "GPT failed."

# -----------------------------
# BOT LOGIC
# -----------------------------
async def bot_logic(turn_context: TurnContext):
    try:
        activity = turn_context.activity
        text = activity.text or ""

        print("\n🔥 USER MESSAGE:", text)

        reply = ""

        # =========================
        # ATTACHMENT HANDLING
        # =========================
        if activity.attachments:

            attachment = activity.attachments[0]
            content_type = attachment.content_type
            url = attachment.content_url

            print("📎 Attachment:", content_type)

            file_data = requests.get(url).content

            # =========================
            # 🖼 IMAGE HANDLING
            # =========================
            if "image" in content_type and vision_client:
                image_stream = io.BytesIO(file_data)

                result = vision_client.analyze_image_in_stream(
                    image_stream,
                    visual_features=["Tags"]
                )

                tags = [t.name for t in result.tags]

                prompt = f"Food image detected with tags: {tags}. Suggest 3 food items."

                reply = get_gpt_response(prompt)

            # =========================
            # 🎤 AUDIO HANDLING (FIXED)
            # =========================
            elif ("audio" in content_type or "wav" in content_type) and speech_config:
                try:
                    print("🎤 Processing audio...")

                    # Safe temp file (Azure + local)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                        temp_audio.write(file_data)
                        temp_audio_path = temp_audio.name

                    # Force proper config
                    audio_input = speechsdk.AudioConfig(filename=temp_audio_path)

                    recognizer = speechsdk.SpeechRecognizer(
                        speech_config=speech_config,
                        audio_config=audio_input
                    )

                    result = recognizer.recognize_once()

                    print("🎧 Speech result:", result.reason)

                    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                        transcript = result.text
                        print("📝 Transcript:", transcript)

                        prompt = f"User said: {transcript}. Suggest 3 food items."

                        reply = get_gpt_response(prompt)

                    elif result.reason == speechsdk.ResultReason.NoMatch:
                        reply = "Could not understand the audio clearly."

                    else:
                        reply = f"Speech recognition failed: {result.reason}"

                except Exception as e:
                    print("❌ SPEECH ERROR:", e)
                    reply = "Error processing audio input."

            else:
                reply = "Unsupported attachment type."

        # =========================
        # TEXT INPUT
        # =========================
        else:
            if not text:
                reply = "Send text, image, or audio 🍔"
            else:
                prompt = f"Suggest 3 food items for: {text}"
                reply = get_gpt_response(prompt)

        print("📤 BOT RESPONSE:", reply)
        await turn_context.send_activity(reply)

    except Exception:
        print("\n❌ BOT LOGIC ERROR:")
        traceback.print_exc()
        await turn_context.send_activity("Error in bot logic.")

# -----------------------------
# ENDPOINT
# -----------------------------
async def messages(req: web.Request):
    try:
        body = await req.json()
        activity = Activity().deserialize(body)

        auth_header = req.headers.get("Authorization", "")

        await adapter.process_activity(activity, auth_header, bot_logic)

        return web.Response(status=200)

    except Exception:
        traceback.print_exc()
        return web.Response(status=500)

# -------------------------
# HEALTH CHECK
# --------------------------
async def health(req):
    return web.Response(text="✅ Multimodal Food Bot Running")

# -----------------------------
# APP
# -----------------------------
app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/", health)

# -----------------------------
# RUN (LOCAL + AZURE APP SERVICE)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Running on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)
