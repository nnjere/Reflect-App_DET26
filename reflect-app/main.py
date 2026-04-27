# ── Imports ───────────────────────────────────────────
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
import anthropic
import httpx
import os
import json

load_dotenv()

app = FastAPI()

# ── AI setup ──────────────────────────────────────────
# Change AI_MODEL here to swap to a different model anytime
ai_client = anthropic.Anthropic(api_key=os.getenv("AI_API_KEY"))
AI_MODEL = "claude-haiku-4-5-20251001"

# ── TikTok config ─────────────────────────────────────
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# ── Token store ───────────────────────────────────────
# Stores your token after you log in once
# Replaced with a database later
user_tokens = {}

# ── Section 1: Health check ───────────────────────────
@app.get("/")
def home():
    return {"status": "Reflect API is running"}

# ── Section 2: TikTok login ───────────────────────────
@app.get("/login")
def login():
    # Sends you to TikTok to approve the app
    # You only need to do this once
    tiktok_auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={TIKTOK_CLIENT_KEY}"
        f"&response_type=code"
        f"&scope=user.info.basic,user.info.profile,user.info.stats,video.list"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state=reflect_state_123"
    )
    return RedirectResponse(url=tiktok_auth_url)

# ── Section 3: TikTok callback ────────────────────────
@app.get("/callback")
async def callback(code: str, state: str = None):
    # TikTok sends you back here after you approve
    # Exchanges the code for a real access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            }
        )

    token_data = token_response.json()
    open_id = token_data.get("open_id")
    access_token = token_data.get("access_token")

    if not access_token:
        return {"error": "Token exchange failed", "details": token_data}

    # Store token in memory
    user_tokens[open_id] = access_token

    # Redirect straight to analyze
    return RedirectResponse(url=f"/analyze?open_id={open_id}")

# ── Section 4: Fetch real TikTok data ─────────────────
async def fetch_tiktok_data(open_id: str):
    token = user_tokens.get(open_id)
    if not token:
        return None

    async with httpx.AsyncClient() as client:

        # Get your profile
        user_response = await client.get(
            "https://open.tiktokapis.com/v2/user/info/",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "display_name,follower_count,video_count,like_count"}
        )

        # Get your videos
        video_response = await client.post(
            "https://open.tiktokapis.com/v2/video/list/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "max_count": 20,
                "fields": ["title", "video_description",
                          "hashtag_names", "like_count",
                          "comment_count", "share_count",
                          "view_count", "duration"]
            }
        )

    return {
        "user": user_response.json().get("data", {}).get("user", {}),
        "videos": video_response.json().get("data", {}).get("videos", [])
    }

# ── Section 5: Inference layer ────────────────────────
@app.get("/analyze")
async def analyze(open_id: str = None):

    # ── Use fake data if no open_id provided ──────────
    # This lets you test Claude without logging into TikTok
    if not open_id:
        tiktok_data = {
            "user": {"display_name": "Test User"},
            "videos": [
                {"title": "My morning routine",
                 "hashtag_names": ["wellness", "morning", "selfcare"]},
                {"title": "Stock market tips",
                 "hashtag_names": ["finance", "investing", "money"]},
                {"title": "Easy pasta recipe",
                 "hashtag_names": ["cooking", "food", "recipe"]},
                {"title": "Political news breakdown",
                 "hashtag_names": ["news", "politics", "trending"]},
                {"title": "Home workout no equipment",
                 "hashtag_names": ["fitness", "workout", "health"]},
                {"title": "Best investment apps 2024",
                 "hashtag_names": ["finance", "money", "apps"]},
                {"title": "What I eat in a day",
                 "hashtag_names": ["food", "wellness", "healthy"]},
                {"title": "Morning yoga flow",
                 "hashtag_names": ["yoga", "wellness", "morning"]}
            ]
        }
    else:
        # ── Use real TikTok data ───────────────────────
        tiktok_data = await fetch_tiktok_data(open_id)
        if not tiktok_data:
            return {"error": "Please login first — visit /login"}

    # ── Build video text for Claude ───────────────────
    video_texts = []
    for video in tiktok_data.get("videos", []):
        title = video.get("title", "")
        tags = " ".join(video.get("hashtag_names", []))
        desc = video.get("video_description", "")
        video_texts.append(f"Title: {title} | Tags: {tags} | Desc: {desc}")

    videos_summary = "\n".join(video_texts)

    # ── Claude prompt ─────────────────────────────────
    prompt = f"""
    Analyze these TikTok videos and identify the key content themes
    and how dominant each theme is in this person's consumption.

    Videos:
    {videos_summary}

    Return ONLY a valid JSON object, no other text, no markdown:
    {{
        "themes": [
            {{"theme": "Theme Name", "percentage": 32}},
            {{"theme": "Theme Name", "percentage": 28}}
        ],
        "total_videos_analyzed": 8,
        "summary": "One sentence describing this person's overall content diet"
    }}

    Rules:
    - Percentages must add up to exactly 100
    - Use broad readable names: Wellness, Finance, Food,
      Fitness, Politics, Entertainment, Education, Other
    - Order from highest to lowest percentage
    - Maximum 6 themes, group small ones into Other
    """

    # ── Call Claude ───────────────────────────────────
    response = ai_client.messages.create(
        model=AI_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = response.content[0].text.strip()

    # ── Parse JSON response ───────────────────────────
    try:
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        result = {"raw_response": raw_text,
                  "error": "JSON parsing failed"}

    return result