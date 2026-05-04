# ── Imports ───────────────────────────────────────────
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from dotenv import load_dotenv
import anthropic
import httpx
import os
import json
import random
from datetime import datetime

load_dotenv()

app = FastAPI()

# ── AI setup ──────────────────────────────────────────
ai_client = anthropic.Anthropic(api_key=os.getenv("AI_API_KEY"))
AI_MODEL = "claude-haiku-4-5-20251001"

# ── TikTok config ─────────────────────────────────────
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# ── Token store ───────────────────────────────────────
user_tokens = {}

# ── Pre-load dummy reports on startup ─────────────────
def preload_dummy_reports():
    personas = load_personas()
    for key, tiktok_data in personas.items():
        username = tiktok_data.get("user", {}).get("display_name", "User")
        analysis = run_inference(tiktok_data, username)
        server_reports[username] = {
            "report_id": username,
            "is_dummy": True,
            "analysis": analysis
        }
    print(f"Preloaded {len(personas)} dummy reports")

# ── Server-side report store (for ESP32 access) ───────
server_reports = {}

# ── Load personas ─────────────────────────────────────
def load_personas():
    data_path = os.path.join(
        os.path.dirname(__file__), "data", "personas.json")
    with open(data_path, "r") as f:
        return json.load(f)

# ── Section 1: Health check ───────────────────────────
@app.get("/")
def home():
    return {"status": "Reflect API is running"}

# ── Section 2: Serve report page ──────────────────────
@app.get("/report", response_class=HTMLResponse)
async def report():
    template_path = os.path.join(
        os.path.dirname(__file__), "templates", "report.html")
    with open(template_path, "r") as f:
        return f.read()

# ── Section 3: TikTok login ───────────────────────────
@app.get("/login")
def login():
    tiktok_auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={TIKTOK_CLIENT_KEY}"
        f"&response_type=code"
        f"&scope=user.info.basic,user.info.profile,user.info.stats,video.list"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state=reflect_state_123"
    )
    return RedirectResponse(url=tiktok_auth_url)

# ── Section 4: TikTok callback ────────────────────────
@app.get("/callback")
async def callback(code: str, state: str = None):
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
    user_tokens[open_id] = access_token
    return RedirectResponse(url=f"/analyze?open_id={open_id}")

# ── Section 5: Fetch real TikTok data ─────────────────
async def fetch_tiktok_data(open_id: str):
    token = user_tokens.get(open_id)
    if not token:
        return None
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://open.tiktokapis.com/v2/user/info/",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "display_name,follower_count,video_count,like_count"}
        )
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

