import os
import traceback
from aiohttp import web

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext
)
from botbuilder.schema import Activity

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# ENV
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

APP_ID = os.getenv("MicrosoftAppId", "")
APP_PASSWORD = os.getenv("MicrosoftAppPassword", "")

# -----------------------------
# 🔍 STARTUP DEBUG CHECK (IMPORTANT)
# -----------------------------
print("==== BOT ENV CHECK ====")
print("MicrosoftAppId:", APP_ID if APP_ID else "❌ MISSING")
print("MicrosoftAppPassword exists:", bool(APP_PASSWORD))
print("PORT:", os.getenv("PORT"))

# Fail fast if misconfigured (VERY IMPORTANT for Azure debugging)
if not APP_ID or not APP_PASSWORD:
    print("❌ BOT CONFIG ERROR: Missing MicrosoftAppId or MicrosoftAppPassword")

# -----------------------------
# CLIENT
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# ADAPTER
# -----------------------------
adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

async def on_error(context: TurnContext, error: Exception):
    print("\n❌ ADAPTER ERROR:")
    traceback.print_exc()
    await context.send_activity("⚠️ Bot encountered an error.")

adapter.on_turn_error = on_error

# -----------------------------
# GPT
# -----------------------------
def get_gpt_response(prompt):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a food recommendation bot."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return res.choices[0].message.content
    except Exception as e:
        print("GPT ERROR:", e)
        return "Failed to generate response."

# -----------------------------
# BOT LOGIC
# -----------------------------
async def bot_logic(turn_context: TurnContext):
    try:
        activity = turn_context.activity
        user_text = activity.text or ""

        print("\n🔥 BOT TURN")
        print("User:", user_text)

        if not user_text:
            reply = "Send me a food request 😊"
        else:
            reply = get_gpt_response(f"Suggest 3 foods for: {user_text}")

        print("📤 Reply:", reply)
        await turn_context.send_activity(reply)

    except Exception:
        print("\n❌ BOT LOGIC ERROR:")
        traceback.print_exc()
        await turn_context.send_activity("Error in bot logic")

# -----------------------------
# HTTP ROUTE
# -----------------------------
async def messages(req: web.Request):
    try:
        print("\n📩 Incoming request")

        body = await req.json()
        activity = Activity().deserialize(body)

        auth_header = req.headers.get("Authorization", "")

        print("🔐 Auth header exists:", bool(auth_header))

        await adapter.process_activity(activity, auth_header, bot_logic)

        return web.Response(status=201)

    except Exception:
        print("\n❌ REQUEST ERROR:")
        traceback.print_exc()
        return web.Response(status=500)

# -----------------------------
# HEALTH CHECK
# -----------------------------
async def health(req):
    return web.Response(text="BOT RUNNING")

# -----------------------------
# APP
# -----------------------------
app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/", health)

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Running on port {port}")
    web.run_app(app, host="0.0.0.0", port=port)
