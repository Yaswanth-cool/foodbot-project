import os
import io
import requests
from aiohttp import web

# Bot Framework
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext
)
from botbuilder.schema import Activity

# OpenAI
from openai import OpenAI

# Azure Vision
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes

# Azure Speech
import azure.cognitiveservices.speech as speechsdk

from dotenv import load_dotenv
load_dotenv()

# -----------------------------
# ENV VARIABLES
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VISION_ENDPOINT = os.getenv("VISION_ENDPOINT")
VISION_KEY = os.getenv("VISION_KEY")
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")
TENANT_ID = os.getenv("MicrosoftAppTenantId", "")

# -----------------------------
# CLIENTS
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

vision_client = ComputerVisionClient(
    VISION_ENDPOINT,
    CognitiveServicesCredentials(VISION_KEY)
)

# -----------------------------
# BOT ADAPTER
# -----------------------------
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

# -----------------------------
# ERROR HANDLING
# -----------------------------
async def on_error(context: TurnContext, error: Exception):
    print(f"[ERROR] {error}")
    await context.send_activity("⚠️ Something went wrong. Please try again.")

adapter.on_turn_error = on_error

# -----------------------------
# HELPER: GPT CALL
# -----------------------------
def get_gpt_response(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a food recommendation assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print("GPT ERROR:", e)
        return "Error generating recommendations."

# -----------------------------
# BOT LOGIC
# -----------------------------
async def bot_logic(turn_context: TurnContext):
    print("🔥 MESSAGE RECEIVED")

    try:
        activity = turn_context.activity

        # ==========================
        # ATTACHMENT HANDLING
        # ==========================
        if activity.attachments:
            attachment = activity.attachments[0]
            content_type = attachment.content_type
            file_url = attachment.content_url

            print("Received attachment:", content_type)

            # Download file safely
            try:
                file_data = requests.get(file_url, timeout=10).content
            except Exception as e:
                print("Download error:", e)
                await turn_context.send_activity("Failed to download file.")
                return

            # ==========================
            # 🎤 AUDIO HANDLING
            # ==========================
            if "audio" in content_type or "ogg" in content_type:
                try:
                    audio_path = "temp_audio.ogg"

                    with open(audio_path, "wb") as f:
                        f.write(file_data)

                    speech_config = speechsdk.SpeechConfig(
                        subscription=SPEECH_KEY,
                        region=SPEECH_REGION
                    )

                    audio_input = speechsdk.AudioConfig(filename=audio_path)

                    recognizer = speechsdk.SpeechRecognizer(
                        speech_config=speech_config,
                        audio_config=audio_input
                    )

                    result = recognizer.recognize_once()

                    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                        user_text = result.text
                        print("Transcribed:", user_text)

                        prompt = f"""
                        User said: {user_text}

                        Suggest 3 food items with:
                        - name
                        - cuisine
                        - price
                        - reason
                        """

                        reply = f"🎤 You said: {user_text}\n\n"
                        reply += get_gpt_response(prompt)

                    else:
                        reply = "❌ Could not recognize speech."

                except Exception as e:
                    print("Speech error:", e)
                    reply = "Error processing audio."

            # ==========================
            # 🖼️ IMAGE HANDLING
            # ==========================
            elif "image" in content_type:
                try:
                    image_stream = io.BytesIO(file_data)

                    result = vision_client.analyze_image_in_stream(
                        image_stream,
                        visual_features=[VisualFeatureTypes.tags]
                    )

                    tags = [tag.name.lower() for tag in result.tags]
                    print("Image tags:", tags)

                    prompt = f"""
                    Food image detected with tags: {tags}

                    Suggest 3 food items with:
                    - name
                    - cuisine
                    - price
                    - reason
                    """

                    reply = get_gpt_response(prompt)

                except Exception as e:
                    print("Vision error:", e)
                    reply = "Error analyzing image."

            else:
                reply = "Unsupported file type."

        # ==========================
        # TEXT HANDLING
        # ==========================
        else:
            user_text = activity.text

            if not user_text:
                await turn_context.send_activity("Please send a message.")
                return

            prompt = f"""
            User query: {user_text}

            Suggest 3 food items with:
            - name
            - cuisine
            - price
            - reason
            """

            reply = get_gpt_response(prompt)

    except Exception as e:
        print("BOT ERROR:", e)
        reply = "Unexpected error occurred."

    await turn_context.send_activity(reply)

# -----------------------------
# ROUTES
# -----------------------------
async def messages(req: web.Request):
    if "application/json" not in req.headers.get("Content-Type", ""):
        return web.Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    await adapter.process_activity(activity, auth_header, bot_logic)
    return web.Response(status=201)

async def home(req):
    return web.Response(text="✅ Food Bot Running!")

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
    port = int(os.environ.get("PORT", 8000))
    web.run_app(app, host="0.0.0.0", port=port)