# ── Section 6: Parse TikTok JSON ──────────────────────
def parse_tiktok_json(data: dict) -> dict:
    searches = []
    try:
        search_list = data["Your Activity"]["Searches"]["SearchList"]
        searches = [s.get("SearchTerm", "") for s in search_list
                   if s.get("SearchTerm")]
    except (KeyError, TypeError):
        searches = []

    collections = []
    try:
        col_list = data["Likes and Favorites"]["Favorite Collection"][
            "FavoriteCollectionList"]
        collections = [c.get("FavoriteCollection", "") for c in col_list
                      if c.get("FavoriteCollection")]
    except (KeyError, TypeError):
        collections = []

    watch_videos = []
    try:
        watch_videos = data["Your Activity"]["Watch History"]["VideoList"]
        if not isinstance(watch_videos, list):
            watch_videos = []
    except (KeyError, TypeError):
        watch_videos = []
    watch_count = len(watch_videos)

    like_videos = []
    try:
        raw_likes = data["Likes and Favorites"]["Like List"]["ItemFavoriteList"]
        if isinstance(raw_likes, list):
            like_videos = raw_likes
    except (KeyError, TypeError):
        like_videos = []
    like_count = len(like_videos)

    saved_videos = []
    try:
        raw_saved = data["Likes and Favorites"]["Favorite Videos"][
            "FavoriteVideoList"]
        if isinstance(raw_saved, list):
            saved_videos = raw_saved
    except (KeyError, TypeError):
        saved_videos = []
    saved_count = len(saved_videos)

    username = "User"
    region = "Unknown"
    try:
        profile = data["Profile And Settings"]["Profile Info"]["ProfileMap"]
        username = profile.get("displayName", "User")
        region = profile.get("accountRegion", "Unknown")
    except (KeyError, TypeError):
        pass

    watch_pattern = {
        "early_morning": 0, "morning": 0,
        "afternoon": 0, "evening": 0, "late_night": 0
    }
    sessions = []
    prev_time = None
    current_session = 1
    parsed_times = []

    for video in watch_videos:
        date_str = video.get("Date") or video.get("date", "")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            parsed_times.append(dt)
            hour = dt.hour
            if 5 <= hour < 8:
                watch_pattern["early_morning"] += 1
            elif 8 <= hour < 12:
                watch_pattern["morning"] += 1
            elif 12 <= hour < 17:
                watch_pattern["afternoon"] += 1
            elif 17 <= hour < 21:
                watch_pattern["evening"] += 1
            else:
                watch_pattern["late_night"] += 1
            if prev_time:
                diff = abs((dt - prev_time).total_seconds() / 60)
                if diff > 30:
                    sessions.append(current_session)
                    current_session = 1
                else:
                    current_session += 1
            prev_time = dt
        except (ValueError, TypeError):
            continue

    if current_session > 0 and parsed_times:
        sessions.append(current_session)

    total_timed = sum(watch_pattern.values())
    if total_timed > 0:
        watch_pattern = {
            k: round((v / total_timed) * 100)
            for k, v in watch_pattern.items()
        }

    avg_session = round(sum(sessions) / len(sessions)) if sessions else 0
    num_sessions = len(sessions)
    like_rate = round((like_count / watch_count) * 100) if watch_count > 0 else 0
    save_rate = round((saved_count / watch_count) * 100) if watch_count > 0 else 0
    peak_hours = max(watch_pattern, key=watch_pattern.get) if total_timed > 0 else "unknown"

    devices = set()
    networks = set()
    try:
        logins = data["Your Activity"]["Login History"]["LoginHistoryList"]
        for login in logins:
            model = login.get("DeviceModel", "")
            network = login.get("NetworkType", "")
            if model:
                devices.add(model)
            if network:
                networks.add(network)
    except (KeyError, TypeError):
        pass

    return {
        "username": username, "region": region,
        "watch_count": watch_count, "like_count": like_count,
        "saved_count": saved_count, "searches": searches,
        "collections": collections, "watch_pattern": watch_pattern,
        "peak_hours": peak_hours, "avg_session_videos": avg_session,
        "num_sessions": num_sessions, "like_rate": like_rate,
        "save_rate": save_rate, "devices": list(devices),
        "networks": list(networks)
    }

# ── Section 7: Build prompt and run inference ──────────
def build_prompt(tiktok_data: dict, username: str) -> str:
    video_texts = []
    for video in tiktok_data.get("videos", []):
        title = video.get("title", "")
        tags = " ".join(video.get("hashtag_names", []))
        creator = video.get("creator", "unknown")
        watch = video.get("watch_time", 0)
        duration = video.get("duration", 0)
        completion = round((watch / duration * 100) if duration > 0 else 0)
        video_texts.append(
            f"Title: {title} | Tags: {tags} | "
            f"Creator: {creator} | Completion: {completion}%"
        )
    videos_summary = "\n".join(video_texts)

    return f"""
    You are analyzing {username}'s TikTok consumption for Reflect.

    Videos:
    {videos_summary}

    Return ONLY valid JSON, no markdown:
    {{
        "user": {{
            "name": "{username}",
            "overall_label": "Diverse/Balanced/Siloed/Polarized",
            "overall_summary": "2 sentences about their media diet"
        }},
        "thematic_analysis": {{
            "total_videos_analyzed": {len(tiktok_data.get("videos", []))},
            "themes": [
                {{
                    "theme": "Theme Name",
                    "percentage": 30,
                    "engagement_level": "High/Medium/Low",
                    "consumption_type": "Active/Passive"
                }}
            ],
            "dominant_theme": "Single most watched theme name only — no secondary themes",
            "theme_summary": "One sentence about themes"
        }},
        "dimensionality_analysis": {{
            "polarity": {{
                "score": 7,
                "label": "Mostly Balanced",
                "breakdown": {{"neutral": 60, "positive": 30, "negative": 10}},
                "summary": "One sentence about polarity"
            }},
            "emotional_tone": {{
                "score": 6,
                "label": "Mostly Positive",
                "breakdown": {{"positive": 65, "neutral": 28, "polarizing": 7}},
                "summary": "One sentence about emotional tone"
            }},
            "echo_chamber": {{
                "score": 7,
                "label": "Low Risk",
                "signal_percentage": 24,
                "breakdown": {{"unique_sources": 78, "repeated_themes": 22}},
                "key_themes": ["Theme1", "Theme2", "Theme3"],
                "summary": "One sentence about echo chamber risk"
            }}
        }},
        "print_summary": {{
            "headline": "Short punchy headline",
            "line1": "Key insight about themes",
            "line2": "Key insight about emotional tone",
            "line3": "Key insight about echo chamber",
            "recommendation": "One actionable recommendation"
        }}
    }}

    Rules: percentages add to 100, max 6 themes, order highest to lowest.
    """

def run_inference(tiktok_data: dict, username: str) -> dict:
    prompt = build_prompt(tiktok_data, username)
    response = ai_client.messages.create(
        model=AI_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.content[0].text.strip()
    try:
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"raw_response": raw_text, "error": "JSON parsing failed"}

# ── Section 8: Dummy endpoint ─────────────────────────
@app.get("/dummy")
async def dummy(persona: str = "diverse"):
    personas = load_personas()
    if persona not in personas:
        return {"error": f"Unknown persona: {persona}"}

    tiktok_data = personas[persona]
    username = tiktok_data.get("user", {}).get("display_name", "User")
    meta = tiktok_data.get("metadata", {})
    watch_count = random.randint(2000, 5000)

    data_summary = {
        "username": username,
        "region": meta.get("region", "Simulated"),
        "watch_count": watch_count,
        "like_count": meta.get("like_count", 0),
        "saved_count": meta.get("saved_count", 0),
        "collections": meta.get("collections", []),
        "top_searches": meta.get("top_searches", [])[:15],
        "watch_pattern": meta.get("watch_pattern", {}),
        "peak_hours": meta.get("peak_hours", "unknown"),
        "avg_session_videos": meta.get("avg_session_minutes", 0),
        "num_sessions": meta.get("sessions_per_day", 0),
        "like_rate": meta.get("like_rate", 0),
        "save_rate": meta.get("save_rate", 0),
        "devices": [], "networks": []
    }

    analysis = run_inference(tiktok_data, username)

    report_data = {
        "report_id": username,
        "is_dummy": True,
        "data_summary": data_summary,
        "analysis": analysis
    }

    # Save to server store for ESP32
    server_reports[username] = report_data
    return report_data

# ── Section 9: Upload JSON endpoint ───────────────────
@app.post("/upload-json")
async def upload_json(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        data = json.loads(contents)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON file"}

    parsed = parse_tiktok_json(data)

    data_summary = {
        "username": parsed["username"],
        "region": parsed["region"],
        "watch_count": parsed["watch_count"],
        "like_count": parsed["like_count"],
        "saved_count": parsed["saved_count"],
        "collections": parsed["collections"],
        "top_searches": parsed["searches"][:15],
        "watch_pattern": parsed["watch_pattern"],
        "peak_hours": parsed["peak_hours"],
        "avg_session_videos": parsed["avg_session_videos"],
        "num_sessions": parsed["num_sessions"],
        "like_rate": parsed["like_rate"],
        "save_rate": parsed["save_rate"],
        "devices": parsed["devices"],
        "networks": parsed["networks"]
    }

    searches_text = "\n".join([f"- {s}" for s in parsed["searches"]])
    collections_text = (", ".join(parsed["collections"])
                       if parsed["collections"] else "None")

    prompt = f"""
    Analyze real TikTok data for Reflect media literacy platform.

    USER SUMMARY:
    - Username: {parsed["username"]}
    - Region: {parsed["region"]}
    - Videos watched: {parsed["watch_count"]}
    - Videos liked: {parsed["like_count"]}
    - Videos saved: {parsed["saved_count"]}
    - Like rate: {parsed["like_rate"]}%
    - Save rate: {parsed["save_rate"]}%
    - Peak usage: {parsed["peak_hours"]}
    - Collections: {collections_text}

    SEARCH HISTORY:
    {searches_text}

    Return ONLY valid JSON, no markdown:
    {{
        "user": {{
            "name": "{parsed["username"]}",
            "overall_label": "Diverse/Balanced/Siloed/Polarized",
            "overall_summary": "2 honest sentences based on real data"
        }},
        "thematic_analysis": {{
            "total_videos_analyzed": {parsed["watch_count"]},
            "total_searches": {len(parsed["searches"])},
            "themes": [
                {{
                    "theme": "Theme Name",
                    "percentage": 30,
                    "evidence": "specific searches showing this",
                    "engagement_level": "High/Medium/Low",
                    "consumption_type": "Active/Passive"
                }}
            ],
            "dominant_theme": "Most searched theme",
            "theme_summary": "One sentence about themes"
        }},
        "dimensionality_analysis": {{
            "polarity": {{
                "score": 7,
                "label": "Mostly Balanced",
                "breakdown": {{"neutral": 60, "positive": 30, "negative": 10}},
                "summary": "One sentence based on real searches"
            }},
            "emotional_tone": {{
                "score": 6,
                "label": "Mostly Positive",
                "breakdown": {{"positive": 65, "neutral": 28, "polarizing": 7}},
                "summary": "One sentence based on real searches"
            }},
            "echo_chamber": {{
                "score": 7,
                "label": "Low Risk",
                "signal_percentage": 24,
                "breakdown": {{"unique_sources": 78, "repeated_themes": 22}},
                "key_themes": ["Theme1", "Theme2", "Theme3"],
                "summary": "One sentence about echo chamber risk"
            }}
        }},
        "print_summary": {{
            "headline": "Short punchy headline",
            "line1": "Key insight about themes",
            "line2": "Key insight about emotional tone",
            "line3": "Key insight about echo chamber",
            "recommendation": "One actionable recommendation"
        }}
    }}

    Be specific, reference actual searches. Theme percentages add to 100.
    """

    response = ai_client.messages.create(
        model=AI_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.content[0].text.strip()
    try:
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        analysis = json.loads(raw_text)
    except json.JSONDecodeError:
        analysis = {"raw_response": raw_text, "error": "Parsing failed"}

    report_data = {
        "report_id": parsed["username"],
        "is_dummy": False,
        "data_summary": data_summary,
        "analysis": analysis
    }

    # Save to server store for ESP32
    server_reports[parsed["username"]] = report_data
    return report_data

# ── Section 10: Blend endpoint ────────────────────────
def run_blend_inference(reports: list) -> dict:
    people_summaries = []
    for r in reports:
        name = r.get("report_id", "Unknown")
        analysis = r.get("analysis", {})
        themes = analysis.get("thematic_analysis", {})
        dims = analysis.get("dimensionality_analysis", {})
        summary = r.get("data_summary", {})
        theme_list = ", ".join([
            f"{t['theme']} ({t['percentage']}%)"
            for t in themes.get("themes", [])[:4]
        ])
        people_summaries.append(f"""
        Person: {name}
        Overall label: {analysis.get("user", {}).get("overall_label", "")}
        Dominant theme: {themes.get("dominant_theme", "")}
        Top themes: {theme_list}
        Polarity score: {dims.get("polarity", {}).get("score", 0)}/10
        Emotional tone score: {dims.get("emotional_tone", {}).get("score", 0)}/10
        Echo chamber score: {dims.get("echo_chamber", {}).get("score", 0)}/10
        Peak usage: {summary.get("peak_hours", "")}
        Like rate: {summary.get("like_rate", 0)}%
        """)

    people_text = "\n---\n".join(people_summaries)
    names = [r.get("report_id", "Unknown") for r in reports]
    names_str = ", ".join(names)

    prompt = f"""
    You are analyzing the media consumption patterns of a group of people
    for the Reflect media literacy platform.

    The group members are: {names_str}

    Here is each person's media profile:
    {people_text}

    Generate a group blend analysis. Return ONLY valid JSON, no markdown:
    {{
        "blend_title": "Short group name like Family, Study Group, etc",
        "group_size": {len(reports)},
        "members": {json.dumps(names)},
        "group_diversity": {{
            "label": "High Diversity/Mixed Diversity/Low Diversity",
            "score": 7,
            "summary": "One sentence about the group's overall diversity"
        }},
        "shared_themes": [
            {{"theme": "Theme Name", "percentage": 45,
              "description": "How this theme appears across members"}}
        ],
        "diverging_themes": [
            {{"theme": "Theme Name",
              "members_who_engage": ["Name1"],
              "members_who_dont": ["Name2"],
              "description": "What this divergence reveals"}}
        ],
        "member_comparisons": [
            {{
                "member_a": "Name1",
                "member_b": "Name2",
                "overlap_score": 75,
                "shared_themes": ["Theme1", "Theme2"],
                "key_difference": "One sentence about main difference"
            }}
        ],
        "closest_pair": {{
            "members": ["Name1", "Name2"],
            "overlap_score": 85,
            "reason": "Why these two align most"
        }},
        "furthest_pair": {{
            "members": ["Name1", "Name2"],
            "overlap_score": 20,
            "reason": "Why these two diverge most"
        }},
        "key_common_themes": ["Theme1", "Theme2", "Theme3", "Theme4"],
        "group_emotional_tone": {{
            "average_score": 6,
            "label": "Mixed",
            "summary": "One sentence about group emotional tone"
        }},
        "group_echo_chamber": {{
            "average_score": 5,
            "label": "Medium Risk",
            "summary": "One sentence about group echo chamber patterns"
        }},
        "group_summary": "2-3 sentences describing what makes this group
                         interesting as a collective media ecosystem",
        "print_summary": {{
            "headline": "Punchy headline for the group",
            "line1": "Key shared insight",
            "line2": "Key divergence insight",
            "line3": "Group echo chamber insight",
            "recommendation": "One recommendation for the group"
        }}
    }}

    Rules:
    - overlap_score is 0-100 where 100 = identical consumption
    - shared_themes percentages show what % of members engage with that theme
    - Be specific and honest about differences
    - Key common themes should be themes at least 2 members share
    """

    response = ai_client.messages.create(
        model=AI_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.content[0].text.strip()
    try:
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

@app.post("/blend")
async def blend(request: dict):
    reports = request.get("reports", [])
    if len(reports) < 2:
        return {"error": "Need at least 2 reports to blend"}
    if len(reports) > 6:
        return {"error": "Maximum 6 reports per blend"}
    names = [r.get("report_id", "Unknown") for r in reports]
    blend_analysis = run_blend_inference(reports)
    blend_id = "Blend_" + "_".join(names[:3])
    result = {
        "blend_id": blend_id,
        "is_blend": True,
        "members": names,
        "blend_analysis": blend_analysis
    }
    server_reports[blend_id] = result
    return result

# ── Section 11: Receipt endpoint (for ESP32) ──────────
@app.get("/receipt")
async def receipt(count: int = 1):

    def format_line(text: str, width: int = 32) -> str:
        if len(text) <= width:
            return text
        return text[:width-3] + "..."

    def center(text: str, width: int = 32) -> str:
        return text.center(width)

    def divider(char: str = "-", width: int = 32) -> str:
        return char * width

    def wrap(text: str, width: int = 32) -> str:
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= width:
                current += (" " if current else "") + word
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return "\n".join(lines)

    available = list(server_reports.values())

    if not available:
        # Generate a fresh dummy report if none saved
        personas = load_personas()
        persona_key = random.choice(list(personas.keys()))
        tiktok_data = personas[persona_key]
        username = tiktok_data.get(
            "user", {}).get("display_name", "User")
        analysis = run_inference(tiktok_data, username)
        available = [{"report_id": username,
                     "is_dummy": True,
                     "analysis": analysis}]

    lines = []
    lines.append(center("* R E F L E C T *"))
    lines.append(center("Media Consumption Report"))
    lines.append(divider())
    lines.append(center(datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines.append(divider())

    if count == 1:
        # Single report — pick a real one preferably
        real_reports = [r for r in available if not r.get("is_dummy")]
        pool = real_reports if real_reports else available
        chosen = random.choice(pool)

        analysis = chosen.get("analysis", {})
        user = analysis.get("user", {})
        themes = analysis.get("thematic_analysis", {})
        dims = analysis.get("dimensionality_analysis", {})
        print_s = analysis.get("print_summary", {})

        lines.append(center(chosen.get("report_id", "User")))
        lines.append(center(user.get("overall_label", "").upper()))
        lines.append(divider())

        lines.append("CONTENT THEMES")
        for t in themes.get("themes", [])[:4]:
            name = t.get("theme", "")
            pct = t.get("percentage", 0)
            bar_len = round(pct / 5)
            bar = "█" * bar_len
            lines.append(f"{name[:14]:<14} {pct:>3}% {bar}")

        lines.append(divider())
        lines.append("SCORES")
        pol = dims.get("polarity", {})
        emo = dims.get("emotional_tone", {})
        echo = dims.get("echo_chamber", {})
        lines.append(f"Polarity      {pol.get('score', 0)}/10")
        lines.append(f"Emotional     {emo.get('score', 0)}/10")
        lines.append(f"Diversity     {echo.get('score', 0)}/10")

        lines.append(divider())
        lines.append("INSIGHT")
        lines.append(wrap(print_s.get("headline", "")))
        lines.append("")
        lines.append(wrap(print_s.get("line1", "")))
        lines.append(wrap(print_s.get("line2", "")))
        lines.append(wrap(print_s.get("line3", "")))

        lines.append(divider())
        lines.append("RECOMMENDATION")
        lines.append(wrap(print_s.get("recommendation", "")))

    else:
        # Blended report — pick N random reports
        count = min(count, len(available), 6)
        chosen = random.sample(available, count)

        # Build blend on the fly
        blend_result = await blend({"reports": chosen})
        blend_analysis = blend_result.get("blend_analysis", {})
        names = blend_result.get("members", [])
        print_s = blend_analysis.get("print_summary", {})

        lines.append(center("GROUP BLEND"))
        lines.append(center(f"{count} People"))
        lines.append(divider())

        lines.append("MEMBERS")
        for name in names:
            lines.append(f"  {format_line(name, 30)}")

        lines.append(divider())
        div = blend_analysis.get("group_diversity", {})
        lines.append(f"Group: {div.get('label', '')}")
        lines.append(wrap(div.get("summary", "")))

        lines.append(divider())
        lines.append("SHARED THEMES")
        for t in blend_analysis.get("key_common_themes", [])[:5]:
            lines.append(f"  + {t}")

        lines.append(divider())
        cp = blend_analysis.get("closest_pair", {})
        fp = blend_analysis.get("furthest_pair", {})
        if cp.get("members"):
            lines.append("MOST ALIGNED")
            lines.append(
                f"  {cp['members'][0]} & {cp['members'][1]}")
            lines.append(wrap(cp.get("reason", ""), 30))

        if fp.get("members"):
            lines.append("MOST DIFFERENT")
            lines.append(
                f"  {fp['members'][0]} & {fp['members'][1]}")
            lines.append(wrap(fp.get("reason", ""), 30))

        lines.append(divider())
        lines.append("GROUP INSIGHT")
        lines.append(wrap(print_s.get("headline", "")))
        lines.append("")
        lines.append(wrap(print_s.get("line1", "")))
        lines.append(wrap(print_s.get("line2", "")))
        lines.append(wrap(print_s.get("recommendation", "")))

    lines.append(divider("="))
    lines.append(center("reflect.app"))
    lines.append(center("know your feed"))
    lines.append("")
    lines.append("")
    lines.append("")

    return PlainTextResponse("\n".join(lines))

    # ── Section 11: Receipt endpoints ─────────────────────
from receipt_formatter import format_individual, format_blend

@app.post("/receipt/individual")
async def receipt_individual(request: Request):
    body = await request.json()
    report = body.get("report")
    if not report:
        return PlainTextResponse("No report data provided.")
    return PlainTextResponse(format_individual(report))

@app.post("/receipt/blend")
async def receipt_blend(request: Request):
    body = await request.json()
    reports_data = body.get("reports", [])
    if len(reports_data) < 2:
        return PlainTextResponse("Need at least 2 reports.")

    # Re-run blend to get fresh analysis
    from main import run_blend_inference
    blend_data = run_blend_inference(reports_data)
    return PlainTextResponse(format_blend(blend_data, reports_data))

@app.get("/receipt/print")
async def receipt_print(count: int = 1):
    import random

    # ── Priority 1: real reports first ────────────────
    real = [r for r in server_reports.values() if not r.get("is_dummy")]
    dummy_pool = [r for r in server_reports.values() if r.get("is_dummy")]

    selected = []

    if len(real) >= count:
        # Enough real reports to fill the request
        selected = random.sample(real, count)

    elif len(real) > 0:
        # Use all real reports, fill remainder with saved dummies
        selected = real.copy()
        needed = count - len(real)
        selected += random.sample(dummy_pool, min(needed, len(dummy_pool)))

    else:
        # No real reports — select from saved dummy pool only
        if len(dummy_pool) == 0:
            return PlainTextResponse(
                "No reports available — generate some reports first at /report")
        selected = random.sample(dummy_pool, min(count, len(dummy_pool)))

    # ── Format and return ──────────────────────────────
    if len(selected) == 1:
        return PlainTextResponse(format_individual(selected[0]))

    blend_data = run_blend_inference(selected)
    return PlainTextResponse(format_blend(blend_data, selected))
    
@app.on_event("startup")
async def startup_event():
    preload_dummy_reports()