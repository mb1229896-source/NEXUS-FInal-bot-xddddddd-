import discord
from discord.ext import commands
import json
import os
import random
import re
import asyncio
import io
from datetime import datetime, timedelta
try:
    import pytz
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable,"-m","pip","install","pytz","--quiet","--break-system-packages"],
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    import pytz
from dotenv import load_dotenv

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    import subprocess, sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "--quiet", "--break-system-packages"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from PIL import Image, ImageDraw, ImageFont
        PILLOW_AVAILABLE = True
        print("[INFO] Pillow auto-installed successfully.")
    except Exception:
        PILLOW_AVAILABLE = False
        print("[WARN] Pillow not available — scorecard images disabled.")

load_dotenv()

# ─────────────────────────────────────────────
# BALL ICON ASSETS (for timeline strip)
# ─────────────────────────────────────────────
import os as _os
_BALL_ICON_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "assets", "ball_icons")
_BALL_ICON_SIZE = 48

def _load_ball_icons():
    icons = {}
    if not PILLOW_AVAILABLE or not _os.path.isdir(_BALL_ICON_DIR):
        return icons
    for key in ["0","1","2","3","4","6","W","NB","WD"]:
        fname = key if key in ["0","1","2","3","4","6","W"] else "0"
        path = _os.path.join(_BALL_ICON_DIR, f"{fname}.png")
        if _os.path.exists(path):
            try:
                img = Image.open(path).convert("RGBA").resize(
                    (_BALL_ICON_SIZE, _BALL_ICON_SIZE), Image.LANCZOS)
                icons[key] = img
            except Exception:
                pass
    return icons

_BALL_ICONS = _load_ball_icons()

def build_timeline_strip(ball_values, max_balls=18):
    """Build a horizontal PNG strip of ball icons. Returns BytesIO or None."""
    if not PILLOW_AVAILABLE or not _BALL_ICONS:
        return None
    balls = [str(v) for v in ball_values[-max_balls:]]
    if not balls:
        return None
    PAD = 4; SZ = _BALL_ICON_SIZE
    W = len(balls)*(SZ+PAD)+PAD; H = SZ+PAD*2
    strip = Image.new("RGBA", (W, H), (0,0,0,0))
    x = PAD
    for val in balls:
        icon = _BALL_ICONS.get(val, _BALL_ICONS.get("0"))
        if icon:
            strip.paste(icon, (x, PAD), icon)
        x += SZ+PAD
    bg = Image.new("RGB", (W, H), (18,18,28))
    bg.paste(strip, (0,0), strip)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────
# SCORECARD IMAGE GENERATOR
# ─────────────────────────────────────────────
import os as _os
_FONT_BOLD_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
]
_FONT_REG_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
]
_FONT_BOLD    = next((p for p in _FONT_BOLD_PATHS if _os.path.exists(p)), None)
_FONT_REGULAR = next((p for p in _FONT_REG_PATHS  if _os.path.exists(p)), None)

_COL_PURPLE_DARK = (75,  0,  130)
_COL_PURPLE_MID  = (100, 30, 160)
_COL_BLUE_TEAM   = (30,  144, 255)
_COL_ROW_LIGHT   = (230, 240, 255)
_COL_ROW_WHITE   = (245, 248, 255)
_COL_TEXT_DARK   = (20,  20,  20)
_COL_TEXT_WHITE  = (255, 255, 255)
_COL_TEXT_CYAN   = (180, 230, 255)
_COL_HDR_BAR     = (50,  80,  160)

def _fnt(size, bold=True):
    path = _FONT_BOLD if bold else _FONT_REGULAR
    try:
        if path and _os.path.exists(path):
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def generate_scorecard_image(
    team1_name, team1_score, team1_wickets, team1_overs,
    team1_batters, team1_bowlers,
    team2_name, team2_score, team2_wickets, team2_overs,
    team2_batters, team2_bowlers,
    result_text,
    pom_name=None
):
    """Generate scorecard matching the reference screenshot style exactly."""
    if not PILLOW_AVAILABLE:
        return None

    W       = 1100
    ROW_H   = 50
    TEAM_H  = 72
    TITLE_H = 96
    HDR_H   = 34
    FOOT_H  = 78
    PAD     = 14
    DIV     = 8
    HALF    = W // 2  # 550 — split point

    # Colours matching screenshots
    C_BG      = (68,   0, 118)
    C_TITLE   = (82,   6, 140)
    C_TEAM    = (26, 136, 255)
    C_HDR     = (48,  14, 102)
    C_ROW_A   = (248, 244, 255)
    C_ROW_B   = (238, 232, 252)
    C_WHITE   = (255, 255, 255)
    C_CYAN    = (150, 212, 255)
    C_GOLD    = (255, 196,  30)
    C_DARK    = (20,  20,  36)
    C_GRAY    = (108, 106, 128)
    C_FOOTER  = (78,   6, 136)
    C_VSEP    = (112,  72, 172)

    def sec_h(bat, bowl):
        return TEAM_H + HDR_H + max(len(bat), len(bowl)) * ROW_H + PAD

    H = (TITLE_H
         + sec_h(team1_batters, team1_bowlers) + DIV
         + sec_h(team2_batters, team2_bowlers)
         + FOOT_H + 4)

    img = Image.new("RGB", (W, H), C_BG)
    d   = ImageDraw.Draw(img)

    def tw(t, f):
        b = d.textbbox((0,0), t, font=f); return b[2]-b[0]
    def th(t, f):
        b = d.textbbox((0,0), t, font=f); return b[3]-b[1]
    def cx(t, x, y, w, f, c):
        d.text((x+(w-tw(t,f))//2, y), t, font=f, fill=c)
    def rx(t, x, y, xr, f, c):
        # right-align inside [x, xr]
        d.text((xr-tw(t,f), y), t, font=f, fill=c)

    # ── TITLE ──────────────────────────────────────────────────────────
    d.rectangle([0, 0, W, TITLE_H], fill=C_TITLE)
    # Chevrons
    for ox, fl in [(55,1),(W-55,-1)]:
        for i in range(3):
            o=i*9
            pts=[(ox+fl*(18+o),20),(ox+fl*(4+o),TITLE_H//2),(ox+fl*(18+o),TITLE_H-20)]
            d.line(pts, fill=C_CYAN, width=2)
    # Bat icon
    d.ellipse([16,14,70,70], outline=C_CYAN, width=3, fill=C_BG)
    d.line([(43,21),(43,65)], fill=C_CYAN, width=3)
    d.polygon([(35,45),(51,45),(55,63),(31,63)], fill=C_CYAN)
    # Ball icon
    bx,by=W-70,14
    d.ellipse([bx,by,bx+54,by+54], outline=C_CYAN, width=3, fill=C_BG)
    d.arc([bx+7,by+7,bx+47,by+47], 20, 160, fill=C_CYAN, width=2)
    d.arc([bx+7,by+7,bx+47,by+47], 200, 340, fill=C_CYAN, width=2)
    # Title text
    tf = _fnt(38)
    cx("MATCH SUMMARY", 0, (TITLE_H-th("M",tf))//2, W, tf, C_WHITE)
    d.rectangle([W//4, TITLE_H-5, 3*W//4, TITLE_H-1], fill=C_GOLD)
    y = TITLE_H

    # Column x positions (split at HALF=550)
    # Bat side: name 16-410, R 414, B 480
    # Bowl side: name 560-870, WKTS/R 875, OV 990
    BX_NAME = 16;  BX_R = 414; BX_B = 480
    WX_NAME = 560; WX_WR = 875; WX_OV = 994

    def draw_section(tname, tscore, twkts, tovers, batters, bowlers, y0):
        # ── Team bar ────────────────────────────────────────────────
        d.rectangle([0, y0, W, y0+TEAM_H], fill=C_TEAM)
        d.rectangle([0, y0, 5, y0+TEAM_H], fill=C_GOLD)

        nf = _fnt(26); sf = _fnt(34); of = _fnt(13, bold=False)
        # Team name left
        d.text((16, y0+(TEAM_H-th(tname,nf))//2), tname.upper(), font=nf, fill=C_WHITE)
        # Score right
        stxt = f"{tscore}/{twkts}"; otxt = f"OVERS {tovers}"
        sw = tw(stxt, sf); ow = tw(otxt, of)
        d.text((W-18-sw-ow-14, y0+TEAM_H//2-2), otxt, font=of, fill=C_CYAN)
        d.text((W-16-sw, y0+(TEAM_H-th(stxt,sf))//2), stxt, font=sf, fill=C_WHITE)

        y = y0 + TEAM_H

        # ── Column headers ───────────────────────────────────────────
        d.rectangle([0, y, W, y+HDR_H], fill=C_HDR)
        hf = _fnt(12)
        for txt, xp in [("BATTER", BX_NAME), ("R", BX_R), ("B", BX_B),
                         ("BOWLER", WX_NAME), ("WKTS/R", WX_WR), ("OV", WX_OV)]:
            d.text((xp, y+(HDR_H-th(txt,hf))//2), txt, font=hf, fill=C_CYAN)
        d.rectangle([HALF-2, y, HALF+2, y+HDR_H], fill=C_VSEP)
        y += HDR_H

        nrows = max(len(batters), len(bowlers))
        for i in range(nrows):
            bg = C_ROW_A if i%2==0 else C_ROW_B
            d.rectangle([0, y, W, y+ROW_H], fill=bg)
            d.rectangle([HALF-2, y, HALF+2, y+ROW_H], fill=(192,182,222))
            cy2 = y + (ROW_H - th("0", _fnt(15))) // 2

            if i < len(batters):
                bname, runs, balls, notout = batters[i]
                star = "*" if notout else ""
                is_pom = pom_name and bname.lower() == pom_name.lower()
                nc = C_GOLD if is_pom else C_DARK
                dn = (bname.upper()+" ★") if is_pom else bname.upper()
                # Truncate if too long
                nfb = _fnt(15)
                while tw(dn, nfb) > 390 and len(dn) > 4:
                    dn = dn[:-2]+"."
                d.text((BX_NAME, cy2), dn, font=nfb, fill=nc)
                # R — bold, right-aligned in its column
                rf = _fnt(17)
                rx(f"{runs}{star}", BX_R, cy2, BX_R+50, rf, C_DARK)
                # B — lighter
                bf = _fnt(14, bold=False)
                rx(str(balls), BX_B, cy2, BX_B+50, bf, C_GRAY)

            if i < len(bowlers):
                bwname, wkts, bruns, bovs = bowlers[i]
                is_pb = pom_name and bwname.lower() == pom_name.lower()
                bc = C_GOLD if is_pb else C_DARK
                db = (bwname.upper()+" ★") if is_pb else bwname.upper()
                nbf = _fnt(15)
                while tw(db, nbf) > 300 and len(db) > 4:
                    db = db[:-2]+"."
                d.text((WX_NAME, cy2), db, font=nbf, fill=bc)
                # WKTS/R
                wrf = _fnt(17)
                rx(f"{wkts}/{bruns}", WX_WR, cy2, WX_WR+80, wrf, C_DARK)
                # OV
                ovf = _fnt(14, bold=False)
                rx(str(bovs), WX_OV, cy2, WX_OV+42, ovf, C_GRAY)

            d.rectangle([0, y+ROW_H-1, W, y+ROW_H], fill=(202,195,228))
            y += ROW_H
        return y + PAD

    y = draw_section(team1_name, team1_score, team1_wickets, team1_overs,
                     team1_batters, team1_bowlers, y)
    d.rectangle([0, y, W, y+DIV], fill=C_BG)
    y += DIV
    y = draw_section(team2_name, team2_score, team2_wickets, team2_overs,
                     team2_batters, team2_bowlers, y)

    # ── FOOTER ──────────────────────────────────────────────────────────
    d.rectangle([0, y, W, y+FOOT_H], fill=C_FOOTER)
    d.rectangle([0, y, W, y+4], fill=C_GOLD)
    rf = _fnt(26)
    ry = y + 12 + (4 if pom_name else 14)
    cx(result_text.upper(), 0, ry, W, rf, C_WHITE)
    if pom_name:
        pf = _fnt(14, bold=False)
        cx(f"★  Player of the Match:  {pom_name}  ★",
           0, ry+th("A",rf)+10, W, pf, C_GOLD)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


scheduled_tasks = {}
active_matches = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='+', intents=intents)

BALANCE_FILE  = 'balances.json'
BUNDLES_FILE  = 'bundles.json'
FIXTURES_FILE = 'fixtures.json'
SHOP_FILE     = 'shop.json'
SQUAD_FILE    = 'squad.json'
PENDING_FILE  = 'pending_packs.json'
STATS_FILE    = 'stats.json'
GIFS_FILE     = 'gifs.json'   # { "<player name lower>": {"50": "url", "100": "url"} }

# ─────────────────────────────────────────────
# PLAYER POOL
# ─────────────────────────────────────────────
ALL_PLAYERS = {
    # ── LEGENDARY ──────────────────────────────────────────────────
    "Rohit Sharma":           {"rarity":"Legendary","role":"BAT", "team":"Mumbai Indians",               "country":"India",        "value":620},
    "Virat Kohli":            {"rarity":"Legendary","role":"BAT", "team":"Royal Challengers Bengaluru",  "country":"India",        "value":600},
    "MS Dhoni":               {"rarity":"Legendary","role":"WK",  "team":"Chennai Super Kings",           "country":"India",        "value":580},
    "Jasprit Bumrah":         {"rarity":"Legendary","role":"BOWL","team":"Mumbai Indians",               "country":"India",        "value":570},
    "Rashid Khan":            {"rarity":"Legendary","role":"BOWL","team":"Gujarat Titans",               "country":"Afghanistan",  "value":555},
    "Pat Cummins":            {"rarity":"Legendary","role":"BOWL","team":"Sunrisers Hyderabad",          "country":"Australia",    "value":545},
    "Jos Buttler":            {"rarity":"Legendary","role":"WK",  "team":"Gujarat Titans",               "country":"England",      "value":535},
    "Andre Russell":          {"rarity":"Legendary","role":"ALR", "team":"Kolkata Knight Riders",        "country":"West Indies",  "value":530},
    "Suryakumar Yadav":       {"rarity":"Legendary","role":"BAT", "team":"Mumbai Indians",               "country":"India",        "value":525},
    "Hardik Pandya":          {"rarity":"Legendary","role":"ALR", "team":"Mumbai Indians",               "country":"India",        "value":515},
    "Ravindra Jadeja":        {"rarity":"Legendary","role":"ALR", "team":"Chennai Super Kings",          "country":"India",        "value":510},
    "KL Rahul":               {"rarity":"Legendary","role":"WK",  "team":"Delhi Capitals",               "country":"India",        "value":505},
    "Rishabh Pant":           {"rarity":"Legendary","role":"WK",  "team":"Lucknow Super Giants",         "country":"India",        "value":500},
    "Yashasvi Jaiswal":       {"rarity":"Legendary","role":"BAT", "team":"Rajasthan Royals",             "country":"India",        "value":500},
    "Travis Head":            {"rarity":"Legendary","role":"BAT", "team":"Sunrisers Hyderabad",          "country":"Australia",    "value":510},
    "Shreyas Iyer":           {"rarity":"Legendary","role":"BAT", "team":"Punjab Kings",                 "country":"India",        "value":495},
    "Babar Azam":             {"rarity":"Legendary","role":"BAT", "team":"Pakistan XI",                  "country":"Pakistan",     "value":490},
    "Glenn Maxwell":          {"rarity":"Legendary","role":"ALR", "team":"Punjab Kings",                 "country":"Australia",    "value":490},
    "Shaheen Afridi":         {"rarity":"Legendary","role":"BOWL","team":"Pakistan XI",                  "country":"Pakistan",     "value":500},
    "Ben Stokes":             {"rarity":"Legendary","role":"ALR", "team":"England XI",                   "country":"England",      "value":495},
    # ── EPIC — CSK ─────────────────────────────────────────────────
    "Ruturaj Gaikwad":        {"rarity":"Epic","role":"BAT", "team":"Chennai Super Kings",          "country":"India",        "value":440},
    "Shivam Dube":            {"rarity":"Epic","role":"ALR", "team":"Chennai Super Kings",          "country":"India",        "value":390},
    "Rachin Ravindra":        {"rarity":"Epic","role":"ALR", "team":"Chennai Super Kings",          "country":"New Zealand",  "value":400},
    "Matheesha Pathirana":    {"rarity":"Epic","role":"BOWL","team":"Chennai Super Kings",          "country":"Sri Lanka",    "value":395},
    "Noor Ahmad":             {"rarity":"Epic","role":"BOWL","team":"Chennai Super Kings",          "country":"Afghanistan",  "value":370},
    "Devon Conway":           {"rarity":"Epic","role":"WK",  "team":"Chennai Super Kings",          "country":"New Zealand",  "value":360},
    "Sam Curran":             {"rarity":"Epic","role":"ALR", "team":"Chennai Super Kings",          "country":"England",      "value":355},
    "R Ashwin":               {"rarity":"Epic","role":"ALR", "team":"Chennai Super Kings",          "country":"India",        "value":350},
    "Khaleel Ahmed":          {"rarity":"Epic","role":"BOWL","team":"Chennai Super Kings",          "country":"India",        "value":320},
    # ── EPIC — RCB ─────────────────────────────────────────────────
    "Rajat Patidar":          {"rarity":"Epic","role":"BAT", "team":"Royal Challengers Bengaluru",  "country":"India",        "value":410},
    "Phil Salt":              {"rarity":"Epic","role":"WK",  "team":"Royal Challengers Bengaluru",  "country":"England",      "value":400},
    "Tim David":              {"rarity":"Epic","role":"BAT", "team":"Royal Challengers Bengaluru",  "country":"Singapore",    "value":380},
    "Liam Livingstone":       {"rarity":"Epic","role":"ALR", "team":"Royal Challengers Bengaluru",  "country":"England",      "value":375},
    "Krunal Pandya":          {"rarity":"Epic","role":"ALR", "team":"Royal Challengers Bengaluru",  "country":"India",        "value":360},
    "Bhuvneshwar Kumar":      {"rarity":"Epic","role":"BOWL","team":"Royal Challengers Bengaluru",  "country":"India",        "value":345},
    "Josh Hazlewood":         {"rarity":"Epic","role":"BOWL","team":"Royal Challengers Bengaluru",  "country":"Australia",    "value":355},
    "Romario Shepherd":       {"rarity":"Epic","role":"ALR", "team":"Royal Challengers Bengaluru",  "country":"West Indies",  "value":330},
    "Devdutt Padikkal":       {"rarity":"Epic","role":"BAT", "team":"Royal Challengers Bengaluru",  "country":"India",        "value":325},
    "Jacob Bethell":          {"rarity":"Epic","role":"ALR", "team":"Royal Challengers Bengaluru",  "country":"England",      "value":310},
    # ── EPIC — MI ──────────────────────────────────────────────────
    "Tilak Varma":            {"rarity":"Epic","role":"BAT", "team":"Mumbai Indians",               "country":"India",        "value":420},
    "Will Jacks":             {"rarity":"Epic","role":"ALR", "team":"Mumbai Indians",               "country":"England",      "value":360},
    "Naman Dhir":             {"rarity":"Rare","role":"ALR", "team":"Mumbai Indians",               "country":"India",        "value":210},
    "Allah Ghazanfar":        {"rarity":"Epic","role":"BOWL","team":"Mumbai Indians",               "country":"Afghanistan",  "value":320},
    "Ryan Rickelton":         {"rarity":"Rare","role":"WK",  "team":"Mumbai Indians",               "country":"South Africa", "value":235},
    "Mitchell Santner":       {"rarity":"Epic","role":"ALR", "team":"Mumbai Indians",               "country":"New Zealand",  "value":355},
    "Karn Sharma":            {"rarity":"Common","role":"BOWL","team":"Mumbai Indians",             "country":"India",        "value":110},
    # ── EPIC — KKR ─────────────────────────────────────────────────
    "Sunil Narine":           {"rarity":"Legendary","role":"ALR","team":"Kolkata Knight Riders",    "country":"West Indies",  "value":530},
    "Ajinkya Rahane":         {"rarity":"Epic","role":"BAT", "team":"Kolkata Knight Riders",        "country":"India",        "value":340},
    "Rinku Singh":            {"rarity":"Epic","role":"BAT", "team":"Kolkata Knight Riders",        "country":"India",        "value":380},
    "Quinton de Kock":        {"rarity":"Epic","role":"WK",  "team":"Kolkata Knight Riders",        "country":"South Africa", "value":390},
    "Rahmanullah Gurbaz":     {"rarity":"Epic","role":"WK",  "team":"Kolkata Knight Riders",        "country":"Afghanistan",  "value":360},
    "Venkatesh Iyer":         {"rarity":"Epic","role":"ALR", "team":"Kolkata Knight Riders",        "country":"India",        "value":355},
    "Anrich Nortje":          {"rarity":"Epic","role":"BOWL","team":"Kolkata Knight Riders",        "country":"South Africa", "value":370},
    "Varun Chakravarthy":     {"rarity":"Epic","role":"BOWL","team":"Kolkata Knight Riders",        "country":"India",        "value":385},
    "Spencer Johnson":        {"rarity":"Rare","role":"BOWL","team":"Kolkata Knight Riders",        "country":"Australia",    "value":230},
    "Moeen Ali":              {"rarity":"Rare","role":"ALR", "team":"Kolkata Knight Riders",        "country":"England",      "value":245},
    "Rovman Powell":          {"rarity":"Rare","role":"BAT", "team":"Kolkata Knight Riders",        "country":"West Indies",  "value":235},
    "Harshit Rana":           {"rarity":"Rare","role":"BOWL","team":"Kolkata Knight Riders",        "country":"India",        "value":250},
    "Ramandeep Singh":        {"rarity":"Rare","role":"ALR", "team":"Kolkata Knight Riders",        "country":"India",        "value":240},
    "Angkrish Raghuvanshi":   {"rarity":"Rare","role":"BAT", "team":"Kolkata Knight Riders",        "country":"India",        "value":210},
    "Mayank Markande":        {"rarity":"Common","role":"BOWL","team":"Kolkata Knight Riders",      "country":"India",        "value":110},
    # ── EPIC — SRH ─────────────────────────────────────────────────
    "Abhishek Sharma":        {"rarity":"Epic","role":"BAT", "team":"Sunrisers Hyderabad",          "country":"India",        "value":400},
    "Heinrich Klaasen":       {"rarity":"Epic","role":"WK",  "team":"Sunrisers Hyderabad",          "country":"South Africa", "value":415},
    "Nitish Reddy":           {"rarity":"Epic","role":"ALR", "team":"Sunrisers Hyderabad",          "country":"India",        "value":370},
    "Ishan Kishan":           {"rarity":"Epic","role":"WK",  "team":"Sunrisers Hyderabad",          "country":"India",        "value":375},
    "Mohammad Shami":         {"rarity":"Epic","role":"BOWL","team":"Sunrisers Hyderabad",          "country":"India",        "value":410},
    "Harshal Patel":          {"rarity":"Rare","role":"BOWL","team":"Sunrisers Hyderabad",          "country":"India",        "value":250},
    "Adam Zampa":             {"rarity":"Rare","role":"BOWL","team":"Sunrisers Hyderabad",          "country":"Australia",    "value":240},
    "Rahul Chahar":           {"rarity":"Rare","role":"BOWL","team":"Sunrisers Hyderabad",          "country":"India",        "value":220},
    "Kamindu Mendis":         {"rarity":"Rare","role":"ALR", "team":"Sunrisers Hyderabad",          "country":"Sri Lanka",    "value":230},
    "Atharva Taide":          {"rarity":"Common","role":"BAT","team":"Sunrisers Hyderabad",         "country":"India",        "value":115},
    "Zeeshan Ansari":         {"rarity":"Common","role":"BOWL","team":"Sunrisers Hyderabad",        "country":"India",        "value":100},
    # ── EPIC — GT ──────────────────────────────────────────────────
    "Shubman Gill":           {"rarity":"Epic","role":"BAT", "team":"Gujarat Titans",               "country":"India",        "value":460},
    "Kagiso Rabada":          {"rarity":"Epic","role":"BOWL","team":"Gujarat Titans",               "country":"South Africa", "value":420},
    "Mohammed Siraj":         {"rarity":"Epic","role":"BOWL","team":"Gujarat Titans",               "country":"India",        "value":390},
    "Prasidh Krishna":        {"rarity":"Epic","role":"BOWL","team":"Gujarat Titans",               "country":"India",        "value":365},
    "Washington Sundar":      {"rarity":"Epic","role":"ALR", "team":"Gujarat Titans",               "country":"India",        "value":355},
    "Sai Sudharsan":          {"rarity":"Epic","role":"BAT", "team":"Gujarat Titans",               "country":"India",        "value":380},
    "Rahul Tewatia":          {"rarity":"Rare","role":"ALR", "team":"Gujarat Titans",               "country":"India",        "value":245},
    "Shahrukh Khan":          {"rarity":"Rare","role":"BAT", "team":"Gujarat Titans",               "country":"India",        "value":230},
    "Gerald Coetzee":         {"rarity":"Rare","role":"BOWL","team":"Gujarat Titans",               "country":"South Africa", "value":235},
    "Anuj Rawat":             {"rarity":"Rare","role":"WK",  "team":"Gujarat Titans",               "country":"India",        "value":200},
    "Manav Suthar":           {"rarity":"Common","role":"BOWL","team":"Gujarat Titans",             "country":"India",        "value":105},
    # ── EPIC — RR ──────────────────────────────────────────────────
    "Sanju Samson":           {"rarity":"Epic","role":"WK",  "team":"Rajasthan Royals",             "country":"India",        "value":440},
    "Riyan Parag":            {"rarity":"Epic","role":"ALR", "team":"Rajasthan Royals",             "country":"India",        "value":370},
    "Dhruv Jurel":            {"rarity":"Epic","role":"WK",  "team":"Rajasthan Royals",             "country":"India",        "value":355},
    "Shimron Hetmyer":        {"rarity":"Epic","role":"BAT", "team":"Rajasthan Royals",             "country":"West Indies",  "value":360},
    "Jofra Archer":           {"rarity":"Epic","role":"BOWL","team":"Rajasthan Royals",             "country":"England",      "value":400},
    "Wanindu Hasaranga":      {"rarity":"Epic","role":"ALR", "team":"Rajasthan Royals",             "country":"Sri Lanka",    "value":365},
    "Maheesh Theekshana":     {"rarity":"Epic","role":"BOWL","team":"Rajasthan Royals",             "country":"Sri Lanka",    "value":345},
    "Fazal Farooqi":          {"rarity":"Rare","role":"BOWL","team":"Rajasthan Royals",             "country":"Afghanistan",  "value":255},
    "Vaibhav Suryavanshi":    {"rarity":"Rare","role":"BAT", "team":"Rajasthan Royals",             "country":"India",        "value":220},
    "Nitish Rana":            {"rarity":"Rare","role":"BAT", "team":"Rajasthan Royals",             "country":"India",        "value":215},
    "Tushar Deshpande":       {"rarity":"Rare","role":"BOWL","team":"Rajasthan Royals",             "country":"India",        "value":205},
    "Kumar Kartikeya":        {"rarity":"Common","role":"BOWL","team":"Rajasthan Royals",           "country":"India",        "value":105},
    "Kwena Maphaka":          {"rarity":"Common","role":"BOWL","team":"Rajasthan Royals",           "country":"South Africa", "value":110},
    # ── EPIC — DC ──────────────────────────────────────────────────
    "Axar Patel":             {"rarity":"Epic","role":"ALR", "team":"Delhi Capitals",               "country":"India",        "value":430},
    "Kuldeep Yadav":          {"rarity":"Epic","role":"BOWL","team":"Delhi Capitals",               "country":"India",        "value":405},
    "Mitchell Starc":         {"rarity":"Epic","role":"BOWL","team":"Delhi Capitals",               "country":"Australia",    "value":420},
    "Faf du Plessis":         {"rarity":"Epic","role":"BAT", "team":"Delhi Capitals",               "country":"South Africa", "value":370},
    "Jake Fraser-McGurk":     {"rarity":"Epic","role":"BAT", "team":"Delhi Capitals",               "country":"Australia",    "value":380},
    "Tristan Stubbs":         {"rarity":"Rare","role":"WK",  "team":"Delhi Capitals",               "country":"South Africa", "value":245},
    "Abishek Porel":          {"rarity":"Rare","role":"WK",  "team":"Delhi Capitals",               "country":"India",        "value":220},
    "T Natarajan":            {"rarity":"Rare","role":"BOWL","team":"Delhi Capitals",               "country":"India",        "value":235},
    "Karun Nair":             {"rarity":"Rare","role":"BAT", "team":"Delhi Capitals",               "country":"India",        "value":210},
    "Mohit Sharma":           {"rarity":"Rare","role":"BOWL","team":"Delhi Capitals",               "country":"India",        "value":225},
    "Sameer Rizvi":           {"rarity":"Rare","role":"BAT", "team":"Delhi Capitals",               "country":"India",        "value":195},
    "Mukesh Kumar":           {"rarity":"Common","role":"BOWL","team":"Delhi Capitals",             "country":"India",        "value":110},
    "Faf du Plessis":         {"rarity":"Epic","role":"BAT", "team":"Delhi Capitals",               "country":"South Africa", "value":370},
    # ── EPIC — LSG ─────────────────────────────────────────────────
    "Nicholas Pooran":        {"rarity":"Epic","role":"WK",  "team":"Lucknow Super Giants",         "country":"West Indies",  "value":420},
    "David Miller":           {"rarity":"Epic","role":"BAT", "team":"Lucknow Super Giants",         "country":"South Africa", "value":390},
    "Aiden Markram":          {"rarity":"Epic","role":"ALR", "team":"Lucknow Super Giants",         "country":"South Africa", "value":375},
    "Mitchell Marsh":         {"rarity":"Epic","role":"ALR", "team":"Lucknow Super Giants",         "country":"Australia",    "value":385},
    "Mayank Yadav":           {"rarity":"Epic","role":"BOWL","team":"Lucknow Super Giants",         "country":"India",        "value":360},
    "Ravi Bishnoi":           {"rarity":"Epic","role":"BOWL","team":"Lucknow Super Giants",         "country":"India",        "value":345},
    "Avesh Khan":             {"rarity":"Rare","role":"BOWL","team":"Lucknow Super Giants",         "country":"India",        "value":240},
    "Abdul Samad":            {"rarity":"Rare","role":"ALR", "team":"Lucknow Super Giants",         "country":"India",        "value":225},
    "Akash Deep":             {"rarity":"Rare","role":"BOWL","team":"Lucknow Super Giants",         "country":"India",        "value":250},
    "Shahbaz Ahmed":          {"rarity":"Rare","role":"ALR", "team":"Lucknow Super Giants",         "country":"India",        "value":215},
    "Shamar Joseph":          {"rarity":"Rare","role":"BOWL","team":"Lucknow Super Giants",         "country":"West Indies",  "value":230},
    "Mohsin Khan":            {"rarity":"Rare","role":"BOWL","team":"Lucknow Super Giants",         "country":"India",        "value":210},
    "Aryan Juyal":            {"rarity":"Common","role":"WK","team":"Lucknow Super Giants",         "country":"India",        "value":100},
    # ── EPIC — PBKS ────────────────────────────────────────────────
    "Arshdeep Singh":         {"rarity":"Epic","role":"BOWL","team":"Punjab Kings",                 "country":"India",        "value":400},
    "Yuzvendra Chahal":       {"rarity":"Epic","role":"BOWL","team":"Punjab Kings",                 "country":"India",        "value":350},
    "Marcus Stoinis":         {"rarity":"Epic","role":"ALR", "team":"Punjab Kings",                 "country":"Australia",    "value":390},
    "Marco Jansen":           {"rarity":"Epic","role":"ALR", "team":"Punjab Kings",                 "country":"South Africa", "value":370},
    "Josh Inglis":            {"rarity":"Epic","role":"WK",  "team":"Punjab Kings",                 "country":"Australia",    "value":355},
    "Lockie Ferguson":        {"rarity":"Epic","role":"BOWL","team":"Punjab Kings",                 "country":"New Zealand",  "value":360},
    "Prabhsimran Singh":      {"rarity":"Rare","role":"WK",  "team":"Punjab Kings",                 "country":"India",        "value":230},
    "Shashank Singh":         {"rarity":"Rare","role":"BAT", "team":"Punjab Kings",                 "country":"India",        "value":240},
    "Harpreet Brar":          {"rarity":"Rare","role":"ALR", "team":"Punjab Kings",                 "country":"India",        "value":215},
    "Azmatullah Omarzai":     {"rarity":"Rare","role":"ALR", "team":"Punjab Kings",                 "country":"Afghanistan",  "value":225},
    "Aaron Hardie":           {"rarity":"Rare","role":"ALR", "team":"Punjab Kings",                 "country":"Australia",    "value":220},
    "Priyansh Arya":          {"rarity":"Rare","role":"BAT", "team":"Punjab Kings",                 "country":"India",        "value":200},
    "Yash Thakur":            {"rarity":"Common","role":"BOWL","team":"Punjab Kings",               "country":"India",        "value":105},
    "Vijaykumar Vyshak":      {"rarity":"Common","role":"BOWL","team":"Punjab Kings",               "country":"India",        "value":110},
    # ── RARE — CSK extras ──────────────────────────────────────────
    "Rahul Tripathi":         {"rarity":"Rare","role":"BAT", "team":"Chennai Super Kings",          "country":"India",        "value":230},
    "Anshul Kamboj":          {"rarity":"Rare","role":"BOWL","team":"Chennai Super Kings",          "country":"India",        "value":210},
    "Jamie Overton":          {"rarity":"Rare","role":"ALR", "team":"Chennai Super Kings",          "country":"England",      "value":220},
    "Nathan Ellis":           {"rarity":"Rare","role":"BOWL","team":"Chennai Super Kings",          "country":"Australia",    "value":215},
    "Vijay Shankar":          {"rarity":"Common","role":"ALR","team":"Chennai Super Kings",         "country":"India",        "value":130},
    "Mukesh Choudhary":       {"rarity":"Common","role":"BOWL","team":"Chennai Super Kings",        "country":"India",        "value":110},
    "Jitesh Sharma":          {"rarity":"Rare","role":"WK",  "team":"Royal Challengers Bengaluru",  "country":"India",        "value":240},
    "Lungi Ngidi":            {"rarity":"Rare","role":"BOWL","team":"Royal Challengers Bengaluru",  "country":"South Africa", "value":220},
    "Yash Dayal":             {"rarity":"Rare","role":"BOWL","team":"Royal Challengers Bengaluru",  "country":"India",        "value":200},
    "Nuwan Thushara":         {"rarity":"Rare","role":"BOWL","team":"Royal Challengers Bengaluru",  "country":"Sri Lanka",    "value":195},
    "Swapnil Singh":          {"rarity":"Common","role":"ALR","team":"Royal Challengers Bengaluru","country":"India",         "value":110},
    "Manoj Bhandage":         {"rarity":"Common","role":"ALR","team":"Royal Challengers Bengaluru","country":"India",         "value":100},
    # ── INTERNATIONAL STARS ────────────────────────────────────────
    "Kane Williamson":        {"rarity":"Epic","role":"BAT", "team":"New Zealand XI",               "country":"New Zealand",  "value":435},
    "Trent Boult":            {"rarity":"Epic","role":"BOWL","team":"New Zealand XI",               "country":"New Zealand",  "value":395},
    "Finn Allen":             {"rarity":"Rare","role":"BAT", "team":"New Zealand XI",               "country":"New Zealand",  "value":240},
    "Tim Southee":            {"rarity":"Rare","role":"BOWL","team":"New Zealand XI",               "country":"New Zealand",  "value":225},
    "Matt Henry":             {"rarity":"Epic","role":"BOWL","team":"New Zealand XI",               "country":"New Zealand",  "value":370},
    "Joe Root":               {"rarity":"Legendary","role":"BAT","team":"England XI",               "country":"England",      "value":480},
    "Jonny Bairstow":         {"rarity":"Epic","role":"WK",  "team":"England XI",                   "country":"England",      "value":380},
    "Adil Rashid":            {"rarity":"Epic","role":"BOWL","team":"England XI",                   "country":"England",      "value":350},
    "Mark Wood":              {"rarity":"Epic","role":"BOWL","team":"England XI",                   "country":"England",      "value":355},
    "Harry Brook":            {"rarity":"Epic","role":"BAT", "team":"England XI",                   "country":"England",      "value":390},
    "David Warner":           {"rarity":"Epic","role":"BAT", "team":"Australia XI",                "country":"Australia",    "value":380},
    "Steve Smith":            {"rarity":"Epic","role":"BAT", "team":"Australia XI",                "country":"Australia",    "value":370},
    "Cameron Green":          {"rarity":"Epic","role":"ALR", "team":"Australia XI",                "country":"Australia",    "value":360},
    "Temba Bavuma":           {"rarity":"Epic","role":"BAT", "team":"South Africa XI",             "country":"South Africa", "value":360},
    "Tabraiz Shamsi":         {"rarity":"Epic","role":"BOWL","team":"South Africa XI",             "country":"South Africa", "value":345},
    "Fakhar Zaman":           {"rarity":"Epic","role":"BAT", "team":"Pakistan XI",                 "country":"Pakistan",     "value":355},
    "Mohammad Rizwan":        {"rarity":"Epic","role":"WK",  "team":"Pakistan XI",                 "country":"Pakistan",     "value":395},
    "Shadab Khan":            {"rarity":"Epic","role":"ALR", "team":"Pakistan XI",                 "country":"Pakistan",     "value":360},
    "Haris Rauf":             {"rarity":"Epic","role":"BOWL","team":"Pakistan XI",                 "country":"Pakistan",     "value":350},
    "Shakib Al Hasan":        {"rarity":"Epic","role":"ALR", "team":"Bangladesh XI",               "country":"Bangladesh",   "value":365},
    "Mustafizur Rahman":      {"rarity":"Rare","role":"BOWL","team":"Bangladesh XI",               "country":"Bangladesh",   "value":225},
    "Liton Das":              {"rarity":"Rare","role":"WK",  "team":"Bangladesh XI",               "country":"Bangladesh",   "value":210},
    "Mehidy Hasan Miraz":     {"rarity":"Rare","role":"ALR", "team":"Bangladesh XI",               "country":"Bangladesh",   "value":215},
    "Pathum Nissanka":        {"rarity":"Rare","role":"BAT", "team":"Sri Lanka XI",                "country":"Sri Lanka",    "value":230},
    "Charith Asalanka":       {"rarity":"Rare","role":"BAT", "team":"Sri Lanka XI",                "country":"Sri Lanka",    "value":225},
    "Sikandar Raza":          {"rarity":"Rare","role":"ALR", "team":"Zimbabwe XI",                 "country":"Zimbabwe",     "value":220},
    "Blessing Muzarabani":    {"rarity":"Rare","role":"BOWL","team":"Zimbabwe XI",                 "country":"Zimbabwe",     "value":215},
    "Kusal Mendis":           {"rarity":"Rare","role":"WK",  "team":"Sri Lanka XI",                "country":"Sri Lanka",    "value":230},
    "Dunith Wellalage":       {"rarity":"Rare","role":"ALR", "team":"Sri Lanka XI",                "country":"Sri Lanka",    "value":215},
}

PLAYER_LOOKUP = {name.lower(): name for name in ALL_PLAYERS}

IPL_TEAMS = {
    "Mumbai Indians","Royal Challengers Bengaluru","Chennai Super Kings",
    "Kolkata Knight Riders","Rajasthan Royals","Delhi Capitals",
    "Punjab Kings","Sunrisers Hyderabad","Lucknow Super Giants","Gujarat Titans"
}
IPL_PLAYERS = {k:v for k,v in ALL_PLAYERS.items() if v["team"] in IPL_TEAMS}

# T20 WC 2026 pack — curated squad players (only those present in ALL_PLAYERS)
_T20_WC_NAMES = [
    "Finn Allen", "Aiden Markram", "Shimron Hetmyer",
    "Ishan Kishan", "Sanju Samson",
    "Will Jacks", "Hardik Pandya", "Rachin Ravindra",
    "Blessing Muzarabani", "Adil Rashid",
    "Varun Chakravarthy", "Lungi Ngidi", "Jasprit Bumrah",
    "Yashasvi Jaiswal", "Mohammad Rizwan", "Wanindu Hasaranga",
    "Fazal Farooqi",
]
T20_WC_PLAYERS = {name: ALL_PLAYERS[name] for name in _T20_WC_NAMES if name in ALL_PLAYERS}

RARITY_WEIGHTS = {"Legendary":5,"Epic":20,"Rare":40,"Common":35}
RARITY_ORDER   = ["Legendary","Epic","Rare","Common"]
RARITY_COLORS  = {"Legendary":0xFFD700,"Epic":0x9B59B6,"Rare":0x3498DB,"Common":0x95A5A6}
RARITY_EMOJI   = {"Legendary":"👑","Epic":"💜","Rare":"🔵","Common":"⚪"}
ROLE_META = {
    "BAT": {"label":"Batters",        "emoji":"🏏","color":0x1ABC9C},
    "BOWL":{"label":"Bowlers",        "emoji":"🎯","color":0xE74C3C},
    "WK":  {"label":"Wicket Keepers", "emoji":"🧤","color":0xF39C12},
    "ALR": {"label":"All-Rounders",   "emoji":"⚡","color":0x9B59B6},
}
PLAYER_IMAGES = {"Rohit Sharma":"assets/rohit_sharma.png"}
SELL_PCT = 0.60   # sell-back percentage of player value

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def weighted_random_player(pool):
    names   = list(pool.keys())
    weights = [RARITY_WEIGHTS[pool[n]["rarity"]] for n in names]
    return random.choices(names, weights=weights, k=1)[0]

def find_player(query: str):
    key = query.strip().lower()
    if key in PLAYER_LOOKUP:
        name = PLAYER_LOOKUP[key]
        return name, ALL_PLAYERS[name]
    matches = [n for n in PLAYER_LOOKUP if key in n]
    if len(matches) == 1:
        name = PLAYER_LOOKUP[matches[0]]
        return name, ALL_PLAYERS[name]
    return None, None

def parse_ist_time(time_str):
    time_str = time_str.replace('.', ':').upper()
    if 'IST' not in time_str:
        time_str += ' IST'
    try:
        dt = datetime.strptime(time_str, "%I:%M %p IST")
        # assume today, if past, tomorrow
        now = datetime.now()
        ist_now = now + timedelta(hours=5, minutes=30)
        dt = dt.replace(year=ist_now.year, month=ist_now.month, day=ist_now.day)
        if dt < ist_now:
            dt += timedelta(days=1)
        # now dt is in IST
        utc_dt = dt - timedelta(hours=5, minutes=30)
        return utc_dt
    except:
        return None

def load_json(filename):
    with open(filename,'r') as f: return json.load(f)

def save_json(data, filename):
    with open(filename,'w') as f: json.dump(data, f, indent=2)

def init_files():
    defaults = {
        BALANCE_FILE:  {},
        BUNDLES_FILE:  {"active_bundles":[]},
        FIXTURES_FILE: {"fixtures":[]},
        SHOP_FILE:     {"items":[]},
        SQUAD_FILE:    {},
        PENDING_FILE:  {},
        STATS_FILE:    {},
        GIFS_FILE:     {},
    }
    for fp, default in defaults.items():
        if not os.path.exists(fp):
            with open(fp,'w') as f: json.dump(default, f)

def add_to_squad(uid: str, player_name: str, acquired_via: str):
    squad = load_json(SQUAD_FILE)
    if uid not in squad: squad[uid] = []
    p = ALL_PLAYERS[player_name]
    squad[uid].append({
        "name":     player_name,
        "rarity":   p["rarity"],
        "role":     p["role"],
        "team":     p["team"],
        "country":  p["country"],
        "value":    p["value"],
        "acquired": acquired_via,
        "timestamp":datetime.now().isoformat()
    })
    save_json(squad, SQUAD_FILE)

def get_balance(uid):
    data = load_json(BALANCE_FILE)
    return data.get(uid, {"coins":0,"tickets":0})

def set_balance(uid, coins, tickets):
    data = load_json(BALANCE_FILE)
    data[uid] = {"coins":coins,"tickets":tickets}
    save_json(data, BALANCE_FILE)

# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    init_files()
    print(f'{bot.user} has landed!')
    print('Bot is ready!')
    # Load and schedule existing fixtures
    data = load_json(FIXTURES_FILE)
    for f in data.get("fixtures", []):
        scheduled_utc = datetime.fromisoformat(f["scheduled_utc"])
        if scheduled_utc > datetime.now():
            channel = bot.get_channel(f["channel_id"])
            if channel:
                team1 = channel.guild.get_role(f["team1_id"])
                team2 = channel.guild.get_role(f["team2_id"])
                if team1 and team2:
                    async def reopen(f=f, channel=channel, team1=team1, team2=team2):
                        delay = (scheduled_utc - datetime.now()).total_seconds()
                        if delay > 0:
                            await asyncio.sleep(delay)
                        everyone = channel.guild.default_role
                        await channel.set_permissions(everyone, send_messages=None)
                        await channel.send(f"{team1.mention} vs {team2.mention} - Match time! {f['time_str']}")
                        data = load_json(FIXTURES_FILE)
                        data["fixtures"] = [fx for fx in data["fixtures"] if fx["channel_id"] != channel.id]
                        save_json(data, FIXTURES_FILE)
                        if channel.id in scheduled_tasks:
                            del scheduled_tasks[channel.id]
                    task = bot.loop.create_task(reopen())
                    scheduled_tasks[channel.id] = task

# ─────────────────────────────────────────────
# BALANCE / ECONOMY
# ─────────────────────────────────────────────
@bot.command(name='balance', aliases=['bal', 'Snbal'])
async def balance(ctx, member: discord.Member = None):
    user = member or ctx.author
    b = get_balance(str(user.id))
    embed = discord.Embed(
        title=f"💰 {user.display_name}'s Wallet",
        color=0xf1c40f
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="🎟️ Tics",  value=f"{b['tickets']:,}", inline=True)
    embed.add_field(name="🪙 Coins", value=f"{b['coins']:,}",   inline=True)
    embed.set_footer(text="Use Snbal to check your balance!")
    await ctx.send(embed=embed)

@bot.command(name='addcoins')
async def add_coins(ctx, member: discord.Member, amount: int):
    """(Admin) Add coins to a user. Usage: -addcoins @user 500"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    uid = str(member.id)
    b = get_balance(uid)
    b['coins'] += amount
    set_balance(uid, b['coins'], b['tickets'])
    await ctx.send(f"✅ Added **{amount:,}** coins to {member.mention} → Balance: **{b['coins']:,}** 🪙")

@bot.command(name='addtickets')
async def add_tickets(ctx, member: discord.Member, amount: int):
    """(Admin) Add tickets to a user. Usage: -addtickets @user 5"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    uid = str(member.id)
    b = get_balance(uid)
    b['tickets'] += amount
    set_balance(uid, b['coins'], b['tickets'])
    await ctx.send(f"✅ Added **{amount}** ticket(s) to {member.mention} → Balance: **{b['tickets']}** 🎫")

@bot.command(name='addbalance')
async def add_balance(ctx, member: discord.Member, coins: int = 0, tickets: int = 0):
    """(Admin) Add both coins and tickets at once."""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    uid = str(member.id)
    b = get_balance(uid)
    b['coins']   += coins
    b['tickets'] += tickets
    set_balance(uid, b['coins'], b['tickets'])
    await ctx.send(f"✅ Added **{coins:,}** coins + **{tickets}** tickets to {member.mention}")

# ─────────────────────────────────────────────
# ADMIN PLAYER MANAGEMENT
# ─────────────────────────────────────────────
@bot.command(name='addplayer')
async def admin_add_player(ctx, member: discord.Member, *, player_name: str):
    """(Admin) Add a player directly to a user's squad. Usage: +addplayer @user Virat Kohli"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    name, data = find_player(player_name)
    if not name:
        return await ctx.send(f"❌ Player **{player_name}** not found. Use `+players` to browse.")
    add_to_squad(str(member.id), name, "Admin Gift")
    rarity = data['rarity']
    embed = discord.Embed(
        title="🎁 Player Added!",
        description=f"**{name}** was added to {member.mention}'s squad by admin.",
        color=RARITY_COLORS[rarity]
    )
    embed.add_field(name="⭐ Rarity",  value=f"{RARITY_EMOJI[rarity]} {rarity}", inline=True)
    embed.add_field(name="🏏 Team",    value=data['team'],                        inline=True)
    embed.add_field(name="🌍 Country", value=data['country'],                     inline=True)
    await ctx.send(embed=embed)

@bot.command(name='removeplayer')
async def admin_remove_player(ctx, member: discord.Member, *, player_name: str):
    """(Admin) Remove a player from a user's squad. Usage: +removeplayer @user Virat Kohli"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    name, data = find_player(player_name)
    if not name:
        return await ctx.send(f"❌ Player **{player_name}** not found. Use `+players` to browse.")
    uid   = str(member.id)
    squad = load_json(SQUAD_FILE)
    cards = squad.get(uid, [])
    idx   = next((i for i, c in enumerate(cards) if c['name'] == name), None)
    if idx is None:
        return await ctx.send(f"❌ **{name}** is not in {member.display_name}'s squad!")
    cards.pop(idx)
    squad[uid] = cards
    save_json(squad, SQUAD_FILE)
    rarity = data['rarity']
    embed = discord.Embed(
        title="🗑️ Player Removed!",
        description=f"**{name}** was removed from {member.mention}'s squad by admin.",
        color=0xE74C3C
    )
    embed.add_field(name="⭐ Rarity",  value=f"{RARITY_EMOJI[rarity]} {rarity}", inline=True)
    embed.add_field(name="🏏 Team",    value=data['team'],                        inline=True)
    embed.add_field(name="🌍 Country", value=data['country'],                     inline=True)
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────
# SELL — confirmation view then execute
# ─────────────────────────────────────────────
class SellConfirmView(discord.ui.View):
    def __init__(self, seller_id: int, player_name: str, pdata: dict):
        super().__init__(timeout=30)
        self.seller_id   = seller_id
        self.player_name = player_name
        self.pdata       = pdata
        self.sell_price  = int(pdata['value'] * SELL_PCT)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.seller_id:
            await interaction.response.send_message("❌ Not your sale!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirm Sale", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid   = str(self.seller_id)
        squad = load_json(SQUAD_FILE)
        cards = squad.get(uid, [])
        idx   = next((i for i, c in enumerate(cards) if c['name'] == self.player_name), None)
        if idx is None:
            await interaction.response.edit_message(
                content=f"❌ **{self.player_name}** is no longer in your squad!",
                embed=None, view=None)
            return
        cards.pop(idx)
        squad[uid] = cards
        save_json(squad, SQUAD_FILE)

        b = get_balance(uid)
        b['coins'] += self.sell_price
        set_balance(uid, b['coins'], b['tickets'])

        rarity = self.pdata['rarity']
        em = discord.Embed(title="💰 Player Sold!", description=f"**{self.player_name}** has left your squad.", color=0xE67E22)
        em.add_field(name="⭐ Rarity",      value=f"{RARITY_EMOJI[rarity]} {rarity}", inline=True)
        em.add_field(name="💸 Sold For",    value=f"{self.sell_price:,} 🪙",          inline=True)
        em.add_field(name="🪙 New Balance", value=f"{b['coins']:,} coins",            inline=True)
        em.set_footer(text=f"Sell price = 60% of card value ({self.pdata['value']:,} coins)")
        await interaction.response.edit_message(content=None, embed=em, view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"❌ Sale of **{self.player_name}** cancelled.", embed=None, view=None)
        self.stop()

@bot.command(name='sell')
async def sell(ctx, *, player_name: str):
    """Sell a player from your squad for 60% of their value. Usage: -sell Virat Kohli"""
    uid = str(ctx.author.id)
    name, pdata = find_player(player_name)
    if not name:
        key  = player_name.strip().lower()
        sugg = [PLAYER_LOOKUP[n] for n in PLAYER_LOOKUP if key in n][:4]
        msg  = f"❌ Player **{player_name}** not found."
        if sugg: msg += f"\nDid you mean: {', '.join(sugg)}?"
        return await ctx.send(msg)

    squad = load_json(SQUAD_FILE)
    cards = squad.get(uid, [])
    idx   = next((i for i, c in enumerate(cards) if c['name'] == name), None)
    if idx is None:
        return await ctx.send(f"❌ You don't have **{name}** in your squad!")

    sell_price = int(pdata['value'] * SELL_PCT)
    rarity     = pdata['rarity']
    b          = get_balance(uid)

    em = discord.Embed(
        title="💸 Confirm Sale",
        description=f"Are you sure you want to sell **{name}**?",
        color=0xE67E22
    )
    em.add_field(name="⭐ Rarity",     value=f"{RARITY_EMOJI[rarity]} {rarity}", inline=True)
    em.add_field(name=f"{ROLE_META[pdata['role']]['emoji']} Role",
                 value=ROLE_META[pdata['role']]['label'],                         inline=True)
    em.add_field(name="🏏 Team",       value=pdata['team'],                       inline=True)
    em.add_field(name="💎 Card Value", value=f"{pdata['value']:,} 🪙",            inline=True)
    em.add_field(name="💸 You'll Get", value=f"**{sell_price:,} 🪙** (60%)",      inline=True)
    em.add_field(name="🪙 Balance",    value=f"{b['coins']:,} coins",             inline=True)
    em.set_footer(text="Expires in 30 seconds.")
    await ctx.send(embed=em, view=SellConfirmView(ctx.author.id, name, pdata))

# ─────────────────────────────────────────────
# BUNDLE — select pack with buttons, confirm, buy → pending
# ─────────────────────────────────────────────
PACK_CONFIG = {
    "IPL Pack":        {"cost":2,"pool":"ipl",  "emoji":"🏏","desc":"IPL players only · 20 Legendary/Epic/Rare/Common"},
    "T20 WC 2026 Pack":{"cost":3,"pool":"t20wc","emoji":"🌍","desc":"17 curated WC 2026 squad players"},
}

class PackConfirmView(discord.ui.View):
    """Step 2 — confirm the pack purchase after seeing the price."""
    def __init__(self, buyer_id: int, pack_name: str):
        super().__init__(timeout=30)
        self.buyer_id  = buyer_id
        self.pack_name = pack_name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("❌ Not your purchase!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirm Purchase", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg  = PACK_CONFIG[self.pack_name]
        uid  = str(self.buyer_id)
        b    = get_balance(uid)
        cost = cfg['cost']
        if b['tickets'] < cost:
            await interaction.response.edit_message(
                content=f"❌ Not enough tickets! Need **{cost}** 🎫 but you have **{b['tickets']}**.",
                embed=None, view=None)
            return
        b['tickets'] -= cost
        set_balance(uid, b['coins'], b['tickets'])

        pending = load_json(PENDING_FILE)
        if uid not in pending: pending[uid] = []
        pending[uid].append({"pack":self.pack_name,"pool":cfg['pool'],"purchased":datetime.now().isoformat()})
        save_json(pending, PENDING_FILE)

        em = discord.Embed(
            title=f"✅ {cfg['emoji']} {self.pack_name} Purchased!",
            description="Your pack is in your inventory! Use **`+open`** to reveal your player.",
            color=0x00ff00
        )
        em.add_field(name="💸 Cost",        value=f"{cost} 🎫",              inline=True)
        em.add_field(name="🎫 Remaining",   value=f"{b['tickets']} tickets", inline=True)
        em.set_footer(text="Use -open any time to reveal your player!")
        await interaction.response.edit_message(content=None, embed=em, view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"❌ Purchase of **{self.pack_name}** cancelled.", embed=None, view=None)
        self.stop()

class BundleSelectView(discord.ui.View):
    """Step 1 — pick which pack you want."""
    def __init__(self, buyer_id: int):
        super().__init__(timeout=30)
        self.buyer_id = buyer_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("❌ Not your menu!", ephemeral=True)
            return False
        return True

    async def _show_confirm(self, interaction: discord.Interaction, pack_name: str):
        cfg = PACK_CONFIG[pack_name]
        uid = str(self.buyer_id)
        b   = get_balance(uid)
        em  = discord.Embed(
            title=f"🛒 Confirm: {cfg['emoji']} {pack_name}",
            description=f"Review the details before purchasing.",
            color=0xffaa00
        )
        em.add_field(name="💸 Cost",       value=f"{cfg['cost']} 🎫",     inline=True)
        em.add_field(name="🎫 You Have",   value=f"{b['tickets']} tickets",inline=True)
        em.add_field(name="📦 Contents",   value=cfg['desc'],              inline=False)
        em.set_footer(text="Expires in 30 seconds.")
        await interaction.response.edit_message(content=None, embed=em,
                                                view=PackConfirmView(self.buyer_id, pack_name))
        self.stop()

    @discord.ui.button(label="🏏 IPL Pack — 2 🎫", style=discord.ButtonStyle.primary)
    async def ipl_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_confirm(interaction, "IPL Pack")

    @discord.ui.button(label="🌍 T20 WC 2026 Pack — 3 🎫", style=discord.ButtonStyle.success)
    async def t20wc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_confirm(interaction, "T20 WC 2026 Pack")

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)
        self.stop()

@bot.command(name='bundle')
async def bundle(ctx):
    """Browse and purchase a pack. Use -open afterwards to reveal your player."""
    uid = str(ctx.author.id)
    b   = get_balance(uid)
    embed = discord.Embed(
        title="🎁 Choose Your Pack",
        description="Select a pack to purchase. You can open it any time with **`+open`**.",
        color=0x00aaff
    )
    embed.add_field(name="🏏 IPL Pack",          value="IPL players only\n**Cost: 2 🎫**",  inline=True)
    embed.add_field(name="🌍 T20 WC 2026 Pack",  value="World Cup stars\n**Cost: 3 🎫**",   inline=True)
    embed.add_field(name="🎫 Your Tickets",       value=f"**{b['tickets']}** available",     inline=False)
    embed.set_footer(text="Packs stay in your inventory until you -open them!")
    view = BundleSelectView(ctx.author.id)
    await ctx.send(embed=embed, view=view)

@bot.command(name='open')
async def open_pack_cmd(ctx):
    """Open your oldest purchased pack and reveal the player."""
    uid     = str(ctx.author.id)
    pending = load_json(PENDING_FILE)
    packs   = pending.get(uid, [])

    if not packs:
        return await ctx.send("📦 You have no pending packs! Use `+bundle` to purchase one.")

    entry = packs.pop(0)
    pending[uid] = packs
    save_json(pending, PENDING_FILE)

    pack_name = entry['pack']
    pool = IPL_PLAYERS if entry['pool'] == 'ipl' else T20_WC_PLAYERS

    player_name = weighted_random_player(pool)
    pdata       = pool[player_name]
    rarity      = pdata['rarity']

    add_to_squad(uid, player_name, pack_name)

    bundles_data = load_json(BUNDLES_FILE)
    bundles_data["active_bundles"].append({
        "player": player_name, "owner": uid,
        "pack": pack_name, "timestamp": datetime.now().isoformat()
    })
    save_json(bundles_data, BUNDLES_FILE)

    embed = discord.Embed(title=f"🎁 {pack_name} Opened!", color=RARITY_COLORS[rarity])
    embed.add_field(name="🏆 You got!", value=f"**{player_name}**",                     inline=False)
    embed.add_field(name="⭐ Rarity",   value=f"{RARITY_EMOJI[rarity]} {rarity}",       inline=True)
    embed.add_field(name=f"{ROLE_META[pdata['role']]['emoji']} Role", value=ROLE_META[pdata['role']]['label'], inline=True)
    embed.add_field(name="🏏 Team",     value=pdata['team'],                             inline=True)
    embed.add_field(name="🌍 Country",  value=pdata['country'],                          inline=True)
    embed.add_field(name="💎 Value",    value=f"{pdata['value']:,} coins",               inline=True)
    remaining = len(packs)
    embed.set_footer(text=f"Added to your squad! {remaining} pack(s) still pending." if remaining else "Added to your squad! Use -bundle for more.")

    img_path = PLAYER_IMAGES.get(player_name)
    if img_path and os.path.exists(img_path):
        fn = os.path.basename(img_path)
        embed.set_image(url=f"attachment://{fn}")
        await ctx.send(embed=embed, file=discord.File(img_path, filename=fn))
    else:
        await ctx.send(embed=embed)

@bot.command(name='mypacks')
async def my_packs(ctx):
    """Check your unopened packs."""
    uid     = str(ctx.author.id)
    pending = load_json(PENDING_FILE)
    packs   = pending.get(uid, [])
    if not packs:
        return await ctx.send("📦 No pending packs. Use `+bundle` to buy one!")
    embed = discord.Embed(title="📦 Your Pending Packs", color=0x00aaff,
                          description=f"You have **{len(packs)}** unopened pack(s). Use `+open` to reveal!")
    for i, p in enumerate(packs, 1):
        cfg = PACK_CONFIG.get(p['pack'], {})
        embed.add_field(name=f"#{i} — {cfg.get('emoji','🎁')} {p['pack']}",
                        value=f"Purchased: {p['purchased'][:10]}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='activebundles')
async def active_bundles(ctx):
    data   = load_json(BUNDLES_FILE)
    active = data.get("active_bundles", [])
    if not active:
        return await ctx.send("📦 No recent opens!")
    embed = discord.Embed(title="📦 Recent Opens", color=0x0099ff)
    for b in active[-8:]:
        embed.add_field(name=b['player'],
                        value=f"<@{b['owner']}> • {b.get('pack','Pack')}", inline=False)
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────
# SQUAD
# ─────────────────────────────────────────────
@bot.command(name='xi', aliases=['XI','playing11'])
async def xi_cmd(ctx, member: discord.Member = None):
    """View your Playing XI. Usage: +xi or +xi @user"""
    user = member or ctx.author
    uid  = str(user.id)

    # Get user squad
    squad_data = load_json(SQUAD_FILE)
    user_squad = squad_data.get(uid, {}).get("players", [])

    # Also include owned cards
    owned = load_json("owned_cards.json") if os.path.exists("owned_cards.json") else {}
    user_cards = owned.get(uid, [])
    cards_db   = load_cards()

    em = discord.Embed(
        title=f"🏏 {user.display_name}'s Playing XI",
        color=0x1a8cff)
    em.set_thumbnail(url=user.display_avatar.url)

    if not user_squad and not user_cards:
        em.description = "❌ No players in squad yet! Use `+buy` to get players."
        return await ctx.send(embed=em)

    # Show squad players
    lines = []
    for i, p in enumerate(user_squad[:11], 1):
        pname = p if isinstance(p, str) else p.get("name","?")
        pdata = ALL_PLAYERS.get(pname, {})
        role_e = {"BOWL":"🎯","ALR":"⚡","BAT":"🏏","WK":"🧤"}.get(pdata.get("role","BAT"),"🏏")
        lines.append(f"`{i:2d}.` {role_e} **{pname}**")

    # Show owned cards too
    for cid in user_cards[:max(0, 11-len(lines))]:
        c = cards_db.get(cid)
        if c:
            cinfo = CARD_TYPES.get(_resolve_card_type(c.get("type","base")), CARD_TYPES["base"])
            lines.append(f"`  ` {cinfo['badge']} **{c['name']}** *(Card)*")

    if lines:
        em.description = "\n".join(lines)
    else:
        em.description = "❌ Squad is empty."

    total = len(user_squad) + len(user_cards)
    em.set_footer(text=f"Total collection: {total} players/cards")
    await ctx.send(embed=em)


@bot.command(name='squad')
async def squad(ctx, member: discord.Member = None):
    """View your player collection. Usage: -squad or -squad @user"""
    user  = member or ctx.author
    uid   = str(user.id)
    data  = load_json(SQUAD_FILE)
    cards = data.get(uid, [])

    if not cards:
        hint = "You have" if user == ctx.author else f"{user.display_name} has"
        return await ctx.send(f"📋 {hint} no players yet! Use `+bundle` or `+buy <name>` to get started.")

    grouped_rarity = {r:[] for r in RARITY_ORDER}
    role_count     = {"BAT":0,"BOWL":0,"WK":0,"ALR":0}
    total_value    = 0

    for c in cards:
        grouped_rarity[c['rarity']].append(c['name'])
        role_count[c.get('role','BAT')] += 1
        total_value += c.get('value', 0)

    embed = discord.Embed(
        title=f"📋 {user.display_name}'s Squad",
        description=(
            f"**{len(cards)}** cards · Total value: **{total_value:,}** 🪙\n"
            f"🏏 {role_count['BAT']} BAT · 🎯 {role_count['BOWL']} BOWL · "
            f"🧤 {role_count['WK']} WK · ⚡ {role_count['ALR']} ALR"
        ),
        color=0x00aaff
    )
    for rarity in RARITY_ORDER:
        names = grouped_rarity[rarity]
        if not names: continue
        counted = {}
        for n in names: counted[n] = counted.get(n,0)+1
        display = ", ".join(f"{n} x{c}" if c>1 else n for n,c in counted.items())
        if len(display) > 1000: display = display[:997]+"…"
        embed.add_field(name=f"{RARITY_EMOJI[rarity]} {rarity} ({len(names)})", value=display, inline=False)
    embed.set_footer(text="-battershower · -bowlershower · -wkshower · -alrshower to browse by role")
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────
# ROLE SHOWROOMS (also usable inside squad-style breakdown)
# ─────────────────────────────────────────────
async def role_showroom(ctx, role_key: str):
    meta     = ROLE_META[role_key]
    filtered = {k:v for k,v in ALL_PLAYERS.items() if v["role"]==role_key}
    grouped  = {r:[] for r in RARITY_ORDER}
    for name, d in filtered.items(): grouped[d["rarity"]].append((name, d["value"]))

    embed = discord.Embed(
        title=f"{meta['emoji']} {meta['label']} Showroom",
        description=f"**{len(filtered)}** players · Buy any with `+buy <name>`",
        color=meta["color"]
    )
    entries = [
        (name, get_player_ovr(d['value'], name), d['team']) for name, d in filtered.items()
    ]
    if entries:
        lines = "\n".join(
            f"**{n}** — {ovr} OVR · {team}"
            for n, ovr, team in sorted(entries, key=lambda x: -x[1])
        )
        if len(lines) > 1024:
            lines = lines[:1020] + "…"
        embed.add_field(name=f"{meta['emoji']} {meta['label']} ({len(entries)})", value=lines, inline=False)
    else:
        embed.add_field(name=f"{meta['emoji']} {meta['label']}", value="No players available.", inline=False)
    embed.set_footer(text="Use -buy <player name> to purchase")
    await ctx.send(embed=embed)

@bot.command(name='autobuild')
async def autobuild(ctx, member: discord.Member = None):
    """Auto-build a best XI from your squad."""
    user = member or ctx.author
    uid  = str(user.id)
    squad = load_json(SQUAD_FILE).get(uid, [])
    if not squad:
        hint = "You have" if user == ctx.author else f"{user.display_name} has"
        return await ctx.send(f"❌ {hint} no players yet! Use `+bundle` or `+buy <name>` first.")

    by_role = {"WK": [], "BAT": [], "ALR": [], "BOWL": []}
    for card in squad:
        role = card.get('role', 'BAT')
        by_role.setdefault(role, []).append(card)

    for role_cards in by_role.values():
        role_cards.sort(key=lambda c: c.get('value', 0), reverse=True)

    xi = []
    if by_role['WK']:
        xi.append(by_role['WK'].pop(0))
    xi.extend(by_role['BAT'][:4]); by_role['BAT'] = by_role['BAT'][4:]
    xi.extend(by_role['ALR'][:2]); by_role['ALR'] = by_role['ALR'][2:]
    xi.extend(by_role['BOWL'][:3]); by_role['BOWL'] = by_role['BOWL'][3:]

    remaining = [card for cards in by_role.values() for card in cards]
    remaining.sort(key=lambda c: c.get('value', 0), reverse=True)
    while len(xi) < 11 and remaining:
        xi.append(remaining.pop(0))

    if not xi:
        return await ctx.send("❌ Could not auto-build an XI from your squad.")

    total_ovr = sum(get_player_ovr(c.get('value', 0), c.get('name')) for c in xi)
    role_groups = {"BAT": [], "BOWL": [], "WK": [], "ALR": []}
    for c in xi:
        role_groups[c.get('role', 'BAT')].append(c)

    lines = []
    for role in ["WK", "BAT", "ALR", "BOWL"]:
        cards = role_groups[role]
        if not cards:
            continue
        lines.append(f"**{ROLE_META[role]['emoji']} {ROLE_META[role]['label']}**")
        for card in cards:
            lines.append(f"• **{card['name']}** — {get_player_ovr(card.get('value', 0), card['name'])} OVR · {card['team']}")
        lines.append("\n")

    embed = discord.Embed(
        title=f"🏏 {user.display_name}'s Auto-built XI",
        description=(
            f"**{len(xi)}** players · Total OVR: **{total_ovr}**\n"
            f"Composition: {len(role_groups['BAT'])} BAT · {len(role_groups['BOWL'])} BOWL · {len(role_groups['ALR'])} ALR · {len(role_groups['WK'])} WK"
        ),
        color=0x00aaff
    )
    embed.add_field(name="Auto-built XI", value="\n".join(lines).strip(), inline=False)
    embed.set_footer(text="This XI removes rarity grouping and uses OVR values.")
    await ctx.send(embed=embed)

@bot.command(name='battershower')
async def batter_shower(ctx):   await role_showroom(ctx,"BAT")

@bot.command(name='bowlershower')
async def bowler_shower(ctx):   await role_showroom(ctx,"BOWL")

@bot.command(name='wkshower')
async def wk_shower(ctx):       await role_showroom(ctx,"WK")

@bot.command(name='alrshower')
async def alr_shower(ctx):      await role_showroom(ctx,"ALR")

# ─────────────────────────────────────────────
# PLAYERS BROWSER
# ─────────────────────────────────────────────
@bot.command(name='players')
async def list_players(ctx, rarity: str = None):
    """Browse all players. Filter: -players Legendary / Epic / Rare / Common"""
    if rarity:
        rarity = rarity.capitalize()
        if rarity not in RARITY_ORDER:
            return await ctx.send("❌ Valid rarities: `Legendary`, `Epic`, `Rare`, `Common`")
        filtered = {k:v for k,v in ALL_PLAYERS.items() if v['rarity']==rarity}
    else:
        filtered = ALL_PLAYERS

    grouped = {r:[] for r in RARITY_ORDER}
    for name, d in filtered.items():
        grouped[d['rarity']].append(f"{name} ({d['value']}🪙)")

    embed = discord.Embed(
        title="🏏 All Cricketers",
        description=f"**{len(filtered)}** players · `+buy <name>` to purchase",
        color=0x00ff00
    )
    for r in RARITY_ORDER:
        names = grouped[r]
        if not names: continue
        chunk = ", ".join(names[:15])
        if len(names)>15: chunk += f" … +{len(names)-15} more"
        embed.add_field(name=f"{RARITY_EMOJI[r]} {r} ({len(names)})", value=chunk, inline=False)
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────
# SPORTS NEXUS MARKET SHOP
# ─────────────────────────────────────────────
# Fixed shop items — images stored as base64 in shop_cards.json
SHOP_ITEMS = [
    {
        "id":    "coetzee_odiwc",
        "name":  "Gerald Coetzee",
        "type":  "ODI WC Special",
        "role":  "RH Fast Bowler",
        "bat":   54, "ovr": 90, "bowl": 90,
        "price_coins":   500_000,
        "price_tickets": None,
        "card_file": "shop_card_coetzee.png",
    },
    {
        "id":    "madushanka_odiwc",
        "name":  "Dilshan Madushanka",
        "type":  "ODI WC Special",
        "role":  "LH Fast Bowler",
        "bat":   32, "ovr": 92, "bowl": 93,
        "price_coins":   750_000,
        "price_tickets": None,
        "card_file": "shop_card_madushanka.png",
    },
    {
        "id":    "markram_odiwc",
        "name":  "Aiden Markram",
        "type":  "ODI WC Special",
        "role":  "RH Batsman",
        "bat":   93, "ovr": 92, "bowl": 60,
        "price_coins":   600_000,
        "price_tickets": 40,
        "card_file": "shop_card_markram.png",
    },
]
SHOP_CARD_FILES = [it["card_file"] for it in SHOP_ITEMS]
SHOP_BANNER_FILE = "shop_banner.png"
SHOP_PURCHASES_FILE = "shop_purchases.json"


def generate_shop_banner():
    """Generate the Sports Nexus Market banner PNG — high quality 3072x2048 matching reference."""
    if not PILLOW_AVAILABLE:
        return False
    from PIL import ImageFilter
    W, H = 3072, 2048

    # ── Background: grass cricket ground ─────────────────────────────
    bg = Image.new("RGB", (W, H))
    draw_bg = ImageDraw.Draw(bg)
    for y in range(int(H * 0.42)):
        ratio = y / (H * 0.42)
        r = int(100 + 60 * ratio); g = int(160 + 40 * ratio); b_c = int(110 + 80 * ratio)
        draw_bg.line([(0, y), (W, y)], fill=(r, g, b_c))
    for y in range(int(H * 0.42), H):
        ratio = (y - H * 0.42) / (H * 0.58)
        r = int(55 + 15 * ratio); g = int(110 + 20 * (1 - ratio)); b_c = 28
        draw_bg.line([(0, y), (W, y)], fill=(r, g, b_c))
    # Grass stripes
    for i in range(10):
        sy = int(H * 0.48) + i * 90
        draw_bg.rectangle([0, sy, W, sy + 45], fill=(62, 112, 32) if i % 2 == 0 else (70, 125, 38))
    # Trees
    for coords in [(-80,80,320,500),(180,40,480,420),(2700,60,3150,480),(2500,100,2850,450)]:
        x0,y0,x1,y1 = [int(c) for c in coords]
        draw_bg.ellipse([x0,y0,x1,y1], fill=(45,90,30))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=3))

    canvas = bg.copy()
    draw = ImageDraw.Draw(canvas)

    # ── Top bar ───────────────────────────────────────────────────────
    TOP_H = 118
    draw.rectangle([0, 0, W, TOP_H], fill=(70, 125, 148))
    from datetime import date as _date
    today_str = _date.today().strftime("%B %d, %Y")
    fnt_date = _fnt(46, bold=False)
    draw.text((W - 440, 36), today_str, font=fnt_date, fill=(255, 255, 255))
    fnt_nav = _fnt(56)
    for txt, cx in [("PLAY", 520), ("PURCHASE", 1340), ("SEASON 5", 2260)]:
        tw = draw.textlength(txt, font=fnt_nav)
        if txt == "PURCHASE":
            draw.rounded_rectangle([cx-tw//2-28, 14, cx+tw//2+28, TOP_H-14],
                                    radius=12, fill=(50,105,128), outline=(0,200,220), width=4)
        draw.text((cx - tw // 2, 30), txt, font=fnt_nav, fill=(255, 255, 255))
    draw.line([(900, 18), (900, 100)], fill=(200, 225, 230), width=3)
    draw.line([(1900, 18), (1900, 100)], fill=(200, 225, 230), width=3)

    # ── Title ─────────────────────────────────────────────────────────
    ty0, ty1 = 138, 290
    draw.rounded_rectangle([360, ty0, 2712, ty1], radius=38,
                            fill=(42, 108, 132), outline=(0, 190, 215), width=5)
    fnt_title = _fnt(124)
    title = "SPORTS NEXUS MARKET"
    tw = draw.textlength(title, font=fnt_title)
    draw.text(((W - tw) // 2, ty0 + 8), title, font=fnt_title, fill=(255, 255, 255))

    # ── Cards ─────────────────────────────────────────────────────────
    card_h = 1400
    card_w  = int(card_h * 1024 / 1536)
    gap = (W - 3 * card_w - 80) // 4
    card_y0 = 315
    fnt_price = _fnt(72)
    fnt_tic   = _fnt(56, bold=False)

    for i, item in enumerate(SHOP_ITEMS):
        cx = gap + i * (card_w + gap) + 40
        cy = card_y0
        fpath = item["card_file"]
        # Cyan glow
        for off, col in [(22, (0,210,230)), (14, (0,180,200)), (7, (0,150,170))]:
            draw.rectangle([cx-off, cy-off, cx+card_w+off, cy+card_h+off], fill=col)
        draw.rectangle([cx-4, cy-4, cx+card_w+4, cy+card_h+4], fill=(255,255,255))
        if os.path.exists(fpath):
            try:
                cimg = Image.open(fpath).convert("RGB").resize((card_w, card_h), Image.LANCZOS)
                canvas.paste(cimg, (cx, cy))
            except Exception as e:
                print(f"[Shop banner] card error: {e}")
                draw.rectangle([cx,cy,cx+card_w,cy+card_h], fill=(30,30,60))
        else:
            draw.rectangle([cx,cy,cx+card_w,cy+card_h], fill=(30,30,60))
            draw.text((cx+20, cy+card_h//2), item["name"][:15], font=_fnt(40), fill=(200,200,200))

        py = cy + card_h + 28
        cs = f"{item['price_coins']:,} 🪙"
        pw = draw.textlength(cs, font=fnt_price)
        draw.text((cx+(card_w-pw)//2+2, py+2), cs, font=fnt_price, fill=(0,0,0))
        draw.text((cx+(card_w-pw)//2,   py),   cs, font=fnt_price, fill=(255,255,255))
        if item.get("price_tickets"):
            ts = f"or  {item['price_tickets']} 🎫"
            tw2 = draw.textlength(ts, font=fnt_tic)
            draw.text((cx+(card_w-tw2)//2, py+92), ts, font=fnt_tic, fill=(150,220,255))

    # ── Bottom bar ────────────────────────────────────────────────────
    boty = H - 155
    draw.rectangle([0, boty, W, H], fill=(48, 92, 26))
    fnt_foot = _fnt(70)
    foot = "Market resets everyday at 12:00 AM IST, don't miss out!"
    fw = draw.textlength(foot, font=fnt_foot)
    draw.text(((W - fw) // 2, boty + 42), foot, font=fnt_foot, fill=(255, 255, 255))

    canvas.save(SHOP_BANNER_FILE)
    return True


class ShopConfirmView(discord.ui.View):
    """Confirm/cancel a shop purchase."""
    def __init__(self, buyer_id, item):
        super().__init__(timeout=30)
        self.buyer_id = buyer_id
        self.item     = item

    @discord.ui.button(emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.buyer_id:
            return await interaction.response.send_message("❌ Not your purchase!", ephemeral=True)
        b           = get_balance(str(self.buyer_id))
        can_coins   = b["coins"]   >= self.item["price_coins"]
        can_tickets = self.item.get("price_tickets") and b["tickets"] >= self.item["price_tickets"]
        if not can_coins and not can_tickets:
            return await interaction.response.edit_message(content="❌ Insufficient balance!", embed=None, view=None)
        if can_coins:
            b["coins"] -= self.item["price_coins"]; paid_str = f"{self.item['price_coins']:,} 🪙"
        else:
            b["tickets"] -= self.item["price_tickets"]; paid_str = f"{self.item['price_tickets']} 🎟️"
        set_balance(str(self.buyer_id), b["coins"], b["tickets"])
        purch = load_json(SHOP_PURCHASES_FILE) if os.path.exists(SHOP_PURCHASES_FILE) else {}
        purch.setdefault(str(self.buyer_id), []).append(self.item["id"])
        save_json(purch, SHOP_PURCHASES_FILE)
        em = discord.Embed(title="✅ Purchase Successful!",
            description=f"**{self.item['name']}** ({self.item['type']}) is now yours!", color=0x00e676)
        em.add_field(name="BAT",  value=str(self.item["bat"]),  inline=True)
        em.add_field(name="OVR",  value=str(self.item["ovr"]),  inline=True)
        em.add_field(name="BOWL", value=str(self.item["bowl"]), inline=True)
        em.add_field(name="Paid", value=paid_str, inline=True)
        em.add_field(name="🪙 Remaining", value=f"{b['coins']:,}", inline=True)
        await interaction.response.edit_message(content=None, embed=em, view=None)
        self.stop()

    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(content="❌ Purchase cancelled.", embed=None, view=None)
        self.stop()


class ShopBuyView(discord.ui.View):
    """Select a player dropdown — matching Cricket Guru Market style."""
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx
        options = []
        for item in SHOP_ITEMS:
            price_str = f"{item['price_coins']//1000}k coins"
            if item.get("price_tickets"):
                price_str += f" / {item['price_tickets']} tics"
            options.append(discord.SelectOption(
                label=item["name"],
                value=item["id"],
                description=f"{item['type']} · OVR {item['ovr']} · {price_str}"[:100]
            ))
        sel = discord.ui.Select(placeholder="Select a player…", options=options)
        sel.callback = self._on_select
        self.add_item(sel)

    async def _on_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item    = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
        if not item:
            return await interaction.response.send_message("❌ Item not found.", ephemeral=True)
        uid   = str(interaction.user.id)
        b     = get_balance(uid)
        purch = load_json(SHOP_PURCHASES_FILE) if os.path.exists(SHOP_PURCHASES_FILE) else {}
        if item["id"] in purch.get(uid, []):
            return await interaction.response.send_message(
                f"❌ You already own **{item['name']}**!", ephemeral=True)
        can_coins   = b["coins"]   >= item["price_coins"]
        can_tickets = item.get("price_tickets") and b["tickets"] >= item["price_tickets"]
        price_str   = f"{item['price_coins']:,} 🪙"
        if item.get("price_tickets"): price_str += f"  or  {item['price_tickets']} 🎟️"
        if not can_coins and not can_tickets:
            return await interaction.response.send_message(
                f"❌ **Insufficient balance!**\nNeed {price_str}\n"
                f"You have **{b['coins']:,}** 🪙 and **{b['tickets']:,}** 🎟️", ephemeral=True)
        em = discord.Embed(title=f"🛒 {item['name']}  —  {item['type']}",
            description=f"{item['role']}", color=0x00c853)
        em.add_field(name="BAT",  value=str(item["bat"]),  inline=True)
        em.add_field(name="OVR",  value=str(item["ovr"]),  inline=True)
        em.add_field(name="BOWL", value=str(item["bowl"]), inline=True)
        em.add_field(name="💰 Price", value=price_str, inline=False)
        em.add_field(name="🪙 Coins", value=f"{b['coins']:,}", inline=True)
        em.add_field(name="🎟️ Tics",  value=f"{b['tickets']:,}", inline=True)
        em.set_footer(text="Confirm ✅ to buy  ·  ❌ to cancel")
        fpath = item.get("card_file","")
        confirm_view = ShopConfirmView(interaction.user.id, item)
        if os.path.exists(fpath):
            await interaction.response.send_message(embed=em, view=confirm_view,
                file=discord.File(fpath, filename="card.png"), ephemeral=True)
        else:
            await interaction.response.send_message(embed=em, view=confirm_view, ephemeral=True)


@bot.command(name='shop')
async def shop(ctx):
    """Browse the Sports Nexus Market."""
    loop = asyncio.get_event_loop()
    ok   = await loop.run_in_executor(None, generate_shop_banner)
    if ok and os.path.exists(SHOP_BANNER_FILE):
        em = discord.Embed(
            title="🏪 Sports Nexus Market",
            description="Pick a card to add to your collection!\nShop resets at **12:00 AM IST** daily.",
            color=0x00c853)
        em.set_image(url="attachment://shop_banner.png")
        await ctx.send(embed=em,
                       file=discord.File(SHOP_BANNER_FILE, filename="shop_banner.png"),
                       view=ShopBuyView(ctx))
    else:
        # Fallback text embed
        em = discord.Embed(title="🏪 Sports Nexus Market", color=0x00c853)
        for item in SHOP_ITEMS:
            price = f"{item['price_coins']:,} 🪙"
            if item.get("price_tickets"):
                price += f"  or  {item['price_tickets']} 🎟️"
            em.add_field(name=f"{item['name']}  ({item['type']})",
                         value=f"BAT {item['bat']} | OVR {item['ovr']} | BOWL {item['bowl']}\n💰 {price}",
                         inline=False)
        await ctx.send(embed=em, view=ShopBuyView(ctx))


@bot.command(name='setprice')
async def set_price(ctx, price:int, *, name:str):
    """(Admin) Set/update the price of an existing card.\nUsage: +setprice 2100000 Rohit Sharma"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admins only!")
    if price < 0:
        return await ctx.send("❌ Price must be positive!")
    cards = load_cards()
    matches = {k:v for k,v in cards.items() if name.lower() in v["name"].lower()}
    if not matches:
        return await ctx.send(f"❌ No card found matching **{name}**.")
    if len(matches) > 1:
        em = discord.Embed(title="⚠️ Multiple matches — be more specific:", color=0xff9900)
        for cid, c in list(matches.items())[:8]:
            em.add_field(name=c["name"], value=f"ID: `{cid}`", inline=False)
        return await ctx.send(embed=em)
    cid, c = list(matches.items())[0]
    old_price = c.get("price", 0)
    cards[cid]["price"] = price
    save_cards(cards)
    em = discord.Embed(title="✅ Price Updated!", color=0x00e676)
    em.add_field(name="Card",      value=c["name"],          inline=True)
    em.add_field(name="Old Price", value=f"{old_price:,} 🪙", inline=True)
    em.add_field(name="New Price", value=f"{price:,} 🪙",     inline=True)
    await ctx.send(embed=em)


@bot.command(name='setshopcard')
async def set_shop_card(ctx, *, player: str):
    """(Admin) Upload a card image for a shop slot.\nUsage: +setshopcard <slot_number or player name>  (attach PNG)\nSlot numbers match the order in SHOP_ITEMS (1, 2, 3...)"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admins only!")
    if not ctx.message.attachments:
        return await ctx.send("❌ Attach the card PNG!")
    key = player.strip().lower()
    # Try slot number first
    matched_fname = None
    try:
        idx = int(key) - 1
        if 0 <= idx < len(SHOP_ITEMS):
            matched_fname = SHOP_ITEMS[idx]["card_file"]
    except ValueError:
        pass
    # Try name match
    if not matched_fname:
        for item in SHOP_ITEMS:
            if key in item["name"].lower():
                matched_fname = item["card_file"]
                break
    if not matched_fname:
        slots = "\n".join(f"`{i+1}` — {it['name']}" for i, it in enumerate(SHOP_ITEMS))
        return await ctx.send(f"❌ Player not found. Available slots:\n{slots}")
    await ctx.message.attachments[0].save(matched_fname)
    await ctx.send(f"✅ Shop card image saved as `{matched_fname}`!")


@bot.command(name='addshopitem')
async def add_shop_item(ctx, name:str, ovr:int, bat:int, bowl:int,
                         price_coins:int, price_tickets:int=0, *, role:str="Batter"):
    """(Admin) Add/update a player in the shop dynamically.\nUsage: +addshopitem "Player Name" <ovr> <bat> <bowl> <price_coins> [price_tickets] [role]\nAttach card PNG to set the image. Saves to shop_items.json for persistence."""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admins only!")
    # Save to dynamic shop file
    dshop = load_json("shop_items_dynamic.json") if os.path.exists("shop_items_dynamic.json") else []
    item_id = name.lower().replace(" ","_") + "_shop"
    card_file = f"shop_card_{name.lower().replace(' ','_')}.png"
    if ctx.message.attachments:
        await ctx.message.attachments[0].save(card_file)
    new_item = {
        "id": item_id, "name": name, "type": "Shop Card", "role": role,
        "bat": bat, "ovr": ovr, "bowl": bowl,
        "price_coins": price_coins,
        "price_tickets": price_tickets if price_tickets > 0 else None,
        "card_file": card_file,
    }
    # Replace if exists
    dshop = [i for i in dshop if i["id"] != item_id]
    dshop.append(new_item)
    save_json(dshop, "shop_items_dynamic.json")
    # Reload SHOP_ITEMS at runtime
    _reload_shop_items()
    em = discord.Embed(title="✅ Shop Item Added!", color=0x00e676)
    em.add_field(name="Player",  value=name,           inline=True)
    em.add_field(name="OVR",     value=str(ovr),        inline=True)
    em.add_field(name="Price",   value=f"{price_coins:,} 🪙", inline=True)
    em.add_field(name="Image",   value="✅ Saved" if ctx.message.attachments else "⚠️ None", inline=True)
    await ctx.send(embed=em)


def _reload_shop_items():
    """Merge static + dynamic shop items."""
    global SHOP_ITEMS
    static = [
        {"id":"coetzee_odiwc","name":"Gerald Coetzee","type":"odiwc",
         "role":"RH Fast Bowler","bat":54,"ovr":90,"bowl":90,
         "price_coins":500_000,"price_tickets":None,"card_file":"shop_card_coetzee.png"},
        {"id":"madushanka_odiwc","name":"Dilshan Madushanka","type":"odiwc",
         "role":"LH Fast Bowler","bat":32,"ovr":92,"bowl":93,
         "price_coins":750_000,"price_tickets":None,"card_file":"shop_card_madushanka.png"},
        {"id":"markram_odiwc","name":"Aiden Markram","type":"odiwc",
         "role":"RH Batsman","bat":93,"ovr":92,"bowl":60,
         "price_coins":600_000,"price_tickets":40,"card_file":"shop_card_markram.png"},
    ]
    try:
        dyn = load_json("shop_items_dynamic.json") if os.path.exists("shop_items_dynamic.json") else []
    except Exception:
        dyn = []
    # Merge: dynamic overrides static if same id
    static_ids = {it["id"] for it in static}
    merged = list(static)
    for d in dyn:
        if d["id"] not in static_ids:
            merged.append(d)
    SHOP_ITEMS[:] = merged


# Load dynamic items at startup
_reload_shop_items()

# ─────────────────────────────────────────────
# BUY — direct player purchase with confirmation
# ─────────────────────────────────────────────
class BuyConfirmView(discord.ui.View):
    def __init__(self, buyer_id, player_name, player_data, price):
        super().__init__(timeout=30)
        self.buyer_id = buyer_id; self.player_name = player_name
        self.player_data = player_data; self.price = price

    async def interaction_check(self, interaction):
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("❌ Not your purchase!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirm Purchase", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        uid = str(self.buyer_id)
        b   = get_balance(uid)
        if b['coins'] < self.price:
            await interaction.response.edit_message(
                content=f"❌ Insufficient coins! Need {self.price:,}, have {b['coins']:,}.",
                embed=None, view=None); return

        b['coins'] -= self.price
        set_balance(uid, b['coins'], b['tickets'])
        add_to_squad(uid, self.player_name, "Direct Buy")

        rarity = self.player_data['rarity']
        em = discord.Embed(title="✅ Player Purchased!",
                           description=f"**{self.player_name}** joined your squad!",
                           color=RARITY_COLORS[rarity])
        em.add_field(name="⭐ Rarity",    value=f"{RARITY_EMOJI[rarity]} {rarity}",  inline=True)
        em.add_field(name="🏏 Team",      value=self.player_data['team'],              inline=True)
        em.add_field(name="🌍 Country",   value=self.player_data['country'],           inline=True)
        em.add_field(name="💰 Paid",      value=f"{self.price:,} 🪙",                 inline=True)
        em.add_field(name="🪙 Remaining", value=f"{b['coins']:,} coins",              inline=True)
        em.set_footer(text="Use -squad to view your collection!")

        img_path = PLAYER_IMAGES.get(self.player_name)
        if img_path and os.path.exists(img_path):
            fn = os.path.basename(img_path)
            em.set_image(url=f"attachment://{fn}")
            await interaction.response.edit_message(content="✅ Purchase confirmed!", embed=None, view=None)
            await interaction.followup.send(embed=em, file=discord.File(img_path, filename=fn))
        else:
            await interaction.response.edit_message(content=None, embed=em, view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(
            content=f"❌ Purchase of **{self.player_name}** cancelled.", embed=None, view=None)
        self.stop()

@bot.command(name='buy', aliases=['gbuy'])
async def buy(ctx, *, query: str):
    """Buy a card by player name. Usage: +buy Rohit Sharma"""
    uid = str(ctx.author.id)

    # First check cards DB (addcard system)
    cards = load_cards()
    matched_card = None
    for cid, c in cards.items():
        if query.strip().lower() in c["name"].lower():
            matched_card = (cid, c)
            break

    if matched_card:
        cid, c = matched_card
        price = c.get("price", 0)
        b     = get_balance(uid)
        if price <= 0:
            return await ctx.send(f"❌ **{c['name']}** has no price set. Ask an admin.")
        
        import base64
        pb = c.get("player_b64","")
        player_bytes = base64.b64decode(pb) if pb else None

        cinfo = CARD_TYPES.get(_resolve_card_type(c.get("type","base")), CARD_TYPES["base"])
        flag  = COUNTRY_FLAGS.get(c["country"],"🌍")

        em = discord.Embed(
            title=f"Sports Nexus : {__import__('datetime').date.today().strftime('%B %d, %Y')}",
            color=cinfo["color"])
        em.add_field(name="Price:", value=f"**{price:,}** 🪙", inline=False)

        view = CardBuyConfirmView(ctx.author.id, cid, c, price)
        # Use the raw saved image (the full card as attached by admin)
        if player_bytes:
            buf = io.BytesIO(player_bytes)
            await ctx.send(embed=em, file=discord.File(buf, filename="card.png"), view=view)
        else:
            em.title = f"{cinfo['badge']} {c['name']}  —  {cinfo['label']}"
            em.description = f"{flag} {c['country']}  ·  {c['style']}"
            await ctx.send(embed=em, view=view)
        return

    # Fallback: old player DB
    player_name, pdata = find_player(query)
    if not player_name:
        key  = query.strip().lower()
        sugg = [PLAYER_LOOKUP[n] for n in PLAYER_LOOKUP if key in n][:5]
        msg  = f"❌ Player **{query}** not found."
        if sugg: msg += f"\nDid you mean: {', '.join(sugg)}?"
        return await ctx.send(msg)

    price = pdata['value']
    b     = get_balance(uid)
    if b['coins'] < price:
        return await ctx.send(
            f"❌ Need **{price:,}** 🪙 for **{player_name}**. You have **{b['coins']:,}** 🪙.")

    em = discord.Embed(title="🛒 Confirm Purchase",
                       description=f"Buy **{player_name}**?", color=0x2ecc71)
    em.add_field(name="💰 Price",   value=f"{price:,} 🪙", inline=True)
    em.add_field(name="🪙 Balance", value=f"{b['coins']:,} coins", inline=True)
    em.set_footer(text="Confirm within 30 seconds.")
    view = BuyConfirmView(ctx.author.id, player_name, pdata, price)
    await ctx.send(embed=em, view=view)


class CardBuyConfirmView(discord.ui.View):
    """Confirm buying a card from the addcard system."""
    def __init__(self, buyer_id, card_id, card_data, price):
        super().__init__(timeout=30)
        self.buyer_id  = buyer_id
        self.card_id   = card_id
        self.card_data = card_data
        self.price     = price

    @discord.ui.button(label="Sign", emoji="✅", style=discord.ButtonStyle.success)
    async def sign(self, interaction:discord.Interaction, button):
        if interaction.user.id != self.buyer_id:
            return await interaction.response.send_message("❌ Not your purchase!", ephemeral=True)
        b = get_balance(str(self.buyer_id))
        if b["coins"] < self.price:
            return await interaction.response.send_message(
                f"❌ Need **{self.price:,}** 🪙, you have **{b['coins']:,}** 🪙.", ephemeral=True)
        b["coins"] -= self.price
        set_balance(str(self.buyer_id), b["coins"], b["tickets"])
        # Record in user owned cards
        owned = load_json("owned_cards.json") if os.path.exists("owned_cards.json") else {}
        owned.setdefault(str(self.buyer_id), []).append(self.card_id)
        save_json(owned, "owned_cards.json")
        em = discord.Embed(title="✅ Card Signed!",
            description=f"**{self.card_data['name']}** is now in your collection!",
            color=0x00e676)
        em.add_field(name="Paid",  value=f"{self.price:,} 🪙", inline=True)
        em.add_field(name="🪙 Left", value=f"{b['coins']:,}",  inline=True)
        await interaction.response.edit_message(content=None, embed=em, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction:discord.Interaction, button):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Promote", emoji="📢", style=discord.ButtonStyle.secondary)
    async def promote(self, interaction:discord.Interaction, button):
        # Post the card publicly for others to see/buy
        await interaction.response.send_message(
            f"📢 **{self.card_data['name']}** is available for **{self.price:,}** 🪙! "
            f"Use `+buy {self.card_data['name']}` to get it.", ephemeral=False)

# ─────────────────────────────────────────────
# MATCH SIMULATION
# ─────────────────────────────────────────────
BALL_OUTCOMES = [0, 1, 2, 3, 4, 6, 'W', 'NB', 'WD']
BALL_WEIGHTS  = [10, 18, 14, 4, 26, 18, 4, 5, 6]  # fallback weights for general simulation
TOTAL_OVERS   = 20
MAX_BOWLER_OVERS = 4
MAX_WICKETS   = 10

OVR_OVERRIDES = {
    "Rohit Sharma": 97,
    "Mitchell Starc": 95,
}

def get_player_ovr(value: int, player_name: str = None) -> int:
    """Convert raw player value into a simulation-friendly OVR between 80 and 99."""
    if player_name and player_name in OVR_OVERRIDES:
        return OVR_OVERRIDES[player_name]
    if value <= 100:
        return 80
    if value >= 600:
        return 99
    return 80 + round((value - 100) * 19 / 500)



class MatchState:
    def __init__(self, channel_id, batting_uid, bowling_uid,
                 batting_name, bowling_name, batting_squad, bowling_squad,
                 bowling_order_batting=None, bowling_order_bowling=None,
                 pitch_type=None, home_team=None):
        self.channel_id   = channel_id
        self.batting_uid  = batting_uid
        self.bowling_uid  = bowling_uid
        self.batting_name = batting_name
        self.bowling_name = bowling_name
        self._inn1_batting = batting_squad[:11]
        self._inn1_bowling = bowling_squad[:11]
        # bowling_order: {bowler_name_lower: [over_numbers]} — team1 bowls in inn2, team2 bowls in inn1
        self._bowling_order_inn1 = bowling_order_bowling or {}  # bowling team's order for inn1
        self._bowling_order_inn2 = bowling_order_batting or {}  # batting team's order for inn2
        self.pitch_type    = pitch_type   # e.g. 'flat', 'green', 'spin', 'dew', 'slow', 'altitude'
        self.home_team     = home_team    # team name string or None
        self.innings       = 1
        self.target        = None
        self.match_bat_stats  = {}
        self.match_bowl_stats = {}
        self.innings_scores   = {}
        self.innings_bat_stats  = {1: {}, 2: {}}   # per-innings bat stats with 'out' field
        self.innings_bowl_stats = {1: {}, 2: {}}   # per-innings bowl stats
        self.commentary      = []
        self.innings_commentary = {1: [], 2: []}
        self.innings_overs   = {1: [], 2: []}
        self._current_over   = []
        self._setup_innings()

    def _setup_innings(self):
        if self.innings == 1:
            batting = self._inn1_batting
            bowling = self._inn1_bowling
            bowling_order = self._bowling_order_inn1
        else:
            batting = self._inn1_bowling
            bowling = self._inn1_batting
            bowling_order = self._bowling_order_inn2

        # Preserve input batting order (user defines the order, e.g. openers first)
        self.batting_order     = [p['name'] for p in batting]
        self.on_strike         = self.batting_order[0] if self.batting_order else 'Batter 1'
        self.non_striker       = self.batting_order[1] if len(self.batting_order) > 1 else 'Batter 2'
        self.available_batters = list(self.batting_order[2:])

        if bowling_order:
            # Use the custom bowling order — map over number → bowler name
            # bowling_order: {bowler_name_lower: [over_numbers]}
            # Build over_to_bowler: {over_num: resolved_name}
            over_to_bowler = {}
            for bname_low, overs in bowling_order.items():
                # Resolve name against bowling squad
                resolved = None
                for p in bowling:
                    if p['name'].lower() == bname_low or bname_low in p['name'].lower():
                        resolved = p['name']
                        break
                if not resolved:
                    # Try find_player
                    fn, _ = find_player(bname_low)
                    resolved = fn or bname_low.title()
                for ov in overs:
                    over_to_bowler[ov] = resolved
            self.over_to_bowler = over_to_bowler
            # bowlers_pool = unique bowlers in order of first appearance
            seen = []
            for ov in sorted(over_to_bowler):
                b = over_to_bowler[ov]
                if b not in seen:
                    seen.append(b)
            self.bowlers_pool = seen
            self.bowler_max_overs = {b: len([o for o in over_to_bowler.values() if o == b])
                                     for b in seen}
        else:
            self.over_to_bowler = {}
            bowlers = sorted([p for p in bowling if p.get('role') == 'BOWL'],
                             key=lambda p: p.get('value', 0), reverse=True)
            all_rounders = sorted([p for p in bowling if p.get('role') == 'ALR'],
                                   key=lambda p: p.get('value', 0), reverse=True)
            bowl_pool = []
            for p in bowlers[:5]:
                bowl_pool.append(p)
            for p in all_rounders:
                if len(bowl_pool) >= 5:
                    break
                if p['name'] not in [b['name'] for b in bowl_pool]:
                    bowl_pool.append(p)
            non_bowlers_used = []
            if not bowl_pool:
                fallback = sorted([p for p in bowling if p.get('role') in ('BAT', 'WK')],
                                  key=lambda p: p.get('value', 0), reverse=True)
                bowl_pool = fallback[:3]
                non_bowlers_used = [p['name'] for p in bowl_pool]
            self.bowlers_pool = [p['name'] for p in bowl_pool]
            self.bowler_max_overs = {}
            for p in bowl_pool:
                if p['name'] in non_bowlers_used:
                    self.bowler_max_overs[p['name']] = 2
                else:
                    self.bowler_max_overs[p['name']] = MAX_BOWLER_OVERS

        self.bowler_overs   = {name: 0 for name in self.bowlers_pool}
        self.current_bowler = None
        self.runs           = 0
        # Impact player support (set externally for interactive mode; defaults for simulate mode)
        self.impact_player_bat  = None
        self.impact_player_bowl = None
        self.impact_used_bat    = False
        self.impact_used_bowl   = False
        self.wickets        = 0
        self.overs          = 0
        self.balls_in_over  = 0
        self.last_ball_was_wicket = False
        self.bat_stats      = {}
        self.bowl_stats     = {}

    def get_batting_uid(self):
        return self.batting_uid if self.innings == 1 else self.bowling_uid

    def get_bowling_uid(self):
        return self.bowling_uid if self.innings == 1 else self.batting_uid

    def get_batting_name(self):
        return self.batting_name if self.innings == 1 else self.bowling_name

    def get_bowling_name(self):
        return self.bowling_name if self.innings == 1 else self.batting_name

    def innings_done(self):
        return self.wickets >= MAX_WICKETS or self.overs >= TOTAL_OVERS

    def chase_won(self):
        return self.innings == 2 and self.target is not None and self.runs >= self.target

    def scoreline(self):
        ov = f"{self.overs}.{self.balls_in_over}" if self.balls_in_over else str(self.overs)
        return f"**{self.runs}/{self.wickets}** ({ov} ov)"

    def _batter_outcome_weights(self):
        batter = self.on_strike or ''
        bowler = self.current_bowler or ''
        role = ALL_PLAYERS.get(batter, {}).get('role', 'BAT')
        runs = self.bat_stats.get(batter, {}).get('runs', 0)
        batter_ovr = get_player_ovr(ALL_PLAYERS[batter]['value'], batter) if batter in ALL_PLAYERS else 85
        bowler_ovr = get_player_ovr(ALL_PLAYERS[bowler]['value'], bowler) if bowler in ALL_PLAYERS else 85

        # Batting position — position 6+ get lower-order penalty
        try:
            bat_position = self.batting_order.index(batter) + 1  # 1-indexed
        except (ValueError, AttributeError):
            bat_position = 5

        # Base weights: [0, 1, 2, 3, 4, 6, W, NB, WD]
        # Realistic T20: avg 175-195 runs, ~6-8 wickets per innings
        # W weight kept LOW for top/mid order — tail gets extra via position penalty
        if role == 'BOWL':
            weights = [26, 22, 13, 3, 13, 6,  4, 4, 3]
        elif role == 'ALR':
            weights = [23, 22, 13, 3, 15, 8,  4, 4, 3]
        elif role == 'WK':
            weights = [22, 22, 13, 3, 16, 9,  4, 4, 3]
        else:  # BAT
            weights = [18, 21, 14, 3, 19, 12, 3, 4, 3]

        # Lower-order batting position penalty — dots increase, boundaries decrease
        # Wicket weight stays low (real tail-enders survive but don't score fast)
        if bat_position >= 9:
            weights[0] += 14  # lots of dots
            weights[6] += 4   # slightly more wickets (but still not extreme)
            weights[4] = max(weights[4] - 7, 2)
            weights[5] = max(weights[5] - 5, 1)
        elif bat_position >= 7:
            weights[0] += 8
            weights[6] += 2
            weights[4] = max(weights[4] - 4, 3)
            weights[5] = max(weights[5] - 3, 1)
        elif bat_position >= 6:
            weights[0] += 4
            weights[6] += 1
            weights[4] = max(weights[4] - 2, 6)
            weights[5] = max(weights[5] - 1, 2)

        # OVR difference — small adjustment only
        diff = batter_ovr - bowler_ovr
        if diff >= 10:
            weights[4] += 2; weights[5] += 1; weights[0] = max(weights[0] - 2, 10)
        elif diff <= -10:
            weights[6] += 2; weights[0] += 2; weights[4] = max(weights[4] - 2, 5)

        # Phase multipliers — keep scoring realistic per phase
        if self.overs < 6:       # Powerplay: moderate scoring
            weights = [int(w * m) for w, m in zip(weights, [1.0, 1.1, 1.0, 0.9, 0.9, 0.7, 1.0, 1.1, 1.1])]
        elif self.overs >= 16:   # Death: slightly more attacking but not crazy
            weights = [int(w * m) for w, m in zip(weights, [0.9, 1.0, 1.0, 1.0, 1.2, 1.4, 1.0, 1.1, 1.1])]
        elif 6 <= self.overs < 12:  # Middle 1: conservative
            weights = [int(w * m) for w, m in zip(weights, [1.1, 1.0, 1.0, 1.0, 0.9, 0.8, 1.0, 1.0, 1.0])]
        else:                    # Middle 2: picking up
            weights = [int(w * m) for w, m in zip(weights, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])]

        # Bowler economy soft cap — expensive bowlers become slightly harder to hit
        # (removed hard override to allow realistic high scores)
        bowl_runs = self.bowl_stats.get(bowler, {}).get('runs', 0)
        if bowl_runs >= 45:
            weights = [int(w * m) for w, m in zip(weights, [1.30, 1.05, 1.0, 1.0, 0.70, 0.55, 1.20, 1.0, 1.0])]
        elif bowl_runs >= 35:
            weights = [int(w * m) for w, m in zip(weights, [1.15, 1.05, 1.0, 1.0, 0.85, 0.70, 1.10, 1.0, 1.0])]

        # ── Pitch type effects ─────────────────────────────────────────
        # Weights: [0-dot, 1, 2, 3, 4-four, 6-six, W-wicket, NB, WD]
        # ── Pitch score soft-cap ────────────────────────────────────────
        pt = getattr(self, 'pitch_type', None)
        if pt and self.innings == 1:
            _caps = PITCH_SCORE_CAPS.get(pt)
            if _caps:
                _lo, _hi = _caps
                _proj = self.runs + max(0, (TOTAL_OVERS - self.overs) * 8)  # rough projection
                if self.runs > _hi:
                    # Over cap — drastically boost wickets, slash boundaries
                    weights = [int(w * m) for w, m in zip(weights, [1.4, 1.0, 0.9, 0.8, 0.5, 0.4, 1.8, 0.8, 0.8])]
                elif self.runs < _lo and self.overs > 15:
                    # Under floor in death — boost boundaries
                    weights = [int(w * m) for w, m in zip(weights, [0.7, 1.0, 1.0, 1.0, 1.5, 1.6, 0.7, 1.1, 1.1])]

        if pt == 'flat':
            # Flat Batting Pitch — batting paradise, high scoring
            weights = [int(w * m) for w, m in zip(weights, [0.80, 1.05, 1.05, 1.0, 1.25, 1.30, 0.75, 1.1, 1.1])]
        elif pt == 'green':
            # Green Seam Pitch — pacers dominate, hard to bat early
            if self.overs < 10:
                weights = [int(w * m) for w, m in zip(weights, [1.30, 0.95, 0.90, 0.9, 0.80, 0.65, 1.40, 1.2, 1.2])]
            else:
                weights = [int(w * m) for w, m in zip(weights, [1.10, 1.0, 1.0, 1.0, 0.90, 0.80, 1.15, 1.0, 1.0])]
        elif pt == 'spin':
            # Spin-Friendly Pitch — spinners dominate middle overs
            if 6 <= self.overs < 16:
                bowler_role = ALL_PLAYERS.get(bowler, {}).get('role', 'BOWL')
                is_spinner = bowler in ALL_PLAYERS and ALL_PLAYERS[bowler].get('country') in ['India','Sri Lanka','Afghanistan','Bangladesh']
                if is_spinner or role == 'BOWL':
                    weights = [int(w * m) for w, m in zip(weights, [1.20, 1.0, 0.95, 1.0, 0.80, 0.70, 1.30, 1.0, 1.0])]
                else:
                    weights = [int(w * m) for w, m in zip(weights, [0.95, 1.0, 1.0, 1.0, 1.05, 1.00, 0.95, 1.0, 1.0])]
            else:
                weights = [int(w * m) for w, m in zip(weights, [1.05, 1.0, 1.0, 1.0, 0.95, 0.90, 1.05, 1.0, 1.0])]
        elif pt == 'dew':
            # Dew-Assisted Night Pitch — chasing advantage (inn2 bats better)
            if self.innings == 2:
                weights = [int(w * m) for w, m in zip(weights, [0.85, 1.05, 1.05, 1.0, 1.20, 1.20, 0.85, 1.1, 1.2])]
            else:
                weights = [int(w * m) for w, m in zip(weights, [1.05, 1.0, 1.0, 1.0, 0.95, 0.90, 1.05, 1.0, 1.0])]
        elif pt == 'slow':
            # Slow Low Bounce Pitch — dead surface, restricted stroke play
            weights = [int(w * m) for w, m in zip(weights, [1.25, 1.05, 1.0, 1.0, 0.70, 0.55, 1.10, 1.0, 1.0])]
        elif pt == 'altitude':
            # High-Altitude Fast Outfield — everything races to boundary
            weights = [int(w * m) for w, m in zip(weights, [0.75, 1.05, 1.05, 1.0, 1.35, 1.45, 0.70, 1.1, 1.1])]

        # Home team batting advantage — slight boost when batting at home
        home = getattr(self, 'home_team', None)
        current_batting = self.batting_name if self.innings == 1 else self.bowling_name
        if home and current_batting == home:
            weights = [int(w * m) for w, m in zip(weights, [0.93, 1.02, 1.02, 1.0, 1.06, 1.06, 0.92, 1.0, 1.0])]

        # Batter milestone boost — slight not massive
        if runs >= 50:
            weights[4] = max(int(weights[4] * 1.1), weights[4])
            weights[5] = max(int(weights[5] * 1.1), weights[5])
            weights[0] = max(int(weights[0] * 1.1), weights[0])  # also more dots when set

        return [max(w, 1) for w in weights]

    def _simulate_one_ball(self):
        outcome = random.choices(BALL_OUTCOMES, weights=self._batter_outcome_weights(), k=1)[0]
        batter  = self.on_strike  or 'Batter'
        bowler  = self.current_bowler or 'Bowler'
        ball_str = f"{self.overs}.{self.balls_in_over + 1}"

        bs = self.bat_stats.setdefault(batter,  {'runs': 0, 'balls': 0, 'out': False})
        bw = self.bowl_stats.setdefault(bowler, {'balls': 0, 'runs': 0, 'wickets': 0})
        mb = self.match_bat_stats.setdefault(batter,  {'runs': 0, 'balls': 0})
        mw = self.match_bowl_stats.setdefault(bowler, {'balls': 0, 'runs': 0, 'wickets': 0})
        ib = self.innings_bat_stats[self.innings].setdefault(batter,  {'runs': 0, 'balls': 0, 'out': False, 'fours': 0, 'sixes': 0, 'dismissal': 'not out'})
        iw = self.innings_bowl_stats[self.innings].setdefault(bowler, {'balls': 0, 'runs': 0, 'wickets': 0, 'maidens': 0, 'nb': 0, 'wd': 0, '_over_runs': 0})

        if outcome in ['NB', 'WD']:
            # No-ball or Wide: +1 run, ball not counted, replay
            self.runs += 1
            bw['runs'] += 1; mw['runs'] += 1
            iw['runs'] += 1; iw['_over_runs'] += 1
            if outcome == 'NB':
                iw['nb'] = iw.get('nb', 0) + 1
                line = f"`{ball_str}` 🟡 **NO BALL!** +1 run, free hit coming up!"
            else:
                iw['wd'] = iw.get('wd', 0) + 1
                line = f"`{ball_str}` 🟠 **WIDE!** +1 run, ball replayed!"
            self.commentary.append(line)
            self.innings_commentary[self.innings].append(line)
            self._current_over.append(line)
            return outcome, line
        else:
            # Legal ball
            self.balls_in_over += 1
            bs['balls'] += 1; bw['balls'] += 1; mb['balls'] += 1; mw['balls'] += 1
            ib['balls'] += 1; iw['balls'] += 1

        if outcome == 'W':
            self._last_wicket_batter = self.on_strike  # track for gif
            self.last_ball_was_wicket = True
            bs['out'] = True
            ib['out'] = True
            # Pick a realistic dismissal type
            _dis_types = ['b', 'c', 'lbw', 'run out', 'st', 'c&b']
            _dis_weights = [30, 40, 15, 8, 4, 3]
            _dis = random.choices(_dis_types, weights=_dis_weights, k=1)[0]
            if _dis == 'b':
                _dis_str = f"b {bowler}"
            elif _dis == 'c&b':
                _dis_str = f"c&b {bowler}"
            elif _dis == 'lbw':
                _dis_str = f"lbw b {bowler}"
            elif _dis == 'st':
                _dis_str = f"st b {bowler}"
            elif _dis == 'run out':
                _dis_str = "run out"
            else:
                # caught — pick a random fielder from bowling team
                _fielders = [p['name'] for p in (self._inn1_bowling if self.innings == 1 else self._inn1_batting)]
                _fielder = random.choice(_fielders) if _fielders else bowler
                _dis_str = f"c {_fielder} b {bowler}"
            ib['dismissal'] = _dis_str
            bw['wickets'] += 1; mw['wickets'] += 1; iw['wickets'] += 1
            iw['_over_runs'] = iw.get('_over_runs', 0)  # no runs this ball
            self.wickets  += 1
            self.on_strike = None
            line = f"`{ball_str}` 🔴 **WICKET!** {batter} is OUT! {_dis_str}"
        else:
            self.last_ball_was_wicket = False
            self.runs   += outcome
            bs['runs']  += outcome; bw['runs']  += outcome
            mb['runs']  += outcome; mw['runs']  += outcome
            ib['runs']  += outcome; iw['runs']  += outcome
            iw['_over_runs'] = iw.get('_over_runs', 0) + outcome
            if outcome == 4:
                ib['fours'] = ib.get('fours', 0) + 1
            elif outcome == 6:
                ib['sixes'] = ib.get('sixes', 0) + 1
            if outcome % 2 == 1:
                self.on_strike, self.non_striker = self.non_striker, self.on_strike
            sym   = {0: '·', 1: '1', 2: '2', 3: '3', 4: '**4** 🔵', 6: '**6** 💥'}[outcome]
            notes = {
                0: random.choice([
                    f"{batter} squeezes it out to the off-side",
                    f"{batter} leaves it alone",
                    f"{batter} plays it safely to mid-off",
                    f"{batter} tucks it behind square for no run"
                ]),
                1: random.choice([
                    f"quick single taken by {batter}",
                    f"single nudged to third man",
                    f"sharp run to the keeper's end"
                ]),
                2: random.choice([
                    f"beautiful two by {batter}",
                    f"two runs through the covers",
                    f"excellent placement brings two"
                ]),
                3: random.choice([
                    f"three! {batter} shakes the field", f"clever running for three", f"three runs from the deep square"
                ]),
                4: random.choice([
                    f"FOUR! {batter} cuts it hard", f"boundary through midwicket from {batter}", f"slick drive for four"
                ]),
                6: random.choice([
                    f"SIX! {batter} clears the ropes!", f"huge blow by {batter}", f"monster six over long-on"
                ])
            }
            line = f"`{ball_str}` {sym} — {notes[outcome]}"
        self.commentary.append(line)
        self.innings_commentary[self.innings].append(line)
        self._current_over.append(line)
        return outcome, line

    def simulate_until_event(self):
        lines = []
        event = 'over_done'
        while self.balls_in_over < 6:
            outcome, line = self._simulate_one_ball()
            lines.append(line)
            if self.chase_won():
                event = 'match_won'; break
            if self.innings_done():
                event = 'innings_done'; break
            if outcome == 'W':
                if self.available_batters:
                    event = 'wicket'; break
                else:
                    event = 'innings_done'; break
        if event == 'over_done' and self.balls_in_over >= 6:
            self.overs += 1
            self.balls_in_over = 0
            if self.current_bowler:
                self.bowler_overs[self.current_bowler] = self.bowler_overs.get(self.current_bowler, 0) + 1
                # Check for maiden over
                _iw_cur = self.innings_bowl_stats[self.innings].get(self.current_bowler, {})
                if _iw_cur.get('_over_runs', 1) == 0:
                    _iw_cur['maidens'] = _iw_cur.get('maidens', 0) + 1
                _iw_cur['_over_runs'] = 0  # reset for next over
                # Remove bowler from pool if they've conceded 35+ runs
                bowl_runs = self.bowl_stats.get(self.current_bowler, {}).get('runs', 0)
                if bowl_runs >= 35 and self.current_bowler in self.bowlers_pool:
                    self.bowlers_pool.remove(self.current_bowler)
                    self.current_bowler = None
            if self._current_over:
                self.innings_overs[self.innings].append(self._current_over)
                self._current_over = []
            if not self.last_ball_was_wicket:
                self.on_strike, self.non_striker = self.non_striker, self.on_strike
            if self.innings_done():
                event = 'innings_done'
            elif self.chase_won():
                event = 'match_won'
        if event in ('innings_done', 'match_won') and self._current_over:
            self.innings_overs[self.innings].append(self._current_over)
            self._current_over = []
        return lines, event


def _build_over_embed(match, lines):
    label = "1st Innings" if match.innings == 1 else "2nd Innings"
    ov_n  = match.overs + 1 if match.balls_in_over > 0 else match.overs
    color = 0x1a8cff if match.innings == 1 else 0xff6600
    em = discord.Embed(title=f"🏏 {label} — Over {ov_n}", color=color)
    em.add_field(name="🎯 This Over", value="\n".join(lines[-8:]) or "—", inline=False)
    em.add_field(name=f"📊 {match.get_batting_name()}", value=match.scoreline(), inline=True)
    if match.innings == 2 and match.target:
        needed = match.target - match.runs
        em.add_field(name="🎯 Target", value=f"Need **{needed}** in **{TOTAL_OVERS - match.overs}** ov", inline=True)
    return em


async def _do_event(interaction, match, channel, lines, event):
    em = _build_over_embed(match, lines)
    await interaction.followup.send(embed=em)

    if event == 'wicket':
        if match.wickets >= MAX_WICKETS or not match.available_batters:
            await _end_innings(channel, match)
            return
        wkt_em = discord.Embed(
            title="🔴 Wicket!",
            description=(
                f"**{match.get_batting_name()}**, the next batter will be chosen automatically.\n"
                f"You have {len(match.available_batters)} batter(s) left."
            ),
            color=0xff0000
        )
        wkt_em.add_field(name="📊 Score", value=match.scoreline(), inline=True)
        await channel.send(embed=wkt_em)

    elif event in ('innings_done', 'match_won'):
        if match.innings == 1 and event == 'innings_done':
            await _end_innings(channel, match)
        else:
            await _end_match(channel, match, event)

    else:  # over_done
        if match.innings_done():
            if match.innings == 1:
                await _end_innings(channel, match)
            else:
                await _end_match(channel, match, 'innings_done')
        else:
            next_em = discord.Embed(
                title=f"✅ Over {match.overs} Complete",
                description=f"**{match.get_bowling_name()}**, pick your bowler for over {match.overs + 1}!",
                color=0x9b59b6
            )
            next_em.add_field(name="📊 Score", value=match.scoreline(), inline=True)
            if match.innings == 2 and match.target:
                next_em.add_field(name="🎯 Need", value=f"**{match.target - match.runs}** more", inline=True)
            await channel.send(embed=next_em, view=BowlerSelectView(match, channel))


def normalize_player_entry(line):
    props = re.findall(r'\(([^)]*)\)', line)
    name = re.sub(r'\s*\([^)]*\)', '', line).strip()
    role = 'BAT'
    for prop in props:
        tag = prop.strip().lower()
        if tag in ('wk', 'w/k', 'wicket keeper', 'wicketkeeper'):
            role = 'WK'
        elif tag in ('bowl', 'bowler'):
            role = 'BOWL'
        elif tag in ('alr', 'al', 'allrounder', 'all-rounder'):
            role = 'ALR'
    return name, role


def build_player_list(team_name, player_lines):
    # Build card lookup: name.lower() -> card data (from +addcard system)
    try:
        cards_db = load_cards() if os.path.exists(CARDS_FILE) else {}
    except Exception:
        cards_db = {}
    card_lookup = {c["name"].lower(): c for c in cards_db.values()}

    STYLE_TO_ROLE = {
        "Right-Handed Batter": "BAT", "Left-Handed Batter": "BAT",
        "Right-Arm Pacer": "BOWL",    "Left-Arm Pacer": "BOWL",
        "Right-Arm Spinner": "BOWL",  "Left-Arm Spinner": "BOWL",
        "WK-Batter": "WK",            "All-Rounder": "ALR",
    }

    players = []
    unknown = []
    for raw in player_lines:
        name, role_hint = normalize_player_entry(raw)
        if not name:
            continue
        found_name, pdata = find_player(name)
        if found_name:
            # Known player from ALL_PLAYERS DB
            entry = dict(pdata)
            entry['name'] = found_name
        elif name.lower() in card_lookup:
            # Player from +addcard cards system — use card stats
            c = card_lookup[name.lower()]
            role = STYLE_TO_ROLE.get(c.get("style", ""), "BAT")
            entry = {
                'name':     name,
                'rarity':   c.get("type", "rd1"),
                'role':     role,
                'team':     team_name,
                'country':  c.get("country", "Unknown"),
                'value':    c.get("price", 500000),
                'bat':      c.get("bat",  75),
                'bowl':     c.get("bowl", 65),
                'ovr':      c.get("ovr",  80),
                'field':    min(99, (c.get("bat",75) + c.get("bowl",65))//2 + 5),
                'pace':     c.get("bowl", 65) if "Pacer"   in c.get("style","") else 65,
                'spin':     c.get("bowl", 65) if "Spinner" in c.get("style","") else 65,
                'keeping':  c.get("bat",  75) if "WK"      in c.get("style","") else 65,
            }
        else:
            # Complete unknown — generic stats
            entry = {
                'name': name, 'rarity': 'Common', 'role': role_hint,
                'team': team_name, 'country': 'Unknown', 'value': 180
            }
            unknown.append(name)
        players.append(entry)
    return players, unknown


def parse_bowling_order(line):
    """Parse a bowling order line like: 'Rcb - Jacob Duffy - 1,3,17,19 , Bhuvneshwar Kumar - 2,4,18,20'\nReturns dict: {bowler_name_lower: [over_numbers]}"""
    line = line.strip()
    # Remove team prefix like "Rcb - " or "Csk - "
    dash_idx = line.find(' - ')
    if dash_idx != -1:
        line = line[dash_idx + 3:]

    bowling_map = {}
    # Pattern: "Name - over_list" where over_list ends before next "Name - digit"
    pattern = re.compile(r'([A-Za-z][A-Za-z\s]+?)\s*-\s*([\d\s,]+?)(?=\s+[A-Za-z][A-Za-z\s]+-\s*\d|$)')
    for m in pattern.finditer(line):
        bowler_name = m.group(1).strip().rstrip(',').strip()
        overs_str   = m.group(2).strip()
        overs = [int(o) for o in re.split(r'[,\s]+', overs_str) if o.strip().isdigit()]
        if bowler_name and overs:
            bowling_map[bowler_name.lower()] = overs
    return bowling_map


def parse_simulate_payload(text):
    blocks = [block.strip() for block in re.split(r'\n\s*\n', text.strip()) if block.strip()]
    if len(blocks) < 2:
        raise ValueError(
            "Please provide two teams separated by a blank line.\n"
            "Example:\n"
            "MI\nplayer1\nplayer2\n\nKKR\nplayer1\nplayer2\n\nrandom (pitch)\nwankhede (stadium)"
        )

    def parse_team_group(block):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError("Each team block must include a team name and at least two players.")
        return lines[0], lines[1:]

    team1_name, team1_players = parse_team_group(blocks[0])
    team2_name, team2_players = parse_team_group(blocks[1])
    pitch = stadium = None
    bowling_order1 = {}  # {bowler_name_lower: [over numbers]} for team1 bowling
    bowling_order2 = {}  # for team2 bowling

    for extra in blocks[2:]:
        lines = [l.strip() for l in extra.splitlines() if l.strip()]
        for line in lines:
            low = line.lower()
            # Detect bowling order lines — contains ' - ' and digits (over numbers)
            if ' - ' in line and re.search(r'\d', line):
                # Figure out which team it belongs to by checking team name prefix
                if low.startswith(team1_name.lower()[:3]) or low.startswith(team1_name.lower().split()[0]):
                    parsed = parse_bowling_order(line)
                    bowling_order1.update(parsed)
                elif low.startswith(team2_name.lower()[:3]) or low.startswith(team2_name.lower().split()[0]):
                    parsed = parse_bowling_order(line)
                    bowling_order2.update(parsed)
            elif 'pitch' in low and pitch is None:
                pitch = line
            elif 'stadium' in low and stadium is None:
                stadium = line
            elif pitch is None and ' - ' not in line:
                pitch = line
            elif stadium is None and ' - ' not in line:
                stadium = line

    return team1_name, team1_players, team2_name, team2_players, pitch, stadium, bowling_order1, bowling_order2


def choose_next_bowler(match, previous_bowler=None):
    # If a custom over schedule exists, use it
    over_to_bowler = getattr(match, 'over_to_bowler', {})
    next_over = match.overs + 1  # overs completed = next over number
    if over_to_bowler and next_over in over_to_bowler:
        return over_to_bowler[next_over]

    max_overs = getattr(match, 'bowler_max_overs', {})
    eligible = [b for b, overs in match.bowler_overs.items()
                if overs < max_overs.get(b, MAX_BOWLER_OVERS)]
    if not eligible:
        eligible = list(match.bowlers_pool)
    if previous_bowler and previous_bowler in eligible and len(eligible) > 1:
        eligible = [b for b in eligible if b != previous_bowler]
    min_overs = min(match.bowler_overs.get(b, 0) for b in eligible)
    candidates = [b for b in eligible if match.bowler_overs.get(b, 0) == min_overs]
    if len(candidates) > 1:
        min_runs = min(match.bowl_stats.get(b, {}).get('runs', 0) for b in candidates)
        candidates = [b for b in candidates if match.bowl_stats.get(b, {}).get('runs', 0) == min_runs]
    return random.choice(candidates)


def simulate_full_match(match):
    if match.bowlers_pool:
        match.current_bowler = choose_next_bowler(match)
    previous_bowler = None  # track who just bowled to prevent consecutive overs

    while True:
        if match.current_bowler is None and match.bowlers_pool:
            match.current_bowler = choose_next_bowler(match, previous_bowler=previous_bowler)

        _, event = match.simulate_until_event()
        if event == 'wicket':
            # Impact player auto-substitution in simulate mode
            _imp = match.impact_player_bat if match.innings == 1 else match.impact_player_bowl
            _imp_used = match.impact_used_bat if match.innings == 1 else match.impact_used_bowl
            if (_imp and not _imp_used and match.wickets in (3,4,5)
                    and match.overs < 18 and _imp in (match.available_batters or [])):
                # Bring in impact player ahead of schedule when mid-order falls
                match.available_batters.remove(_imp)
                match.available_batters.insert(0, _imp)
                if match.innings == 1: match.impact_used_bat = True
                else: match.impact_used_bowl = True
            if match.available_batters:
                next_batter = match.available_batters.pop(0)
                match.on_strike = next_batter
                match.bat_stats.setdefault(next_batter, {'runs': 0, 'balls': 0, 'out': False})

        if event == 'over_done':
            previous_bowler = match.current_bowler  # remember who just bowled
            if match.current_bowler:
                bowl_runs = match.bowl_stats.get(match.current_bowler, {}).get('runs', 0)
                if bowl_runs >= 45 and match.current_bowler in match.bowlers_pool:
                    match.bowlers_pool.remove(match.current_bowler)
                    match.current_bowler = None
            if match.bowlers_pool:
                # MUST pass previous_bowler to block consecutive overs
                match.current_bowler = choose_next_bowler(match, previous_bowler=previous_bowler)
            continue

        if event == 'innings_done':
            if match.innings == 1:
                match.innings_scores[1] = match.scoreline()
                target = match.runs + 1
                match.innings = 2
                match.target = target
                match._setup_innings()
                if match.bowlers_pool:
                    match.current_bowler = choose_next_bowler(match)
                continue
            match.innings_scores[2] = match.scoreline()
            break

        if event == 'match_won':
            match.innings_scores[2] = match.scoreline()
            break

    return match


def pick_player_of_match(match):
    impact = {}
    for name, s in match.match_bat_stats.items():
        bonus = 5 if s['balls'] and s['runs'] / s['balls'] >= 1.2 else 0
        impact[name] = impact.get(name, 0) + s['runs'] + bonus
    for name, s in match.match_bowl_stats.items():
        impact[name] = impact.get(name, 0) + s['wickets'] * 22 - s['runs'] * 0.35
        if s['wickets'] >= 2:
            impact[name] += 5
    if not impact:
        return None, 0
    return max(impact.items(), key=lambda x: (x[1], x[0]))


def innings_batting_name(match, inning):
    return match.batting_name if inning == 1 else match.bowling_name


def innings_bowling_name(match, inning):
    return match.bowling_name if inning == 1 else match.batting_name


def build_full_scorecard_embed(match, inning):
    """Build a detailed innings scorecard embed like the reference screenshot."""
    batting_name = innings_batting_name(match, inning)
    bowling_name = innings_bowling_name(match, inning)

    # Determine player order lists
    if inning == 1:
        bat_players = [p['name'] for p in match._inn1_batting]
        bowl_players = [p['name'] for p in match._inn1_bowling]
    else:
        bat_players = [p['name'] for p in match._inn1_bowling]
        bowl_players = [p['name'] for p in match._inn1_batting]

    bat_stats  = match.innings_bat_stats.get(inning, {})
    bowl_stats = match.innings_bowl_stats.get(inning, {})
    score_str  = match.innings_scores.get(inning, '0/0')

    # ── BATTING TABLE ────────────────────────────────────────────────
    bat_lines = []
    bat_lines.append(f"{'Batsman':<22} {'R(B)':<9} {'4s':<4} {'6s':<4} {'Status'}")
    bat_lines.append("─" * 56)

    for name in bat_players:
        s = bat_stats.get(name)
        if s and s.get('balls', 0) > 0:
            rb    = f"{s['runs']}({s['balls']})"
            fours = s.get('fours', 0)
            sixes = s.get('sixes', 0)
            dis   = s.get('dismissal', 'not out')
            if not s.get('out', False):
                dis = 'not out*'
            short = name.split()[-1] if ' ' in name else name
            # Truncate name to fit
            display = name if len(name) <= 20 else name[:19] + '.'
            bat_lines.append(f"{display:<22} {rb:<9} {fours:<4} {sixes:<4} {dis}")
        else:
            # DNB
            short = name if len(name) <= 20 else name[:19] + '.'
            bat_lines.append(f"{short:<22} {'0(0)':<9} {'0':<4} {'0':<4} DNB")

    # Extras
    total_nb = sum(s.get('nb', 0) for s in bowl_stats.values())
    total_wd = sum(s.get('wd', 0) for s in bowl_stats.values())
    total_extras = total_nb + total_wd
    bat_lines.append("─" * 56)
    bat_lines.append(f"📦 **Extras** — B: 0, LB: 0, W: {total_wd}, NB: {total_nb} | Total: {total_extras}")

    # ── BOWLING TABLE ────────────────────────────────────────────────
    bowl_lines = []
    bowl_lines.append(f"{'Bowler':<22} {'O':<5} {'M':<4} {'R':<5} {'W':<4} {'Econ'}")
    bowl_lines.append("─" * 48)

    for name in bowl_players:
        s = bowl_stats.get(name)
        if s and s.get('balls', 0) > 0:
            overs_str = f"{s['balls']//6}.{s['balls']%6}"
            maidens   = s.get('maidens', 0)
            runs      = s['runs']
            wkts      = s['wickets']
            overs_f   = s['balls'] / 6
            econ      = f"{runs/overs_f:.1f}" if overs_f > 0 else "0.0"
            display   = name if len(name) <= 20 else name[:19] + '.'
            bowl_lines.append(f"{display:<22} {overs_str:<5} {maidens:<4} {runs:<5} {wkts:<4} {econ}")

    # Build embed with monospaced blocks (code blocks)
    color = 0x1a8cff if inning == 1 else 0xff6600
    em = discord.Embed(
        title=f"📋 {'1st' if inning==1 else '2nd'} Innings — {batting_name}",
        description=f"**Score:** {score_str}  |  **vs {bowling_name}**",
        color=color
    )
    # Split into chunks if needed (Discord 1024 char field limit)
    NL = "\n"
    TICK = "```"
    bat_text = TICK + NL + NL.join(bat_lines) + NL + TICK
    if len(bat_text) > 1020:
        mid = len(bat_lines) // 2
        em.add_field(name="\U0001f3cf Batting", value=TICK + NL + NL.join(bat_lines[:mid]) + NL + TICK, inline=False)
        em.add_field(name="\U0001f3cf Batting (cont.)", value=TICK + NL + NL.join(bat_lines[mid:]) + NL + TICK, inline=False)
    else:
        em.add_field(name="\U0001f3cf Batting", value=bat_text, inline=False)

    bowl_text = TICK + NL + NL.join(bowl_lines) + NL + TICK
    em.add_field(name="\U0001f3af Bowling", value=bowl_text, inline=False)

    return em



def build_innings_menu_embed(match, inning, pitch=None, stadium=None, extra_note=None):
    batting = innings_batting_name(match, inning)
    bowling = innings_bowling_name(match, inning)
    total_overs = len(match.innings_overs.get(inning, []))
    score = match.innings_scores.get(inning, "N/A")
    description = [f"**Batting:** {batting}", f"**Bowling:** {bowling}", f"**Score:** {score}", f"**Overs available:** {total_overs}"]
    if pitch:
        description.insert(0, f"**Pitch:** {pitch}")
    if stadium:
        description.insert(1, f"**Stadium:** {stadium}")
    if extra_note:
        description.append(extra_note)

    em = discord.Embed(
        title=f"📋 Innings {inning} Overview",
        description="\n".join(description),
        color=0x1abc9c
    )
    if total_overs:
        em.add_field(name="➡ Select over", value="Choose an over from the dropdown below.", inline=False)
    else:
        em.add_field(name="⚠️ No commentary yet", value="This innings has no completed overs.", inline=False)
    return em


def build_over_commentary_embed(match, inning, over_index, pitch=None, stadium=None, extra_note=None):
    batting = innings_batting_name(match, inning)
    lines = match.innings_overs.get(inning, [])
    if over_index < 1 or over_index > len(lines):
        return discord.Embed(title="⚠️ Over not available", description="This over is not available.", color=0xe74c3c)

    over_lines = lines[over_index - 1]
    em = discord.Embed(
        title=f"🎯 Innings {inning} — Over {over_index}",
        description=f"**Batting:** {batting}",
        color=0x9b59b6
    )
    em.add_field(name="📣 Ball-by-ball", value="\n".join(over_lines), inline=False)
    em.add_field(name="📊 Over summary", value=f"{len(over_lines)} ball(s)", inline=True)
    if pitch:
        em.add_field(name="Pitch", value=pitch, inline=True)
    if stadium:
        em.add_field(name="Stadium", value=stadium, inline=True)
    if extra_note:
        em.set_footer(text=extra_note)
    return em


class FullScorecardView(discord.ui.View):
    """View shown when displaying full innings scorecard. Just a Back button."""
    def __init__(self, match, pitch=None, stadium=None, extra_note=None):
        super().__init__(timeout=300)
        self.match = match
        self.pitch = pitch
        self.stadium = stadium
        self.extra_note = extra_note

    @discord.ui.button(label="◀ Back to Menu", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        from discord import Embed
        em = build_simulation_summary(self.match, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note)
        await interaction.response.edit_message(embed=em,
            view=SimulationMenuView(self.match, self.pitch, self.stadium, self.extra_note))


class SimulationMenuView(discord.ui.View):
    def __init__(self, match, pitch=None, stadium=None, extra_note=None):
        super().__init__(timeout=300)
        self.match = match
        self.pitch = pitch
        self.stadium = stadium
        self.extra_note = extra_note

    @discord.ui.button(label="📋 Inn 1 Scorecard", style=discord.ButtonStyle.success, row=0)
    async def inn1_scorecard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_full_scorecard_embed(self.match, 1),
            view=FullScorecardView(self.match, self.pitch, self.stadium, self.extra_note)
        )

    @discord.ui.button(label="📋 Inn 2 Scorecard", style=discord.ButtonStyle.success, row=0)
    async def inn2_scorecard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_full_scorecard_embed(self.match, 2),
            view=FullScorecardView(self.match, self.pitch, self.stadium, self.extra_note)
        )

    @discord.ui.button(label="🎬 Innings 1 Overs", style=discord.ButtonStyle.primary, row=1)
    async def innings_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_innings_menu_embed(self.match, 1, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
            view=SimulationOverSelectView(self.match, 1, self.pitch, self.stadium, self.extra_note)
        )

    @discord.ui.button(label="🎬 Innings 2 Overs", style=discord.ButtonStyle.primary, row=1)
    async def innings_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_innings_menu_embed(self.match, 2, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
            view=SimulationOverSelectView(self.match, 2, self.pitch, self.stadium, self.extra_note)
        )


class SimulationOverSelectView(discord.ui.View):
    def __init__(self, match, inning, pitch=None, stadium=None, extra_note=None):
        super().__init__(timeout=300)
        self.match = match
        self.inning = inning
        self.pitch = pitch
        self.stadium = stadium
        self.extra_note = extra_note
        options = []
        for idx, _ in enumerate(match.innings_overs.get(inning, []), start=1):
            options.append(discord.SelectOption(label=f"Over {idx}", value=str(idx)))
        if not options:
            options = [discord.SelectOption(label="No overs available", value="0", description="No commentary available")]
        select = discord.ui.Select(placeholder="Select over…", options=options, custom_id=f"over_select_{inning}")

        async def select_over(interaction: discord.Interaction):
            value = select.values[0]
            if value == "0":
                await interaction.response.defer()
                return
            over_index = int(value)
            await interaction.response.edit_message(
                embed=build_over_commentary_embed(self.match, self.inning, over_index, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
                view=SimulationOverDetailView(self.match, self.inning, over_index, self.pitch, self.stadium, self.extra_note)
            )

        select.callback = select_over
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_to_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_simulation_summary(self.match, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
            view=SimulationMenuView(self.match, self.pitch, self.stadium, self.extra_note)
        )


class SimulationOverDetailView(discord.ui.View):
    def __init__(self, match, inning, over_index, pitch=None, stadium=None, extra_note=None):
        super().__init__(timeout=300)
        self.match = match
        self.inning = inning
        self.over_index = over_index
        self.pitch = pitch
        self.stadium = stadium
        self.extra_note = extra_note
        self.total_overs = len(match.innings_overs.get(inning, []))

        # Dynamically add Prev / Next buttons based on position
        if over_index > 1:
            prev_btn = discord.ui.Button(label=f"◀ Over {over_index - 1}", style=discord.ButtonStyle.primary, row=0)
            async def go_prev(interaction: discord.Interaction, _btn=prev_btn):
                new_idx = self.over_index - 1
                await interaction.response.edit_message(
                    embed=build_over_commentary_embed(self.match, self.inning, new_idx, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
                    view=SimulationOverDetailView(self.match, self.inning, new_idx, self.pitch, self.stadium, self.extra_note)
                )
            prev_btn.callback = go_prev
            self.add_item(prev_btn)

        if over_index < self.total_overs:
            next_btn = discord.ui.Button(label=f"Over {over_index + 1} ▶", style=discord.ButtonStyle.primary, row=0)
            async def go_next(interaction: discord.Interaction, _btn=next_btn):
                new_idx = self.over_index + 1
                await interaction.response.edit_message(
                    embed=build_over_commentary_embed(self.match, self.inning, new_idx, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
                    view=SimulationOverDetailView(self.match, self.inning, new_idx, self.pitch, self.stadium, self.extra_note)
                )
            next_btn.callback = go_next
            self.add_item(next_btn)

    @discord.ui.button(label="Back to overs", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_overs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_innings_menu_embed(self.match, self.inning, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
            view=SimulationOverSelectView(self.match, self.inning, self.pitch, self.stadium, self.extra_note)
        )

    @discord.ui.button(label="Main menu", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_simulation_summary(self.match, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note),
            view=SimulationMenuView(self.match, self.pitch, self.stadium, self.extra_note)
        )


def build_simulation_summary(match, pitch=None, stadium=None, extra_note=None):
    score1 = match.innings_scores.get(1, "?")
    score2 = match.innings_scores.get(2, "?")

    def _score_runs(score_text):
        if score_text == "?":
            return 0
        m = re.search(r"(\d+)/(\d+)", score_text)
        return int(m.group(1)) if m else 0

    t1 = _score_runs(score1)
    t2 = _score_runs(score2)
    if t2 > t1:
        winner = match.bowling_name
        margin = f"by {MAX_WICKETS - match.wickets} wickets"
    elif t1 > t2:
        winner = match.batting_name
        margin = f"by {t1 - t2} runs"
    else:
        winner = "No one — it's a"
        margin = "TIE!"

    title = f"🏆 {winner} {margin}" if winner != "No one — it's a" else "🤝 Match tied"
    description_parts = []
    if pitch:
        description_parts.append(f"**Pitch:** {pitch}")
    if stadium:
        description_parts.append(f"**Stadium:** {stadium}")
    if extra_note:
        description_parts.append(extra_note)

    em = discord.Embed(
        title=title,
        description="\n".join(description_parts) if description_parts else "Simulated match result",
        color=0x00aaff if t1 >= t2 else 0x9b59b6
    )
    em.add_field(name=f"{match.batting_name}", value=score1, inline=True)
    em.add_field(name=f"{match.bowling_name}", value=score2, inline=True)

    top_bat = sorted(match.match_bat_stats.items(), key=lambda x: (-x[1]['runs'], x[1]['balls']))[:4]
    top_bow = sorted(match.match_bowl_stats.items(), key=lambda x: (-x[1]['wickets'], x[1]['runs']))[:4]
    if top_bat:
        em.add_field(
            name="🌟 Top Scorers",
            value="\n".join(
                f"**{n}** ({ALL_PLAYERS[n]['team'] if n in ALL_PLAYERS else match.batting_name if n in [c['name'] for c in match._inn1_batting] else match.bowling_name}) — {s['runs']} ({s['balls']}b)"
                for n, s in top_bat),
            inline=False
        )
    if top_bow:
        em.add_field(
            name="🎯 Top Bowlers",
            value="\n".join(
                f"**{n}** ({ALL_PLAYERS[n]['team'] if n in ALL_PLAYERS else match.bowling_name if n in [c['name'] for c in match._inn1_bowling] else match.batting_name}) — {s['wickets']}/{s['runs']}"
                for n, s in top_bow),
            inline=False
        )

    def _commentary_preview(lines):
        if not lines:
            return []
        if len(lines) <= 10:
            return lines
        return lines[:5] + ["...best moments..."] + lines[-5:]

    if match.commentary:
        em.add_field(
            name="📣 Ball-by-ball Highlights",
            value="\n".join(_commentary_preview(match.commentary)),
            inline=False
        )

    pom_name, pom_score = pick_player_of_match(match)
    if pom_name:
        pom_parts = []
        if pom_name in match.match_bat_stats:
            bat = match.match_bat_stats[pom_name]
            pom_parts.append(f"{bat['runs']} runs")
        if pom_name in match.match_bowl_stats:
            bowl = match.match_bowl_stats[pom_name]
            pom_parts.append(f"{bowl['wickets']} wickets")
        em.add_field(
            name="🏅 Player of the Match",
            value=f"**{pom_name}** — {' and '.join(pom_parts)}",
            inline=False
        )
    return em


async def send_scorecard(channel, match):
    """Generate and send the scorecard image after a simulation."""
    if not PILLOW_AVAILABLE:
        return

    batting_team_players = [p['name'] for p in match._inn1_batting]
    bowling_team_players = [p['name'] for p in match._inn1_bowling]

    def build_batters(player_names, inn_stats, top=4):
        rows = []
        for name in player_names:
            s = inn_stats.get(name)
            if s and s.get('balls', 0) > 0:
                not_out = not s.get('out', False)  # True = not out = show *
                rows.append((name, s['runs'], s['balls'], not_out))
        # Keep batting order (player_names is already ordered), just take top 4 by runs for display
        rows.sort(key=lambda x: -x[1])
        return rows[:top]

    def build_bowlers(player_names, inn_stats, top=4):
        rows = []
        for name in player_names:
            s = inn_stats.get(name)
            if s and s.get('balls', 0) > 0:
                overs = f"{s['balls']//6}.{s['balls']%6}"
                rows.append((name, s['wickets'], s['runs'], overs))
        rows.sort(key=lambda x: (-x[1], x[2]))
        return rows[:top]

    # Inn1: batting_team bats, bowling_team bowls
    t1_bat  = build_batters(batting_team_players,  match.innings_bat_stats[1])
    t1_bowl = build_bowlers(bowling_team_players,  match.innings_bowl_stats[1])
    # Inn2: bowling_team bats, batting_team bowls
    t2_bat  = build_batters(bowling_team_players,  match.innings_bat_stats[2])
    t2_bowl = build_bowlers(batting_team_players,  match.innings_bowl_stats[2])

    def parse_score(score_str):
        m = re.search(r'(\d+)/(\d+)', score_str or '')
        if m:
            return int(m.group(1)), int(m.group(2))
        return 0, 0

    score1_str = match.innings_scores.get(1, '0/0')
    score2_str = match.innings_scores.get(2, '0/0')
    s1_runs, s1_wkts = parse_score(score1_str)
    s2_runs, s2_wkts = parse_score(score2_str)

    # Overs
    def get_overs(inn_bowl_stats):
        total_balls = sum(s.get('balls', 0) for s in inn_bowl_stats.values())
        return f"{total_balls//6}.{total_balls%6}"

    t1_overs = get_overs(match.innings_bowl_stats[1])
    t2_overs = get_overs(match.innings_bowl_stats[2])

    # Result text
    if s2_runs > s1_runs:
        winner = match.bowling_name
        margin = f"by {10 - s2_wkts} wickets"
    elif s1_runs > s2_runs:
        winner = match.batting_name
        margin = f"by {s1_runs - s2_runs} runs"
    else:
        winner = "Match"
        margin = "tied!"
    result_text = f"{winner} won {margin}"

    # Player of the Match
    pom_name, _ = pick_player_of_match(match)

    buf = generate_scorecard_image(
        match.batting_name, s1_runs, s1_wkts, t1_overs,
        t1_bat, t1_bowl,
        match.bowling_name, s2_runs, s2_wkts, t2_overs,
        t2_bat, t2_bowl,
        result_text,
        pom_name=pom_name
    )
    if buf:
        try:
            await channel.send(file=discord.File(buf, filename="scorecard.png"))
        except Exception as e:
            print(f"[Scorecard] Failed to send image: {e}")


# ─────────────────────────────────────────────
# PITCH DEFINITIONS
# ─────────────────────────────────────────────
PITCH_OPTIONS = [
    {
        "key": "flat",
        "emoji": "🟡",
        "name": "Flat Batting Pitch",
        "short": "High scoring (170–210) · Batters dominate · Little swing",
        "desc": "Hard surface, even bounce, very little swing or seam, fast outfield. Bowlers struggle badly.",
        "color": 0xf1c40f,
    },
    {
        "key": "green",
        "emoji": "🟢",
        "name": "Green Seam Pitch",
        "short": "Low scores (150–190) · Pacers dominate · Early swing",
        "desc": "Grass-covered surface, early moisture, strong swing and seam. Difficult batting early.",
        "color": 0x27ae60,
    },
    {
        "key": "spin",
        "emoji": "🟤",
        "name": "Spin-Friendly Pitch",
        "short": "Moderate scores (155–200) · Spinners dominate · Turn & grip",
        "desc": "Dry surface with cracks. Slow turn and uneven bounce. Spinners lethal in middle overs.",
        "color": 0xe67e22,
    },
    {
        "key": "dew",
        "emoji": "🔵",
        "name": "Dew-Assisted Night Pitch",
        "short": "Chasing advantage · High scoring · Toss critical",
        "desc": "Heavy dew in 2nd innings, ball becomes wet. Chasing team gets a big advantage.",
        "color": 0x2980b9,
    },
    {
        "key": "slow",
        "emoji": "⚫",
        "name": "Slow Low Bounce Pitch",
        "short": "Low scores (130–180) · Timing difficult · Dead surface",
        "desc": "Dead surface, ball stops on bat. Low and inconsistent bounce, stroke play restricted.",
        "color": 0x7f8c8d,
    },
    {
        "key": "altitude",
        "emoji": "🔴",
        "name": "High-Altitude Fast Outfield",
        "short": "Very high scoring (210–230) · Mishits go for boundaries",
        "desc": "Ball travels quickly off bat, fast outfield. Even mishits go for fours. Bowlers heavily punished.",
        "color": 0xe74c3c,
    },
]
PITCH_KEY_MAP = {p["key"]: p for p in PITCH_OPTIONS}

# Score caps per pitch (min, max) — first innings target range
PITCH_SCORE_CAPS = {
    "flat":     (170, 210),
    "green":    (150, 190),
    "spin":     (155, 200),
    "dew":      (140, 160),
    "slow":     (130, 180),
    "altitude": (210, 230),
}


class PitchSelectionView(discord.ui.View):
    """Step 0 — pick pitch type before bowling selection."""
    def __init__(self, ctx, team1_name, team1_list, team2_name, team2_list, stadium, extra_note, home_team=None):
        super().__init__(timeout=120)
        self.ctx        = ctx
        self.team1_name = team1_name
        self.team1_list = team1_list
        self.team2_name = team2_name
        self.team2_list = team2_list
        self.stadium    = stadium
        self.extra_note = extra_note
        self.home_team  = home_team

        options = [
            discord.SelectOption(
                label=f"{p['emoji']} {p['name']}",
                value=p['key'],
                description=p['short'][:100]
            )
            for p in PITCH_OPTIONS
        ]
        select = discord.ui.Select(
            placeholder="🏟️ Select pitch type…",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self._on_pitch_select
        self.add_item(select)

    async def _on_pitch_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your match!", ephemeral=True)

        pitch_key = interaction.data['values'][0]
        pinfo = PITCH_KEY_MAP[pitch_key]
        pitch_label = f"{pinfo['emoji']} {pinfo['name']}"

        em = discord.Embed(
            title=f"🏏 Match Setup — Pick Bowlers",
            description=(
                f"**{self.team1_name}** vs **{self.team2_name}**\n\n"
                f"**Pitch:** {pitch_label}\n_{pinfo['desc']}_\n\n"
                f"Now select bowlers for **{self.team1_name}** (up to 5).\n"
                f"Only BOWL 🎯 and ALR ⚡ players are recommended!"
            ),
            color=pinfo['color']
        )
        if self.stadium:
            em.add_field(name="🏟️ Stadium", value=self.stadium, inline=True)

        view = BowlingSelectionView(
            self.ctx, self.team1_name, self.team1_list,
            self.team2_name, self.team2_list,
            pitch_label, self.stadium, self.extra_note,
            pitch_type_key=pitch_key,
            home_team=self.home_team
        )
        await interaction.response.edit_message(embed=em, view=view)


class BowlingSelectionView(discord.ui.View):
    """Step 1 & 2 — pick bowlers for each team via dropdown, then start match."""
    def __init__(self, ctx, team1_name, team1_list, team2_name, team2_list, pitch, stadium, extra_note, pitch_type_key=None, home_team=None):
        super().__init__(timeout=120)
        self.ctx        = ctx
        self.team1_name = team1_name
        self.team1_list = team1_list
        self.team2_name = team2_name
        self.team2_list = team2_list
        self.pitch      = pitch
        self.stadium    = stadium
        self.extra_note = extra_note
        self.pitch_type_key = pitch_type_key
        self.home_team  = home_team
        self.selected_bowlers = {}   # team_name -> [player_names]
        self.step = 1  # 1 = picking team1 bowlers, 2 = picking team2 bowlers

        self._build_select(team1_name, team1_list)

    def _get_bowling_candidates(self, player_list):
        """Return BOWL and ALR players first, then others as fallback."""
        primary   = [p for p in player_list if p.get('role') in ('BOWL', 'ALR')]
        secondary = [p for p in player_list if p.get('role') not in ('BOWL', 'ALR')]
        return primary + secondary

    def _build_select(self, team_name, player_list):
        self.clear_items()
        candidates = self._get_bowling_candidates(player_list)
        options = []
        for p in candidates[:25]:
            role_emoji = {'BOWL': '🎯', 'ALR': '⚡', 'BAT': '🏏', 'WK': '🧤'}.get(p.get('role', 'BAT'), '🏏')
            label = f"{role_emoji} {p['name']}"[:100]
            options.append(discord.SelectOption(label=label, value=p['name']))

        select = discord.ui.Select(
            placeholder=f"🎳 Choose bowlers for {team_name} (pick up to 5)…",
            options=options,
            min_values=1,
            max_values=min(5, len(options))
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your match!", ephemeral=True)

        values = interaction.data['values']

        if self.step == 1:
            self.selected_bowlers[self.team1_name] = values
            self.step = 2
            self._build_select(self.team2_name, self.team2_list)
            em = discord.Embed(
                title=f"✅ {self.team1_name} bowlers set!",
                description=f"Now pick bowlers for **{self.team2_name}**",
                color=0xffaa00
            )
            em.add_field(name=f"🎯 {self.team1_name} Bowling Attack",
                         value="\n".join(f"• {v}" for v in values), inline=False)
            await interaction.response.edit_message(embed=em, view=self)

        else:
            self.selected_bowlers[self.team2_name] = values
            await interaction.response.edit_message(
                content="⚙️ Setting up the match…", embed=None, view=None)
            await self._start_match(interaction, original_interaction=interaction)

    async def _start_match(self, interaction, original_interaction=None):
        # Build bowling orders from selections — distribute overs evenly
        def build_order(bowler_names):
            order = {}
            total_overs = 20
            n = len(bowler_names)
            overs_each = total_overs // n
            extra = total_overs % n
            over_num = 1
            for i, name in enumerate(bowler_names):
                count = overs_each + (1 if i < extra else 0)
                overs = list(range(over_num, over_num + count))
                over_num += count
                order[name.lower()] = overs
            return order

        bo1 = build_order(self.selected_bowlers[self.team1_name])
        bo2 = build_order(self.selected_bowlers[self.team2_name])

        # Coin toss — home team wins toss 60% of the time and bats first by default
        home = getattr(self, 'home_team', None)
        toss_won_by_team1 = random.random() < (0.6 if home == self.team1_name else (0.4 if home == self.team2_name else 0.5))
        if toss_won_by_team1:
            batting_name, batting_list = self.team1_name, self.team1_list
            bowling_name, bowling_list = self.team2_name, self.team2_list
            bo_batting, bo_bowling = bo1, bo2
        else:
            batting_name, batting_list = self.team2_name, self.team2_list
            bowling_name, bowling_list = self.team1_name, self.team1_list
            bo_batting, bo_bowling = bo2, bo1

        channel = self.ctx.channel
        match = MatchState(channel.id, 'simulate', 'simulate',
                           batting_name, bowling_name, batting_list, bowling_list,
                           bowling_order_batting=bo_batting, bowling_order_bowling=bo_bowling,
                           pitch_type=getattr(self, 'pitch_type_key', None),
                           home_team=getattr(self, 'home_team', None))

        # Run simulation in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, simulate_full_match, match)

        summary_embed = build_simulation_summary(match, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note)
        menu_view = SimulationMenuView(match, pitch=self.pitch, stadium=self.stadium, extra_note=self.extra_note)

        # ── Quest progress hooks ─────────────────────────────────────
        try:
            uid = str(self.ctx.author.id)
            # Determine winner from innings scores
            s1 = match.innings_scores.get(1, "0/0")
            s2 = match.innings_scores.get(2, "0/0")
            r1 = int(s1.split("/")[0]) if s1 != "0/0" else 0
            r2 = int(s2.split("/")[0]) if s2 != "0/0" else 0
            user_team = self.team1_name   # user picks team1 in +simulate
            winner_team = match.batting_name if r2 > r1 else (match.bowling_name if r1 > r2 else None)
            if winner_team and winner_team == user_team:
                update_quest_progress(uid, "sim_win", 1)
            # Score a century / fifty — check bat stats
            for name, stat in match.match_bat_stats.items():
                if stat.get("runs", 0) >= 100:
                    update_quest_progress(uid, "century", 1)
                elif stat.get("runs", 0) >= 50:
                    update_quest_progress(uid, "fifty", 1)
            # Bowling: check 3-fer / 5-fer
            for name, stat in match.match_bowl_stats.items():
                wkts = stat.get("wickets", 0)
                if wkts >= 5:
                    update_quest_progress(uid, "fivefer", 1)
                elif wkts >= 3:
                    update_quest_progress(uid, "threfer", 1)
        except Exception as _qe:
            print(f"[Quest hook error] {_qe}")

        # Edit the "Setting up the match..." message with the actual result
        if original_interaction is not None:
            try:
                await original_interaction.edit_original_response(
                    content=None, embed=summary_embed, view=menu_view)
            except Exception:
                await channel.send(embed=summary_embed, view=menu_view)
        else:
            await channel.send(embed=summary_embed, view=menu_view)

        try:
            await send_scorecard(channel, match)
        except Exception as e:
            print(f"[Scorecard Error] {e}")
            import traceback; traceback.print_exc()


@bot.command(name='simulate')
async def simulate_match(ctx, *, payload: str = None):
    """Simulate a custom match from two team blocks."""
    if not payload or not payload.strip():
        return await ctx.send(
            "❌ Usage: `+simulate` followed by two team blocks separated by a blank line."
        )

    try:
        team1_name, team1_players, team2_name, team2_players, pitch, stadium, _, _ = parse_simulate_payload(payload)
    except ValueError as exc:
        return await ctx.send(f"❌ {exc}")

    team1_list, unknown1 = build_player_list(team1_name, team1_players)
    team2_list, unknown2 = build_player_list(team2_name, team2_players)

    if len(team1_list) < 2 or len(team2_list) < 2:
        return await ctx.send("❌ Each team needs at least two players.")

    if len(team1_list) > 11:
        team1_list = team1_list[:11]
    if len(team2_list) > 11:
        team2_list = team2_list[:11]

    extra_notes = []
    if unknown1 or unknown2:
        extra_notes.append("Generic stats used for: " + ", ".join(unknown1 + unknown2))
    extra_note = "\n".join(extra_notes) if extra_notes else None

    em = discord.Embed(
        title="🏏 Match Setup — Select Pitch",
        description=(
            f"**{team1_name}** vs **{team2_name}**\n\n"
            f"Choose the **pitch conditions** for this match.\n"
            f"The pitch will affect scoring rates, wicket chances, and which bowlers thrive!"
        ),
        color=0x00aaff
    )
    if stadium: em.add_field(name="🏟️ Stadium", value=stadium, inline=True)
    if unknown1 or unknown2:
        em.add_field(name="⚠️ Generic Stats", value=", ".join(unknown1 + unknown2), inline=False)

    # Show pitch options as fields
    for p in PITCH_OPTIONS:
        em.add_field(name=f"{p['emoji']} {p['name']}", value=p['short'], inline=False)

    # Step 0: Home team selection
    em = discord.Embed(
        title="🏠 Match Setup — Home Team",
        description=(
            f"**{team1_name}** vs **{team2_name}**\n\n"
            "Which team is playing at **home**?\n"
            "The home team gets a toss advantage (60%) and slight batting boost.\n"
            "Select **Neutral** for no advantage."
        ),
        color=0x00aaff
    )
    if stadium: em.add_field(name="🏟️ Stadium", value=stadium, inline=True)
    view = HomeTeamSelectionView(ctx, team1_name, team1_list, team2_name, team2_list, stadium, extra_note)
    await ctx.send(embed=em, view=view)


class HomeTeamSelectionView(discord.ui.View):
    """Step 0 — pick home team before pitch selection."""
    def __init__(self, ctx, team1_name, team1_list, team2_name, team2_list, stadium, extra_note):
        super().__init__(timeout=120)
        self.ctx        = ctx
        self.team1_name = team1_name
        self.team1_list = team1_list
        self.team2_name = team2_name
        self.team2_list = team2_list
        self.stadium    = stadium
        self.extra_note = extra_note

        options = [
            discord.SelectOption(label=f"🏠 {team1_name} (Home)", value=team1_name, description=f"{team1_name} plays at home — toss & batting advantage"),
            discord.SelectOption(label=f"🏠 {team2_name} (Home)", value=team2_name, description=f"{team2_name} plays at home — toss & batting advantage"),
            discord.SelectOption(label="⚖️ Neutral Venue", value="__neutral__", description="No home advantage — fair 50/50 toss"),
        ]
        select = discord.ui.Select(placeholder="🏠 Select home team…", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your match!", ephemeral=True)
        val = interaction.data["values"][0]
        home_team = None if val == "__neutral__" else val
        home_label = f"🏠 {home_team}" if home_team else "⚖️ Neutral Venue"

        em = discord.Embed(
            title="🏏 Match Setup — Select Pitch",
            description=(
                f"**{self.team1_name}** vs **{self.team2_name}**\n"
                f"**Home:** {home_label}\n\n"
                "Now choose the **pitch conditions**."
            ),
            color=0x00aaff
        )
        for p in PITCH_OPTIONS:
            em.add_field(name=f"{p['emoji']} {p['name']}", value=p["short"], inline=False)

        view = PitchSelectionView(self.ctx, self.team1_name, self.team1_list,
                                   self.team2_name, self.team2_list,
                                   self.stadium, self.extra_note, home_team=home_team)
        await interaction.response.edit_message(embed=em, view=view)


# ─────────────────────────────────────────────
# INTERACTIVE MATCH COMMAND
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# INTERACTIVE MATCH — CHALLENGE SYSTEM
# ─────────────────────────────────────────────
# pending_challenges[challenger_id] = {data}
pending_challenges = {}

# pending_xi_setups[setup_id] = {data}
pending_xi_setups = {}

@bot.command(name="interactive")
async def interactive_match(ctx, *, payload: str = None):
    """Challenge another user to a live ball-by-ball match.\n\nTwo ways to start:\n\n1) Quick challenge — just mention two users:\n`+interactive @user1 @user2`\nThen BOTH captains submit their playing XI with:\n`+xi <TeamName> | player1, player2, ..., player11`\n(any player names are accepted — known players use real stats,\nunknown players get generic stats)\n
    2) Inline payload (legacy):
       +interactive
       KKR (@user1)
       Player1
       ...

       CSK (@user2)
       Player1
       ...
    """
    # ── New flow: `+interactive @u1 @u2` (mentions only, no team blocks) ──
    mentions = ctx.message.mentions if ctx.message else []
    payload_text = (payload or "").strip()
    # Detect "mentions only" mode: payload contains only mention tokens (after stripping <@...>)
    stripped = re.sub(r"<@!?\d+>", "", payload_text).strip()
    if mentions and len(mentions) >= 2 and not stripped:
        u1, u2 = mentions[0], mentions[1]
        if u1.id == u2.id:
            return await ctx.send("❌ You must mention two different users.")
        setup_id = ctx.channel.id  # one setup per channel
        if setup_id in pending_xi_setups:
            return await ctx.send(
                "⚠️ An interactive setup is already in progress in this channel. "
                "Wait for it to finish or use `+cancelxi` to cancel."
            )
        data = {
            "ctx": ctx,
            "channel": ctx.channel,
            "captains": {u1.id: u1, u2.id: u2},
            "order": [u1.id, u2.id],     # u1 = team 1, u2 = team 2
            "teams": {},                 # uid -> {"name": str, "players": [str,...]}
            "stadium": None,
            "extra_note": None,
        }
        pending_xi_setups[setup_id] = data
        em = discord.Embed(
            title="⚔️ Interactive Match — Submit Your Playing XI",
            description=(
                f"{u1.mention} **vs** {u2.mention}\n\n"
                "**Each captain — submit your XI in this channel:**\n"
                "`+myxi <TeamName> | player1, player2, player3, ..., player11`\n\n"
                "**Examples:**\n"
                "`+myxi MI | Rohit Sharma, Jasprit Bumrah, Suryakumar Yadav, ...`\n"
                "`+myxi RCB | Virat Kohli, Faf du Plessis, Glenn Maxwell, ...`\n\n"
                "✅ You can pick **any player** — known players use real stats; "
                "anyone else gets generic stats automatically.\n"
                "📝 You can also list players on separate lines after `+myxi <Team>`.\n\n"
                "Once both captains submit, the match auto-starts.\n"
                "Use `+cancelxi` to cancel."
            ),
            color=0xff6600,
        )
        em.set_footer(text="Setup expires in 10 minutes.")
        await ctx.send(embed=em)
        # Auto-expire after 10 min
        async def _expire(sid=setup_id):
            await asyncio.sleep(600)
            if sid in pending_xi_setups:
                del pending_xi_setups[sid]
        asyncio.create_task(_expire())
        return

    # ── Legacy flow: full payload with team blocks ──
    if not payload or not payload.strip():
        return await ctx.send(
            "❌ **Usage:** `+interactive @user1 @user2`  (then each captain runs `+xi <Team> | p1, p2, ...`)\n"
            "Or: `+interactive`\nTeamName (@user)\nPlayer1\nPlayer2...\n\nTeamName2 (@user2)\nPlayer1\nPlayer2..."
        )
    try:
        t1n, t1p, t2n, t2p, _, stadium, _, _ = parse_simulate_payload(payload)
    except ValueError as exc:
        return await ctx.send(f"❌ {exc}")

    # Extract @mentions from team name lines
    def extract_uid(name_str):
        m = re.search(r"<@!?(\d+)>", name_str)
        return int(m.group(1)) if m else None

    def clean_name(name_str):
        return re.sub(r"<@!?\d+>", "", name_str).strip().strip("()").strip()

    t1_uid = extract_uid(t1n); t2_uid = extract_uid(t2n)
    t1n = clean_name(t1n);     t2n = clean_name(t2n)

    t1_list, unk1 = build_player_list(t1n, t1p)
    t2_list, unk2 = build_player_list(t2n, t2p)
    if len(t1_list)<2 or len(t2_list)<2:
        return await ctx.send("❌ Each team needs at least 2 players.")
    t1_list=t1_list[:11]; t2_list=t2_list[:11]
    extra_note = ("Generic stats: "+", ".join(unk1+unk2)) if (unk1 or unk2) else None

    # Determine challenger/opponent
    challenger_id = ctx.author.id
    # The opponent is whichever uid is NOT the challenger, or None if no mentions
    opponent_id = None
    if t1_uid and t1_uid != challenger_id:
        opponent_id = t1_uid
    elif t2_uid and t2_uid != challenger_id:
        opponent_id = t2_uid

    challenge_data = {
        "challenger_id": challenger_id,
        "opponent_id": opponent_id,
        "t1n": t1n, "t1_list": t1_list, "t1_uid": t1_uid,
        "t2n": t2n, "t2_list": t2_list, "t2_uid": t2_uid,
        "stadium": stadium, "extra_note": extra_note,
        "ctx": ctx,
    }

    if opponent_id:
        # Send challenge request
        pending_challenges[opponent_id] = challenge_data
        opp = ctx.guild.get_member(opponent_id)
        opp_mention = opp.mention if opp else f"<@{opponent_id}>"
        em = discord.Embed(
            title="⚔️ Match Challenge!",
            description=(
                f"{ctx.author.mention} has challenged {opp_mention} to a cricket match!\n\n"
                f"🏏 **{t1n}** vs **{t2n}**\n"
                f"{'🏟️ ' + stadium if stadium else ''}\n\n"
                f"{opp_mention} — Do you **Accept** or **Decline**?"
            ),
            color=0xff6600
        )
        em.set_footer(text="Challenge expires in 5 minutes.")
        await ctx.send(embed=em, view=ChallengeView(challenge_data, ctx.channel))
    else:
        # No opponent tagged — go straight to setup (solo mode)
        await _start_interactive_setup(ctx, ctx.channel, challenge_data)


# ─────────────────────────────────────────────
# +xi  — captain submits playing XI for an interactive match setup
# ─────────────────────────────────────────────
@bot.command(name="myxi", aliases=["pickxi","setxi","submitxi"])
async def submit_xi(ctx, *, payload: str = None):
    """Submit your playing XI for an active `+interactive @u1 @u2` setup.\n\nUsage:\n+myxi <TeamName> | player1, player2, player3, ..., player11\nOr list players on separate lines:\n+xi <TeamName>\nplayer1\nplayer2\n...\nPick ANY player you want — known players use real stats, unknown\nplayers get generic stats automatically.
    """
    setup = pending_xi_setups.get(ctx.channel.id)
    if not setup:
        return await ctx.send(
            "❌ No interactive match setup is active in this channel.\n"
            "Start one with `+interactive @user1 @user2`."
        )
    if ctx.author.id not in setup["captains"]:
        return await ctx.send("❌ Only the two tagged captains can submit an XI.")
    if not payload or not payload.strip():
        return await ctx.send(
            "❌ Usage: `+xi <TeamName> | player1, player2, ..., player11`"
        )

    # Parse: either "TeamName | p1, p2, ..." or "TeamName\np1\np2\n..."
    text = payload.strip()
    team_name = None
    player_lines = []
    if "|" in text and "\n" not in text:
        head, tail = text.split("|", 1)
        team_name = head.strip()
        player_lines = [p.strip() for p in re.split(r"[,;\n]+", tail) if p.strip()]
    else:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return await ctx.send("❌ No team name or players given.")
        first = lines[0]
        if "|" in first:
            head, tail = first.split("|", 1)
            team_name = head.strip()
            extras = [p.strip() for p in re.split(r"[,;]+", tail) if p.strip()]
            player_lines = extras + lines[1:]
        else:
            team_name = first.strip()
            rest = lines[1:]
            # If a single comma-separated line was given alongside name, split it
            expanded = []
            for r in rest:
                if "," in r:
                    expanded.extend([x.strip() for x in r.split(",") if x.strip()])
                else:
                    expanded.append(r)
            player_lines = expanded

    if not team_name:
        return await ctx.send("❌ Team name is required.")
    if len(player_lines) < 2:
        return await ctx.send("❌ Provide at least 2 players (ideally 11).")
    player_lines = player_lines[:11]

    setup["teams"][ctx.author.id] = {
        "name": team_name,
        "raw_players": player_lines,
    }

    # Acknowledge
    em = discord.Embed(
        title=f"✅ XI submitted — {team_name}",
        description=f"{ctx.author.mention} locked in **{len(player_lines)}** players.",
        color=0x00e676,
    )
    em.add_field(name="Players", value="\n".join(f"• {p}" for p in player_lines), inline=False)
    other = [uid for uid in setup["order"] if uid != ctx.author.id][0]
    if other not in setup["teams"]:
        opp = setup["captains"][other]
        em.set_footer(text=f"Waiting on {opp.display_name} to submit their XI…")
    await ctx.send(embed=em)

    # If both captains have submitted → start the match
    if all(uid in setup["teams"] for uid in setup["order"]):
        del pending_xi_setups[ctx.channel.id]
        await _begin_interactive_from_xi_setup(setup)


@bot.command(name="cancelxi", aliases=["cancelinteractive"])
async def cancel_xi(ctx):
    """Cancel an active `+interactive @u1 @u2` setup in this channel."""
    setup = pending_xi_setups.get(ctx.channel.id)
    if not setup:
        return await ctx.send("❌ No interactive setup is active here.")
    if ctx.author.id not in setup["captains"] and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only a captain or an admin can cancel.")
    del pending_xi_setups[ctx.channel.id]
    await ctx.send("🛑 Interactive match setup cancelled.")


async def _begin_interactive_from_xi_setup(setup):
    """Both XIs received — build the challenge_data and start interactive setup flow."""
    ctx     = setup["ctx"]
    channel = setup["channel"]
    u1_id, u2_id = setup["order"]
    t1 = setup["teams"][u1_id]
    t2 = setup["teams"][u2_id]

    t1_list, unk1 = build_player_list(t1["name"], t1["raw_players"])
    t2_list, unk2 = build_player_list(t2["name"], t2["raw_players"])
    if len(t1_list) < 2 or len(t2_list) < 2:
        return await channel.send("❌ Each team needs at least 2 valid players.")
    t1_list = t1_list[:11]; t2_list = t2_list[:11]
    extra_note = ("Generic stats: " + ", ".join(unk1 + unk2)) if (unk1 or unk2) else None

    challenge_data = {
        "challenger_id": u1_id,
        "opponent_id": u2_id,
        "t1n": t1["name"], "t1_list": t1_list, "t1_uid": u1_id,
        "t2n": t2["name"], "t2_list": t2_list, "t2_uid": u2_id,
        "stadium": setup.get("stadium"),
        "extra_note": extra_note,
        "ctx": ctx,
    }
    em = discord.Embed(
        title="🏏 Both XIs Locked In — Starting Match Setup!",
        description=f"**{t1['name']}** vs **{t2['name']}**",
        color=0x00e676,
    )
    if extra_note:
        em.add_field(name="📝 Note", value=extra_note, inline=False)
    await channel.send(embed=em)
    await _start_interactive_setup(ctx, channel, challenge_data)


class ChallengeView(discord.ui.View):
    def __init__(self, data, channel):
        super().__init__(timeout=300)
        self.data = data
        self.channel = channel

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        d = self.data
        opp_id = d["opponent_id"]
        if interaction.user.id != opp_id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        if opp_id in pending_challenges:
            del pending_challenges[opp_id]
        em = discord.Embed(
            title="✅ Challenge Accepted!",
            description=f"**{d['t1n']}** vs **{d['t2n']}** — Let's go! Setting up match...",
            color=0x00ff00
        )
        await interaction.response.edit_message(embed=em, view=None)
        await _start_interactive_setup(d["ctx"], self.channel, d)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        d = self.data
        if interaction.user.id not in (d["opponent_id"], d["challenger_id"]):
            return await interaction.response.send_message("❌ Not your challenge!", ephemeral=True)
        if d["opponent_id"] in pending_challenges:
            del pending_challenges[d["opponent_id"]]
        em = discord.Embed(title="❌ Challenge Declined", color=0xff0000,
            description="The match challenge was declined.")
        await interaction.response.edit_message(embed=em, view=None)


async def _start_interactive_setup(ctx, channel, data):
    """Show home team selector to start interactive setup."""
    t1n = data["t1n"]; t2n = data["t2n"]
    em = discord.Embed(
        title="🏠 Interactive Match — Select Home Team",
        description=(
            f"**{t1n}** vs **{t2n}**\n\nWho is playing at **home**? Home team wins toss 60% of the time.\nSelect **Neutral** for equal toss odds."
        ),
        color=0xff6600
    )
    if data.get("stadium"): em.add_field(name="🏟️ Stadium", value=data["stadium"], inline=True)
    await channel.send(embed=em, view=IMatchHomeView(ctx, channel, data))


class IMatchHomeView(discord.ui.View):
    def __init__(self, ctx, channel, data):
        super().__init__(timeout=180)
        self.ctx=ctx; self.channel=channel; self.data=data
        t1n=data["t1n"]; t2n=data["t2n"]
        opts=[
            discord.SelectOption(label=f"🏠 {t1n}", value=t1n, description=f"{t1n} has home advantage"),
            discord.SelectOption(label=f"🏠 {t2n}", value=t2n, description=f"{t2n} has home advantage"),
            discord.SelectOption(label="⚖️ Neutral Venue", value="__neutral__"),
        ]
        sel=discord.ui.Select(placeholder="🏠 Select home team…", options=opts)
        sel.callback=self._cb; self.add_item(sel)

    async def _cb(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the match organiser can set this.", ephemeral=True)
        val=interaction.data["values"][0]
        self.data["home_team"] = None if val=="__neutral__" else val
        em=discord.Embed(title="🏏 Select Pitch Conditions",
            description=f"**{self.data['t1n']}** vs **{self.data['t2n']}**\nChoose the pitch:",
            color=0xff6600)
        for p in PITCH_OPTIONS:
            em.add_field(name=f"{p['emoji']} {p['name']}", value=p["short"], inline=False)
        await interaction.response.edit_message(embed=em, view=IMatchPitchView(self.ctx, self.channel, self.data))


class IMatchPitchView(discord.ui.View):
    def __init__(self, ctx, channel, data):
        super().__init__(timeout=180)
        self.ctx=ctx; self.channel=channel; self.data=data
        opts=[discord.SelectOption(label=f"{p['emoji']} {p['name']}", value=p["key"], description=p["short"][:100]) for p in PITCH_OPTIONS]
        sel=discord.ui.Select(placeholder="🏟️ Select pitch…", options=opts)
        sel.callback=self._cb; self.add_item(sel)

    async def _cb(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the organiser can set this.", ephemeral=True)
        pk=interaction.data["values"][0]
        pinfo=PITCH_KEY_MAP[pk]
        self.data["pitch_key"]=pk
        self.data["pitch_label"]=f"{pinfo['emoji']} {pinfo['name']}"

        # ── TOSS ──────────────────────────────────────────────────────
        home=self.data.get("home_team")
        t1n=self.data["t1n"]; t2n=self.data["t2n"]
        t1_wins = random.random() < (0.6 if home==t1n else 0.4 if home==t2n else 0.5)
        toss_winner = t1n if t1_wins else t2n
        self.data["toss_winner"]=toss_winner

        pitch_flavor = {
            "flat":     "🌤️ Perfect batting conditions — expect a high-scoring game!",
            "green":    "🌿 Overcast, green top — pacers will be licking their lips!",
            "spin":     "🌀 Dry, dusty surface — spinners will dominate!",
            "dew":      "💧 Heavy dew expected — second innings batting becomes easier!",
            "slow":     "🪨 Slow & low — timing is everything here!",
            "altitude": "⛰️ High altitude — the ball flies off the bat!",
        }
        flavor = pitch_flavor.get(pk, "")
        em=discord.Embed(
            title=f"🪙 TOSS — {toss_winner} wins!",
            description=(
                f"**{toss_winner}** won the toss and will decide!\n\n"
                f"**🏟️ Pitch:** {self.data['pitch_label']}\n"
                f"_{pinfo['desc']}_\n"
                f"{flavor}\n\n"
                f"**{toss_winner}**, what do you choose?"
            ),
            color=0xf1c40f
        )
        em.set_footer(text="Home advantage gives 60% toss win probability")
        await interaction.response.edit_message(embed=em, view=IMatchTossView(self.ctx, self.channel, self.data))


class IMatchTossView(discord.ui.View):
    def __init__(self, ctx, channel, data):
        super().__init__(timeout=180)
        self.ctx=ctx; self.channel=channel; self.data=data

    def _get_toss_uid(self):
        d=self.data
        if d["toss_winner"]==d["t1n"]: return d.get("t1_uid") or d["ctx"].author.id
        else: return d.get("t2_uid") or d["ctx"].author.id

    @discord.ui.button(label="🏏 Bat First", style=discord.ButtonStyle.primary)
    async def bat(self, interaction, button):
        toss_uid = self._get_toss_uid()
        if interaction.user.id != toss_uid:
            return await interaction.response.send_message("❌ Only the toss winner decides!", ephemeral=True)
        await self._start(interaction, toss_winner_bats=True)

    @discord.ui.button(label="🎯 Bowl First", style=discord.ButtonStyle.secondary)
    async def bowl(self, interaction, button):
        toss_uid = self._get_toss_uid()
        if interaction.user.id != toss_uid:
            return await interaction.response.send_message("❌ Only the toss winner decides!", ephemeral=True)
        await self._start(interaction, toss_winner_bats=False)

    async def _start(self, interaction, toss_winner_bats):
        d=self.data
        tw=d["toss_winner"]
        if (tw==d["t1n"]) == toss_winner_bats:
            bat_n,bat_l,bat_uid = d["t1n"],d["t1_list"],d.get("t1_uid")
            bwl_n,bwl_l,bwl_uid = d["t2n"],d["t2_list"],d.get("t2_uid")
        else:
            bat_n,bat_l,bat_uid = d["t2n"],d["t2_list"],d.get("t2_uid")
            bwl_n,bwl_l,bwl_uid = d["t1n"],d["t1_list"],d.get("t1_uid")

        # Impact player: if squad > 11, last player is impact player
        def _split_impact(lst):
            if len(lst) > 11:
                return lst[:11], lst[-1]['name']
            return lst, None
        bat_l_xi, bat_imp = _split_impact(bat_l)
        bwl_l_xi, bwl_imp = _split_impact(bwl_l)

        match = MatchState(self.channel.id, str(bat_uid or "solo"), str(bwl_uid or "solo"),
                           bat_n, bwl_n, bat_l_xi, bwl_l_xi,
                           pitch_type=d.get("pitch_key"), home_team=d.get("home_team"))
        match.impact_player_bat  = bat_imp
        match.impact_player_bowl = bwl_imp
        if bat_imp:
            match.available_batters.append(bat_imp)
        # All 11 players can bowl in interactive — override bowlers_pool
        match.bowlers_pool = [p["name"] for p in bwl_l_xi]
        match.bowler_overs = {p["name"]: 0 for p in bwl_l_xi}
        active_matches[self.channel.id] = match
        # Store toss result for live scorecard footer
        decision = "bat" if toss_winner_bats else "bowl"
        d["toss_result"] = f"{tw} won toss & chose to {decision} first"
        d["_bat_uid"] = str(bat_uid or "solo")
        d["_bwl_uid"] = str(bwl_uid or "solo")

        decision_txt = "bat" if toss_winner_bats else "bowl"
        em=discord.Embed(
            title="🏟️ MATCH BEGINS!",
            description=(
                f"🏏 **{bat_n}** will bat first\n"
                f"🎳 **{bwl_n}** will bowl first\n\n"
                f"**{tw}** won the toss and chose to **{decision_txt}** first\n"
                f"**Pitch:** {d['pitch_label']}"
            ),
            color=0x00e676
        )
        if d.get("stadium"): em.add_field(name="🏟️ Stadium", value=d["stadium"], inline=True)
        em.add_field(name="🎯 First Up", value=f"**{bwl_n}** — pick your opening bowler!", inline=False)
        em.set_footer(text="Max 4 overs per bowler · No consecutive overs · All 11 can bowl")
        await interaction.response.edit_message(embed=em, view=None)
        await self.channel.send(
            embed=discord.Embed(
                title=f"🎳 Choose Bowler — Over 1",
                description=f"**{bwl_n}** captain, select your opening bowler!",
                color=0x9b59b6),
            view=IMatchBowlerView(match, self.channel, self.data)
        )


class IMatchBowlerView(discord.ui.View):
    """Bowler selection — ALL players eligible, not just BOWL/ALR."""
    def __init__(self, match, channel, data):
        super().__init__(timeout=300)
        self.match=match; self.channel=channel; self.data=data
        last_bowl = getattr(match, '_last_completed_bowler', None)
        opts=[]
        for n in match.bowlers_pool[:25]:
            s=match.bowl_stats.get(n,{})
            ov=s.get("balls",0)//6
            role=ALL_PLAYERS.get(n,{}).get("role","BAT")
            rem = 4 - ov  # max 4 overs each in T20
            if rem <= 0: continue
            # Exclude last bowler from dropdown (can't bowl consecutive overs)
            if n == last_bowl and len([x for x in match.bowlers_pool if match.bowl_stats.get(x,{}).get("balls",0)//6 < 4]) > 1:
                continue
            re_={"BOWL":"🎯","ALR":"⚡","BAT":"🏏","WK":"🧤"}.get(role,"🏏")
            opts.append(discord.SelectOption(
                label=f"{re_} {n} ({ov} ov, {rem} rem)"[:100], value=n))
        if not opts:
            opts=[discord.SelectOption(label="All bowlers used", value="__none__")]
        sel=discord.ui.Select(placeholder=f"⚾ Pick bowler for Over {match.overs+1}…", options=opts[:25], row=0)
        sel.callback=self._cb; self.add_item(sel)
        # Quick Sim button — simulates rest of innings automatically
        qs_btn = discord.ui.Button(label="⚡ Quick Sim Innings", style=discord.ButtonStyle.secondary, row=1)
        async def _quick_sim(interaction, _b=qs_btn):
            uid=self._get_bowl_uid()
            if uid and str(uid) != "None" and interaction.user.id != uid:
                return await interaction.response.send_message("❌ Only the bowling captain can quick-sim!", ephemeral=True)
            await interaction.response.edit_message(content="⚡ Quick simming rest of innings…", embed=None, view=None)
            # Auto-assign bowlers and simulate all remaining overs
            m = self.match
            remaining_overs = TOTAL_OVERS - m.overs
            for _ in range(remaining_overs * 10):  # safety limit
                if m.innings_done() or m.chase_won():
                    break
                if m.balls_in_over == 0:
                    # Pick bowler with fewest overs who has overs left
                    pool = [n for n in m.bowlers_pool if m.bowl_stats.get(n,{}).get("balls",0)//6 < 4]
                    if not pool: pool = m.bowlers_pool[:1]
                    if pool:
                        m.current_bowler = min(pool, key=lambda n: m.bowl_stats.get(n,{}).get("balls",0))
                lines2, event2 = m.simulate_until_event()
                if event2 in ("innings_done","match_won"):
                    if m.innings==1 and event2=="innings_done":
                        await _imatch_end_innings(m, self.channel, self.data)
                    else:
                        await _imatch_end_match(m, self.channel, self.data)
                    return
                if event2=="wicket" and m.available_batters:
                    next_bat = m.available_batters.pop(0)
                    m.on_strike = next_bat
                    m.bat_stats.setdefault(next_bat,{"runs":0,"balls":0,"out":False})
                    m.innings_bat_stats[m.innings].setdefault(next_bat,{"runs":0,"balls":0,"out":False,"fours":0,"sixes":0,"dismissal":"not out"})
            # If we exit loop without ending, force end
            if m.innings==1:
                await _imatch_end_innings(m, self.channel, self.data)
            else:
                await _imatch_end_match(m, self.channel, self.data)
        qs_btn.callback = _quick_sim
        self.add_item(qs_btn)

    def _get_bowl_uid(self):
        # Return uid of the team CURRENTLY bowling (swaps in inn2)
        d=self.data; m=self.match
        current_bowling = m.get_bowling_name()   # correctly swapped in inn2
        if current_bowling == d.get("t1n"):
            return d.get("t1_uid") or d["ctx"].author.id
        elif current_bowling == d.get("t2n"):
            return d.get("t2_uid") or d["ctx"].author.id
        return d["ctx"].author.id

    async def _cb(self, interaction):
        uid=self._get_bowl_uid()
        # Allow anyone if solo (no uid set)
        if uid and str(uid) != "None" and interaction.user.id != uid:
            return await interaction.response.send_message(
                f"❌ Only **{self.match.get_bowling_name()}** captain picks the bowler!", ephemeral=True)
        bowler=interaction.data["values"][0]
        if bowler=="__none__":
            return await interaction.response.send_message("❌ No bowlers with overs remaining!", ephemeral=True)
        # Enforce 4-over max per bowler
        s=self.match.bowl_stats.get(bowler,{})
        if s.get("balls",0)//6 >= 4:
            return await interaction.response.send_message(f"❌ {bowler} has already bowled 4 overs!", ephemeral=True)
        # Block consecutive overs — same bowler can't bowl two in a row
        last_bowler = getattr(self.match, '_last_completed_bowler', None)
        if bowler == last_bowler and len(self.match.bowlers_pool) > 1:
            return await interaction.response.send_message(
                f"❌ **{bowler}** just bowled the last over! A different bowler must bowl this over.", ephemeral=True)
        self.match.current_bowler=bowler
        await interaction.response.edit_message(
            content=f"⚾ **{bowler}** is bowling Over {self.match.overs+1}…", embed=None, view=None)
        lines, event = self.match.simulate_until_event()
        await _imatch_do_event(self.match, self.channel, self.data, lines, event)


class IMatchBatterView(discord.ui.View):
    """Batter selection after a wicket — shown to batting team captain."""
    def __init__(self, match, channel, data):
        super().__init__(timeout=300)
        self.match=match; self.channel=channel; self.data=data
        opts=[discord.SelectOption(
            label=f"🏏 {n}"[:100], value=n) for n in match.available_batters[:25]]
        if not opts:
            opts=[discord.SelectOption(label="No batters remaining", value="__none__")]
        sel=discord.ui.Select(placeholder="🏏 Send in next batter…", options=opts)
        sel.callback=self._cb; self.add_item(sel)

    def _get_bat_uid(self):
        d=self.data; m=self.match
        current_batting = m.get_batting_name()   # correctly swapped in inn2
        if current_batting == d.get("t1n"): return d.get("t1_uid") or d["ctx"].author.id
        return d.get("t2_uid") or d["ctx"].author.id

    async def _cb(self, interaction):
        uid=self._get_bat_uid()
        if uid and str(uid) != "None" and interaction.user.id != uid:
            return await interaction.response.send_message(
                f"❌ Only **{self.match.get_batting_name()}** captain sends in the batter!", ephemeral=True)
        batter=interaction.data["values"][0]
        if batter=="__none__":
            return await interaction.response.send_message("❌ No batters left!", ephemeral=True)
        m=self.match
        if batter in m.available_batters: m.available_batters.remove(batter)
        m.on_strike=batter
        m.bat_stats.setdefault(batter,{"runs":0,"balls":0,"out":False})
        m.innings_bat_stats[m.innings].setdefault(batter,{"runs":0,"balls":0,"out":False,"fours":0,"sixes":0,"dismissal":"not out"})
        batters_left = len(m.available_batters)
        em=discord.Embed(
            title=f"🏏 {batter} walks in!",
            description=(
                f"**{batter}** is the new batter!\n"
                f"Wickets left: **{10 - m.wickets}** · Batters in shed: **{batters_left}**"
            ),
            color=0x3498db)
        em.add_field(name="📊 Score", value=f"**{m.runs}/{m.wickets}** ({m.overs}.{m.balls_in_over} ov)", inline=True)
        if m.innings == 2 and m.target:
            needed = m.target - m.runs
            balls_left = (TOTAL_OVERS - m.overs)*6 - m.balls_in_over
            em.add_field(name="🎯 Need", value=f"**{needed}** off **{balls_left}** balls", inline=True)
        await interaction.response.edit_message(embed=em, view=None)
        # Check if over is still in progress (balls remain) or complete
        balls_bowled_this_over = m.balls_in_over  # 0 means over just ended
        over_in_progress = balls_bowled_this_over > 0 and balls_bowled_this_over < 6
        if over_in_progress:
            # Continue current over with same bowler
            lines2, event2 = m.simulate_until_event()
            await _imatch_do_event(m, self.channel, self.data, lines2, event2)
        else:
            # Over is done (wicket on ball 6 or start of new over) — pick new bowler
            if not m.innings_done() and not m.chase_won():
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"🎯 Choose Bowler — Over {m.overs+1}",
                        color=0x9b59b6,
                        description=f"**{m.bowling_name}**, pick your bowler for Over {m.overs+1}!"),
                    view=IMatchBowlerView(m, self.channel, self.data))
            else:
                # Innings/match ended
                if m.innings==1:
                    await _imatch_end_innings(m, self.channel, self.data)
                else:
                    await _imatch_end_match(m, self.channel, self.data)



def _build_live_scorecard_embed(match, lines, event, data):
    NL = "\n"
    inn_label = "1st Innings" if match.innings == 1 else "2nd Innings"
    inn_emoji = "🏏" if match.innings == 1 else "🎯"
    bf_t = match.overs * 6 + match.balls_in_over
    crr_v = round(match.runs / max(1, bf_t / 6), 2)

    # Dynamic color based on match state
    if match.innings == 2 and match.target:
        needed    = match.target - match.runs
        balls_left = (TOTAL_OVERS - match.overs) * 6 - match.balls_in_over
        rrr_val   = round(needed / max(0.1, balls_left / 6), 2)
        if rrr_val > 15:   color = 0xe74c3c
        elif rrr_val > 12: color = 0xe67e22
        elif rrr_val > 9:  color = 0xf1c40f
        elif rrr_val > 6:  color = 0x2ecc71
        else:              color = 0x1abc9c
    else:
        if crr_v > 12:   color = 0x9b59b6
        elif crr_v > 9:  color = 0x3498db
        elif crr_v > 7:  color = 0x1abc9c
        else:            color = 0x95a5a6

    over_str = f"{match.overs}.{match.balls_in_over}/20"

    # Momentum dots (last 6 balls)
    dot_map = []
    for ln in (lines or [])[-6:]:
        ll = ln.lower()
        if "six" in ll:        dot_map.append("🟣")
        elif "four" in ll:     dot_map.append("🟦")
        elif "wicket" in ll or " out" in ll: dot_map.append("🔴")
        elif "wide" in ll or "no ball" in ll: dot_map.append("🟡")
        elif "dot" in ll or "0 run" in ll: dot_map.append("⬛")
        else:                  dot_map.append("🟩")
    momentum = " ".join(dot_map) if dot_map else "⬛ ⬛ ⬛ ⬛ ⬛ ⬛"

    on = match.on_strike or "—"
    ns = match.non_striker or "—"

    # Build description
    if match.innings == 2 and match.target:
        proj_txt = f"🎯 Need **{needed}** off **{balls_left}** balls  |  RRR: **{rrr_val}**"
        chasing  = f"*(Chasing {match.target} — {match.bowling_name})*"
        desc = (f"# {match.runs}/{match.wickets}  `({over_str})`\n"
                f"CRR **{crr_v}**  {proj_txt}\n{chasing}")
    else:
        proj = int(crr_v * 20) if bf_t > 6 else "—"
        desc = (f"# {match.runs}/{match.wickets}  `({over_str})`\n"
                f"CRR **{crr_v}**  ·  Projected: **{proj}**")

    em = discord.Embed(title=f"{inn_emoji} {inn_label} — {match.get_batting_name()}",
                       description=desc, color=color)

    # ── BATTERS TABLE ─────────────────────────────────────────────────────────
    def bline(name, striker=False):
        s  = match.bat_stats.get(name, {})
        r  = s.get("runs", 0); b = s.get("balls", 0)
        sr = round(r / b * 100, 1) if b > 0 else 0.0
        mil = " ⚡" if r >= 100 else (" 🔥" if r >= 50 else "")
        ptr = " ◄" if striker else ""
        fours  = s.get("fours", 0); sixes = s.get("sixes", 0)
        return f"`{name[:14]:<14} {r:>3}({b}) 4s:{fours} 6s:{sixes} SR:{sr:.0f}`{mil}{ptr}"

    on_s  = match.bat_stats.get(on, {}); ns_s = match.bat_stats.get(ns, {})
    p_r   = on_s.get("runs", 0) + ns_s.get("runs", 0)
    p_b   = on_s.get("balls", 0) + ns_s.get("balls", 0)

    bat_txt = (f"`{'BATTERS':<14} {'R':>3}(B)  4s 6s  SR`\n"
               f"`{'─'*40}`\n"
               f"{bline(on, striker=True)}\n")
    if ns and ns != "—":
        bat_txt += f"{bline(ns)}\n"
    bat_txt += f"`Partnership: {p_r}({p_b})`"
    em.add_field(name="🏏 At the Crease", value=bat_txt, inline=False)

    # ── BOWLER TABLE ──────────────────────────────────────────────────────────
    bowler = match.current_bowler or "—"
    bw     = match.bowl_stats.get(bowler, {})
    bw_ov  = f"{bw.get('balls',0)//6}.{bw.get('balls',0)%6}"
    econ   = round(bw.get("runs",0) / max(0.1, bw.get("balls",0)/6), 1)
    bowl_txt = (f"`{'BOWLER':<14} {'O':>4}  {'R':>3}  {'W':>2}  ECN`\n"
                f"`{'─'*40}`\n"
                f"`{bowler[:14]:<14} {bw_ov:>4}  {bw.get('runs',0):>3}  "
                f"{bw.get('wickets',0):>2}  {econ}`")
    em.add_field(name="🎳 Bowling", value=bowl_txt, inline=False)

    # ── THIS OVER COMMENTARY ──────────────────────────────────────────────────
    if lines:
        # Enrich commentary with emojis
        rich = []
        for ln in lines[-6:]:
            ll = ln.lower()
            if "six" in ll:       rich.append(f"🟣 {ln}")
            elif "four" in ll:    rich.append(f"🟦 {ln}")
            elif "wicket" in ll or " out" in ll: rich.append(f"🔴 {ln}")
            elif "wide" in ll:    rich.append(f"🟡 {ln}")
            elif "no ball" in ll: rich.append(f"🟡 {ln}")
            else:                 rich.append(f"▪️ {ln}")
        em.add_field(name=f"📣 Over {match.overs} Commentary", value="\n".join(rich), inline=False)

    # ── MOMENTUM ─────────────────────────────────────────────────────────────
    em.add_field(name="⚡ Last 6 Balls", value=momentum, inline=False)

    # ── MILESTONE ALERTS ─────────────────────────────────────────────────────
    milestones = []
    for nm, st in match.bat_stats.items():
        r = st.get("runs", 0)
        if r == 50:   milestones.append(f"🏅 **{nm}** hits a FIFTY!")
        elif r == 100: milestones.append(f"💯 **{nm}** scores a CENTURY!")
        elif r == 150: milestones.append(f"🚀 **{nm}** reaches 150!")
    for nm, st in match.bowl_stats.items():
        w = st.get("wickets", 0)
        if w == 3:   milestones.append(f"🎯 **{nm}** takes a 3-FER!")
        elif w == 5: milestones.append(f"🔥 **{nm}** FIVE-FER!")
    if milestones:
        em.add_field(name="🌟 Milestones", value="\n".join(milestones[-3:]), inline=False)

    # Footer
    toss = data.get("toss_result", "")
    pl   = data.get("pitch_label", "")
    footer_parts = [x for x in [toss, f"Pitch: {pl}" if pl else ""] if x]
    if footer_parts:
        em.set_footer(text=" | ".join(footer_parts))
    return em


async def _imatch_do_event(match, channel, data, lines, event):
    """Handle ball-by-ball results and route to next step."""
    em = _build_live_scorecard_embed(match, lines, event, data)
    await channel.send(embed=em)

    # Post milestone GIFs (50 / 100) if any batter just crossed
    try:
        await post_milestone_gifs(channel, match)
    except Exception as _e:
        print(f"[Milestone hook error] {_e}")

    if event=="wicket":
        # Post wicket celebration GIF for the bowler
        try:
            bowler = match.current_bowler or ""
            batter = getattr(match, "_last_wicket_batter", "") or ""
            if bowler:
                await post_wicket_gif(channel, bowler, batter, match)
        except Exception as _we:
            print(f"[Wicket GIF hook] {_we}")

        if match.wickets>=MAX_WICKETS or not match.available_batters:
            await _imatch_end_innings(match, channel, data)
        else:
            wem=discord.Embed(title="🔴 Wicket!",
                description=f"**{match.batting_name}** — who bats next? ({len(match.available_batters)} batter(s) remaining)",
                color=0xff0000)
            wem.add_field(name="📊 Score", value=match.scoreline(), inline=True)
            await channel.send(embed=wem, view=IMatchBatterView(match, channel, data))

    elif event in ("innings_done","match_won"):
        if match.innings==1 and event=="innings_done":
            await _imatch_end_innings(match, channel, data)
        else:
            await _imatch_end_match(match, channel, data)

    else:  # over_done
        if match.innings_done():
            if match.innings==1:
                await _imatch_end_innings(match, channel, data)
            else:
                await _imatch_end_match(match, channel, data)
        else:
            match._last_completed_bowler = match.current_bowler
            # Over summary stats
            last_bowler = match.current_bowler or "?"
            bw = match.bowl_stats.get(last_bowler, {})
            ov_str = f"{bw.get('balls',0)//6}.{bw.get('balls',0)%6}"
            eco    = round(bw.get("runs",0)/max(0.1, bw.get("balls",0)/6), 1)
            overs_left = TOTAL_OVERS - match.overs
            nxt = discord.Embed(
                title=f"✅ End of Over {match.overs}",
                description=(
                    f"**{last_bowler}**: {ov_str} ov  {bw.get('runs',0)}R  {bw.get('wickets',0)}W  Eco:{eco}\n"
                    f"**Score:** {match.runs}/{match.wickets} ({match.overs}/{TOTAL_OVERS} ov) · **{overs_left}** overs left\n\n"
                    f"**{match.bowling_name}**, pick your bowler for Over **{match.overs+1}**!"
                ),
                color=0x9b59b6)
            if match.innings == 2 and match.target:
                needed = match.target - match.runs
                balls_left = overs_left * 6
                rrr = round(needed/max(0.1, balls_left/6), 1)
                nxt.add_field(name="🎯 Chase", value=f"Need **{needed}** off **{balls_left}** balls · RRR **{rrr}**", inline=False)
            await channel.send(embed=nxt, view=IMatchBowlerView(match, channel, data))


async def _imatch_end_innings(match, channel, data):
    score1=match.scoreline()
    match.innings_scores[1]=score1
    target=match.runs+1; match.target=target; match.innings=2
    match._setup_innings()
    # In innings 2, the team that was bowling in inn1 now bats, and vice versa
    # bowlers_pool = the team now bowling = _inn1_batting (they batted in inn1, now bowl in inn2)
    # All 11 players from the now-bowling team can bowl
    match.bowlers_pool = [p["name"] for p in match._inn1_batting]
    match.bowler_overs = {p["name"]: 0 for p in match._inn1_batting}
    match._last_completed_bowler = None  # reset for new innings

    # Full batting scorecard inn1
    bat_rows = []
    top_scorer = ("", 0)
    for n, s in match.innings_bat_stats[1].items():
        if s.get("balls", 0) > 0:
            star = "*" if not s.get("out") else ""
            sr   = round(s["runs"]/max(1,s["balls"])*100, 0)
            dis  = s.get("dismissal","") if s.get("out") else "not out"
            bat_rows.append(f"`{n[:16]:<16} {s['runs']}{star:1}({s['balls']})  4s:{s.get('fours',0)} 6s:{s.get('sixes',0)}  SR:{sr:.0f}`")
            if s["runs"] > top_scorer[1]: top_scorer = (n, s["runs"])
    # Bowling
    bowl_rows = []
    best_bowl = ("", 0)
    for n, s in match.bowl_stats.items():
        if s.get("balls", 0) > 0:
            ov  = f"{s['balls']//6}.{s['balls']%6}"
            eco = round(s["runs"] / max(0.1, s["balls"]/6), 1)
            bowl_rows.append(f"`{n[:16]:<16} {ov}  {s['runs']}R  {s['wickets']}W  Eco:{eco}`")
            if s["wickets"] > best_bowl[1]: best_bowl = (n, s["wickets"])

    em = discord.Embed(
        title=f"🏁 Innings Break — {match.batting_name}",
        description=(
            f"## {score1}\n"
            f"**{match.bowling_name}** need **{target}** to win in {TOTAL_OVERS} overs!\n"
            + (f"⭐ Top scorer: **{top_scorer[0]}** ({top_scorer[1]})" if top_scorer[0] else "")
            + ("  |  " if top_scorer[0] and best_bowl[0] else "")
            + (f"🎳 Best bowler: **{best_bowl[0]}** ({best_bowl[1]}W)" if best_bowl[0] else "")
        ),
        color=0x9b59b6)
    if bat_rows:
        em.add_field(name="🏏 Batting Scorecard", value="\n".join(bat_rows[:11]), inline=False)
    if bowl_rows:
        em.add_field(name="🎳 Bowling Figures",   value="\n".join(bowl_rows[:8]),  inline=False)
    await channel.send(embed=em)
    inn2_batting = match.get_batting_name()   # team chasing in inn2
    inn2_bowling = match.get_bowling_name()   # team defending in inn2
    await channel.send(
        embed=discord.Embed(
            title=f"🎯 2nd Innings — {inn2_batting} need {target} to win!",
            description=(
                f"🏏 **{inn2_batting}** will bat (chasing {target})\n"
                f"🎳 **{inn2_bowling}** captain, pick your opening bowler!"
            ),
            color=0xff6600),
        view=IMatchBowlerView(match, channel, data))


async def _imatch_end_match(match, channel, data):
    score2=match.scoreline(); match.innings_scores[2]=score2
    s1=match.innings_scores.get(1,"0/0")
    inn1_runs=(match.target or 1)-1; inn2_runs=match.runs
    if inn2_runs>inn1_runs: winner=match.bowling_name; margin=f"by {MAX_WICKETS-match.wickets} wickets"
    elif inn1_runs>inn2_runs: winner=match.batting_name; margin=f"by {inn1_runs-inn2_runs} runs"
    else: winner="Match"; margin="TIED!"
    result_emoji = "🏆" if winner != "Match" else "🤝"
    result_txt   = f"{result_emoji} **{winner}** won {margin}!" if winner != "Match" else "🤝 **MATCH TIED!**"
    win_color    = 0x00e676 if winner != "Match" else 0xf1c40f

    # Build full final scorecard
    em = discord.Embed(
        title=f"🏏 MATCH OVER — {data.get('t1n','Team 1')} vs {data.get('t2n','Team 2')}",
        description=(
            f"{result_txt}\n\n"
            f"**{match.batting_name}** (Inn 1): **{s1}**\n"
            f"**{match.bowling_name}** (Inn 2): **{score2}**"
        ),
        color=win_color
    )
    # Batting highlights inn2
    bat2_rows = []
    for n, s in match.innings_bat_stats.get(2, {}).items():
        if s.get("balls",0) > 0:
            star = "*" if not s.get("out") else ""
            sr   = round(s["runs"]/max(1,s["balls"])*100, 0)
            bat2_rows.append(f"`{n[:14]:<14} {s['runs']}{star}({s['balls']})  SR:{sr:.0f}`")
    if bat2_rows:
        em.add_field(name=f"🏏 {match.bowling_name} Batting", value="\n".join(bat2_rows[:6]), inline=False)
    # POM
    pom, _ = pick_player_of_match(match)
    if pom:
        em.add_field(name="⭐ Player of the Match", value=f"**{pom}**", inline=False)
    if data.get("pitch_label"):
        em.add_field(name="🏟️ Pitch", value=data["pitch_label"], inline=True)
    if data.get("stadium"):
        em.add_field(name="🏟️ Stadium", value=data["stadium"], inline=True)
    await channel.send(embed=em)
    pl=data.get("pitch_label"); st=data.get("stadium"); xn=data.get("extra_note")
    await channel.send(
        embed=build_simulation_summary(match, pitch=pl, stadium=st, extra_note=xn),
        view=SimulationMenuView(match, pitch=pl, stadium=st, extra_note=xn))
    try:
        await send_scorecard(channel, match)
    except Exception as e:
        print(f"[IMatch Scorecard Error] {e}")
    if channel.id in active_matches:
        del active_matches[channel.id]


async def _end_innings(channel, match):
    score1 = match.scoreline()
    match.innings_scores[1] = score1

    bat_lines  = [f"**{n}** {s['runs']} ({s['balls']}b) — {'out' if s['out'] else 'not out*'}"
                  for n, s in match.bat_stats.items()]
    bowl_lines = [f"**{n}** {s['balls']//6}.{s['balls']%6}–{s['runs']}–{s['wickets']}"
                  for n, s in match.bowl_stats.items()]

    em = discord.Embed(
        title=f"🏁 End of Innings 1 — {match.get_batting_name()}: {score1}",
        color=0x9b59b6
    )
    if bat_lines:
        em.add_field(name="🏏 Batting", value="\n".join(bat_lines[:11]), inline=False)
    if bowl_lines:
        em.add_field(name="🎯 Bowling", value="\n".join(bowl_lines[:8]),  inline=False)

    match.innings = 2
    target        = match.runs + 1
    match.target  = target
    match._setup_innings()

    em.add_field(
        name="🎯 2nd Innings Target",
        value=f"**{match.get_batting_name()}** need **{target}** runs in {TOTAL_OVERS} overs!",
        inline=False
    )
    em.set_footer(text=f"{match.get_bowling_name()} — pick your opening bowler!")
    await channel.send(embed=em, view=BowlerSelectView(match, channel))


async def _end_match(channel, match, event):
    score2 = match.scoreline()
    match.innings_scores[2] = score2
    score1   = match.innings_scores.get(1, '?')
    inn1_runs = (match.target or 1) - 1
    inn2_runs = match.runs

    if event == 'match_won' or inn2_runs >= (match.target or 0):
        winner = match.get_batting_name()
        margin = f"by {MAX_WICKETS - match.wickets} wickets"
    elif inn2_runs < inn1_runs:
        winner = match.batting_name if match.innings == 1 else match.bowling_name
        margin = f"by {inn1_runs - inn2_runs} runs"
    else:
        winner = "No one — it's a"
        margin = "TIE!"

    em = discord.Embed(
        title="🏆 Match Over!",
        description=f"**{winner}** wins {margin}!",
        color=0xffd700
    )
    em.add_field(name=f"🏏 {match.batting_name} (Inn 1)", value=score1, inline=True)
    em.add_field(name=f"🏏 {match.bowling_name} (Inn 2)", value=score2, inline=True)

    top_bat = sorted(match.match_bat_stats.items(),  key=lambda x: -x[1]['runs'])[:3]
    top_bow = sorted(match.match_bowl_stats.items(), key=lambda x: -x[1]['wickets'])[:3]
    if top_bat:
        em.add_field(name="🌟 Top Scorers",
                     value="\n".join(f"**{n}** — {s['runs']} ({s['balls']}b)" for n, s in top_bat),
                     inline=False)
    if top_bow:
        em.add_field(name="🎯 Top Wicket-Takers",
                     value="\n".join(f"**{n}** — {s['wickets']} wkt, {s['runs']} runs" for n, s in top_bow),
                     inline=False)

    stats = load_json(STATS_FILE) if os.path.exists(STATS_FILE) else {}
    for name, s in match.match_bat_stats.items():
        e = stats.setdefault(name, {'matches': 0, 'runs': 0, 'balls_faced': 0,
                                    'wickets': 0, 'balls_bowled': 0, 'runs_conceded': 0})
        e['runs'] += s['runs']; e['balls_faced'] += s['balls']; e['matches'] += 1
    for name, s in match.match_bowl_stats.items():
        e = stats.setdefault(name, {'matches': 0, 'runs': 0, 'balls_faced': 0,
                                    'wickets': 0, 'balls_bowled': 0, 'runs_conceded': 0})
        e['wickets'] += s['wickets']; e['balls_bowled'] += s['balls']; e['runs_conceded'] += s['runs']
        if name not in match.match_bat_stats:
            e['matches'] += 1
    save_json(stats, STATS_FILE)

    del active_matches[match.channel_id]
    await channel.send(embed=em)


class BowlerSelectView(discord.ui.View):
    def __init__(self, match: MatchState, channel):
        super().__init__(timeout=300)
        self.match = match; self.channel = channel
        opts = [discord.SelectOption(label=n[:80], value=n) for n in match.bowlers_pool[:25]]
        if not opts:
            opts = [discord.SelectOption(label='Default Bowler', value='Default Bowler')]
        sel = discord.ui.Select(
            placeholder=f"⚾ Choose bowler for over {match.overs + 1}…", options=opts)
        sel.callback = self._on_select
        self.add_item(sel)

    async def interaction_check(self, interaction):
        if str(interaction.user.id) != self.match.get_bowling_uid():
            await interaction.response.send_message(
                f"❌ Only **{self.match.get_bowling_name()}** can pick the bowler!", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        bowler = interaction.data['values'][0]
        self.match.current_bowler = bowler
        await interaction.response.edit_message(
            content=f"⚾ **{bowler}** is bowling over {self.match.overs + 1}…", embed=None, view=None)
        lines, event = self.match.simulate_until_event()
        await _do_event(interaction, self.match, self.channel, lines, event)


class BatterSelectView(discord.ui.View):
    def __init__(self, match: MatchState, channel):
        super().__init__(timeout=300)
        self.match = match; self.channel = channel
        opts = [discord.SelectOption(label=n[:80], value=n) for n in match.available_batters[:25]]
        if not opts:
            opts = [discord.SelectOption(label='No batters left', value='__none__')]
        sel = discord.ui.Select(placeholder="🏏 Choose your next batter…", options=opts)
        sel.callback = self._on_select
        self.add_item(sel)

    async def interaction_check(self, interaction):
        if str(interaction.user.id) != self.match.get_batting_uid():
            await interaction.response.send_message(
                f"❌ Only **{self.match.get_batting_name()}** can pick the batter!", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        batter = interaction.data['values'][0]
        if batter == '__none__':
            await interaction.response.send_message("❌ No batters left!", ephemeral=True)
            return
        if batter in self.match.available_batters:
            self.match.available_batters.remove(batter)
        self.match.on_strike = batter
        if not self.match.current_bowler and self.match.bowlers_pool:
            self.match.current_bowler = self.match.bowlers_pool[0]
        self.match.bat_stats.setdefault(batter, {'runs': 0, 'balls': 0, 'out': False})
        await interaction.response.edit_message(
            content=f"🏏 **{batter}** walks in to bat…", embed=None, view=None)
        lines, event = self.match.simulate_until_event()
        await _do_event(interaction, self.match, self.channel, lines, event)




# ─────────────────────────────────────────────────────────────────────────────
# IPL 2025 SQUADS  (10 teams)
# ─────────────────────────────────────────────────────────────────────────────
IPL_SQUADS = {
    "CSK": {
        "full": "Chennai Super Kings",
        "emoji": "🦁",
        "color": 0xf7c200,
        "players": [
            "Ruturaj Gaikwad","Devon Conway","Rachin Ravindra","Shivam Dube",
            "Rahul Tripathi","MS Dhoni","Sameer Rizvi","Ravindra Jadeja",
            "Sam Curran","Matheesha Pathirana","Khaleel Ahmed",
        ],
    },
    "MI": {
        "full": "Mumbai Indians",
        "emoji": "🔵",
        "color": 0x005da0,
        "players": [
            "Rohit Sharma","Ryan Rickelton","Suryakumar Yadav","Tilak Varma",
            "Hardik Pandya","Naman Dhir","Will Jacks","Mitchell Santner",
            "Jasprit Bumrah","Allah Ghazanfar","Karn Sharma",
        ],
    },
    "RCB": {
        "full": "Royal Challengers Bengaluru",
        "emoji": "🔴",
        "color": 0xec1c24,
        "players": [
            "Virat Kohli","Phil Salt","Devdutt Padikkal","Rajat Patidar",
            "Tim David","Liam Livingstone","Krunal Pandya","Jitesh Sharma",
            "Romario Shepherd","Bhuvneshwar Kumar","Josh Hazlewood",
        ],
    },
    "KKR": {
        "full": "Kolkata Knight Riders",
        "emoji": "🟣",
        "color": 0x3a225d,
        "players": [
            "Sunil Narine","Rahmanullah Gurbaz","Quinton de Kock","Ajinkya Rahane",
            "Rinku Singh","Venkatesh Iyer","Andre Russell","Ramandeep Singh",
            "Varun Chakravarthy","Harshit Rana","Anrich Nortje",
        ],
    },
    "SRH": {
        "full": "Sunrisers Hyderabad",
        "emoji": "🟠",
        "color": 0xff6b00,
        "players": [
            "Travis Head","Abhishek Sharma","Ishan Kishan","Heinrich Klaasen",
            "Nitish Kumar Reddy","Kamindu Mendis","Pat Cummins","Harshal Patel",
            "Mohammed Shami","Adam Zampa","Rahul Chahar",
        ],
    },
    "GT": {
        "full": "Gujarat Titans",
        "emoji": "🔷",
        "color": 0x1c4fa0,
        "players": [
            "Shubman Gill","Jos Buttler","Sai Sudharsan","Shahrukh Khan",
            "Rahul Tewatia","Anuj Rawat","Washington Sundar","Rashid Khan",
            "Kagiso Rabada","Mohammed Siraj","Prasidh Krishna",
        ],
    },
    "RR": {
        "full": "Rajasthan Royals",
        "emoji": "💗",
        "color": 0xe91e8c,
        "players": [
            "Yashasvi Jaiswal","Sanju Samson","Nitish Rana","Riyan Parag",
            "Shimron Hetmyer","Dhruv Jurel","Wanindu Hasaranga","Jofra Archer",
            "Maheesh Theekshana","Fazal Farooqi","Tushar Deshpande",
        ],
    },
    "DC": {
        "full": "Delhi Capitals",
        "emoji": "🔵",
        "color": 0x004c93,
        "players": [
            "Jake Fraser-McGurk","KL Rahul","Faf du Plessis","Karun Nair",
            "Axar Patel","Tristan Stubbs","Abishek Porel","Kuldeep Yadav",
            "Mitchell Starc","T Natarajan","Mohit Sharma",
        ],
    },
    "LSG": {
        "full": "Lucknow Super Giants",
        "emoji": "🐝",
        "color": 0x00a0e3,
        "players": [
            "Rishabh Pant","Nicholas Pooran","David Miller","Aiden Markram",
            "Mitchell Marsh","Abdul Samad","Shahbaz Ahmed","Ravi Bishnoi",
            "Mayank Yadav","Avesh Khan","Akash Deep",
        ],
    },
    "PBKS": {
        "full": "Punjab Kings",
        "emoji": "🦁",
        "color": 0xed1b24,
        "players": [
            "Shreyas Iyer","Prabhsimran Singh","Josh Inglis","Shashank Singh",
            "Priyansh Arya","Marcus Stoinis","Glenn Maxwell","Marco Jansen",
            "Arshdeep Singh","Lockie Ferguson","Yuzvendra Chahal",
        ],
    },
}

IPL_TEAM_KEYS = list(IPL_SQUADS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# +simipl COMMAND & VIEWS
# ─────────────────────────────────────────────────────────────────────────────
@bot.command(name="simipl")
async def simipl_command(ctx, opponent: discord.Member = None):
    """Start an IPL match simulation. Usage: +simipl @opponent (or solo)"""
    challenger_id = ctx.author.id
    opponent_id   = opponent.id if opponent else None

    em = discord.Embed(
        title="🏏 IPL Match — Select Your Team",
        description=(
            f"{'**Challenger:** ' + ctx.author.mention + ((' vs ' + opponent.mention) if opponent else '')}\n\n"
            "Select your **IPL team** from the dropdown below!"
        ),
        color=0xf7c200
    )
    for short, info in IPL_SQUADS.items():
        em.add_field(name=f"{info['emoji']} {short} — {info['full']}", value="\u200b", inline=True)

    data = {
        "challenger_id": challenger_id,
        "opponent_id": opponent_id,
        "challenger_member": ctx.author,
        "opponent_member": opponent,
        "ctx": ctx,
    }
    await ctx.send(embed=em, view=IPLTeamSelectView(ctx, ctx.channel, data, role="challenger"))


class IPLTeamSelectView(discord.ui.View):
    """Team selection dropdown for IPL mode."""
    def __init__(self, ctx, channel, data, role):
        super().__init__(timeout=180)
        self.ctx = ctx; self.channel = channel; self.data = data; self.role = role
        opts = [
            discord.SelectOption(
                label=f"{info['emoji']} {short} — {info['full']}",
                value=short,
                description=", ".join(info["players"][:4]) + "..."
            )
            for short, info in IPL_SQUADS.items()
        ]
        sel = discord.ui.Select(
            placeholder=f"🏟️ Choose {'your' if role=='challenger' else 'opponent'} IPL team…",
            options=opts
        )
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        d = self.data
        expected_id = d["challenger_id"] if self.role == "challenger" else (d.get("opponent_id") or d["challenger_id"])
        if interaction.user.id != expected_id:
            return await interaction.response.send_message("❌ Not your turn to pick!", ephemeral=True)

        team_key = interaction.data["values"][0]
        info = IPL_SQUADS[team_key]

        if self.role == "challenger":
            d["ch_team"] = team_key
            d["ch_team_info"] = info
            # If there's an opponent, they now pick their team
            if d.get("opponent_id"):
                opp = d.get("opponent_member")
                opp_mention = opp.mention if opp else f"<@{d['opponent_id']}>"
                em = discord.Embed(
                    title=f"⚔️ Challenge Accepted — {opp_mention}, pick your team!",
                    description=(
                        f"**{d['challenger_member'].mention}** chose **{info['emoji']} {info['full']}**\n\n"
                        f"{opp_mention} — select your IPL team!"
                    ),
                    color=info["color"]
                )
                await interaction.response.edit_message(embed=em,
                    view=IPLTeamSelectView(self.ctx, self.channel, d, role="opponent"))
            else:
                # Solo — pick opponent team too
                em = discord.Embed(
                    title="🏟️ Now pick the Opponent Team",
                    description=f"You chose **{info['emoji']} {info['full']}**\nNow pick the opponent team!",
                    color=info["color"]
                )
                await interaction.response.edit_message(embed=em,
                    view=IPLTeamSelectView(self.ctx, self.channel, d, role="opponent"))
        else:
            # Opponent picked their team
            ch_key  = d["ch_team"]
            ch_info = d["ch_team_info"]
            if team_key == ch_key:
                return await interaction.response.send_message("❌ Can't pick the same team!", ephemeral=True)
            d["op_team"] = team_key
            d["op_team_info"] = info

            em = discord.Embed(
                title="🏏 IPL Match Setup — Xi Selection",
                description=(
                    f"**{ch_info['emoji']} {ch_info['full']}** vs **{info['emoji']} {info['full']}**\n\n"
                    "Choose **Auto XI** (bot picks best 11) or **Manual XI** (you pick your lineup) for each team."
                ),
                color=0xf7c200
            )
            em.add_field(name=f"{ch_info['emoji']} {ch_key}", value="\n".join(ch_info["players"]), inline=True)
            em.add_field(name=f"{info['emoji']} {team_key}", value="\n".join(info["players"]), inline=True)
            await interaction.response.edit_message(embed=em, view=IPLXISelectView(self.ctx, self.channel, d))


class IPLXISelectView(discord.ui.View):
    """Auto or Manual XI selection for both teams."""
    def __init__(self, ctx, channel, data):
        super().__init__(timeout=180)
        self.ctx = ctx; self.channel = channel; self.data = data
        self.data.setdefault("ch_xi_mode", None)
        self.data.setdefault("op_xi_mode", None)
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        d = self.data
        ch_info = d["ch_team_info"]; op_info = d["op_team_info"]

        # Challenger XI mode
        if d["ch_xi_mode"] is None:
            opts = [
                discord.SelectOption(label=f"🤖 Auto XI — {d['ch_team']}", value="auto_ch",
                    description="Bot selects best 11 automatically"),
                discord.SelectOption(label=f"✍️ Manual XI — {d['ch_team']}", value="manual_ch",
                    description="You select your own 11 players"),
            ]
            sel = discord.ui.Select(placeholder=f"Select XI mode for {d['ch_team']}…", options=opts)
            sel.callback = self._on_ch
            self.add_item(sel)

        # Opponent XI mode
        if d["op_xi_mode"] is None and d["ch_xi_mode"] is not None:
            opts = [
                discord.SelectOption(label=f"🤖 Auto XI — {d['op_team']}", value="auto_op",
                    description="Bot selects best 11 automatically"),
                discord.SelectOption(label=f"✍️ Manual XI — {d['op_team']}", value="manual_op",
                    description="Opponent selects their own 11 players"),
            ]
            sel = discord.ui.Select(placeholder=f"Select XI mode for {d['op_team']}…", options=opts)
            sel.callback = self._on_op
            self.add_item(sel)

    async def _on_ch(self, interaction):
        if interaction.user.id != self.data["challenger_id"]:
            return await interaction.response.send_message("❌ Only the challenger can set their XI mode.", ephemeral=True)
        val = interaction.data["values"][0]
        self.data["ch_xi_mode"] = "auto" if val == "auto_ch" else "manual"
        self._rebuild()
        await interaction.response.edit_message(
            content=f"✅ **{self.data['ch_team']}** XI mode: **{'Auto' if self.data['ch_xi_mode']=='auto' else 'Manual'}**. Now set opponent XI mode.",
            view=self)

    async def _on_op(self, interaction):
        expected = self.data.get("opponent_id") or self.data["challenger_id"]
        if interaction.user.id != expected:
            return await interaction.response.send_message("❌ Not your selection.", ephemeral=True)
        val = interaction.data["values"][0]
        self.data["op_xi_mode"] = "auto" if val == "auto_op" else "manual"
        # Both modes set — proceed
        await interaction.response.edit_message(content="⚙️ Setting up XI…", view=None)
        await self._proceed(interaction)

    async def _proceed(self, interaction):
        d = self.data
        ch_squad = [p for p in d["ch_team_info"]["players"]]
        op_squad = [p for p in d["op_team_info"]["players"]]

        if d["ch_xi_mode"] == "manual":
            await self.channel.send(
                embed=discord.Embed(
                    title=f"✍️ {d['ch_team']} — Select Your XI",
                    description="Pick exactly **11 players** for your team:",
                    color=d["ch_team_info"]["color"]
                ),
                view=IPLManualXIView(self.ctx, self.channel, d, "ch", ch_squad, op_squad)
            )
        else:
            # Auto XI for challenger
            d["ch_xi"] = ch_squad  # Already exactly 11
            if d["op_xi_mode"] == "manual":
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"✍️ {d['op_team']} — Select Your XI",
                        description="Pick exactly **11 players** for your team:",
                        color=d["op_team_info"]["color"]
                    ),
                    view=IPLManualXIView(self.ctx, self.channel, d, "op", op_squad, ch_squad)
                )
            else:
                d["op_xi"] = op_squad
                await _start_ipl_match(self.ctx, self.channel, d)


class IPLManualXIView(discord.ui.View):
    """Manual player selection for IPL XI."""
    def __init__(self, ctx, channel, data, team_role, squad, other_squad):
        super().__init__(timeout=300)
        self.ctx=ctx; self.channel=channel; self.data=data
        self.team_role=team_role; self.squad=squad; self.other_squad=other_squad
        self.selected = []
        self._build()

    def _build(self):
        self.clear_items()
        remaining = [p for p in self.squad if p not in self.selected]
        opts = [discord.SelectOption(label=p, value=p) for p in remaining[:25]]
        if not opts:
            opts = [discord.SelectOption(label="All selected", value="__done__")]
        sel = discord.ui.Select(
            placeholder=f"Pick players ({len(self.selected)}/11 selected)…",
            options=opts,
            min_values=1,
            max_values=min(len(opts), 11 - len(self.selected))
        )
        sel.callback = self._cb
        self.add_item(sel)

        if len(self.selected) >= 11:
            btn = discord.ui.Button(label="✅ Confirm XI", style=discord.ButtonStyle.success)
            btn.callback = self._confirm
            self.add_item(btn)

    async def _cb(self, interaction):
        expected = self.data["challenger_id"] if self.team_role == "ch" else (self.data.get("opponent_id") or self.data["challenger_id"])
        if interaction.user.id != expected:
            return await interaction.response.send_message("❌ Not your XI to pick!", ephemeral=True)
        vals = interaction.data["values"]
        self.selected.extend([v for v in vals if v not in self.selected])
        self.selected = self.selected[:11]
        self._build()
        em = discord.Embed(
            title=f"✍️ {self.data[self.team_role+'_team']} XI ({len(self.selected)}/11)",
            description="\n".join(f"• {p}" for p in self.selected) or "None yet",
            color=self.data[self.team_role+"_team_info"]["color"]
        )
        if len(self.selected) >= 11:
            em.set_footer(text="Press ✅ Confirm XI to finalize!")
        await interaction.response.edit_message(embed=em, view=self)

    async def _confirm(self, interaction):
        expected = self.data["challenger_id"] if self.team_role == "ch" else (self.data.get("opponent_id") or self.data["challenger_id"])
        if interaction.user.id != expected:
            return await interaction.response.send_message("❌ Not your XI!", ephemeral=True)
        if len(self.selected) < 11:
            return await interaction.response.send_message(f"❌ Need exactly 11! You have {len(self.selected)}.", ephemeral=True)
        self.data[self.team_role+"_xi"] = self.selected
        await interaction.response.edit_message(
            content=f"✅ **{self.data[self.team_role+'_team']} XI confirmed!**",
            embed=None, view=None)

        # Check if other team needs XI
        other = "op" if self.team_role == "ch" else "ch"
        if self.data.get(other+"_xi_mode") == "manual" and not self.data.get(other+"_xi"):
            other_info = self.data[other+"_team_info"]
            other_squad = other_info["players"]
            other_expected = self.data.get("opponent_id" if other=="op" else "challenger_id") or self.data["challenger_id"]
            opp_mem = self.data.get("opponent_member")
            mention = opp_mem.mention if opp_mem else f"<@{other_expected}>"
            await self.channel.send(
                embed=discord.Embed(
                    title=f"✍️ {self.data[other+'_team']} — {mention}, select your XI!",
                    color=other_info["color"]
                ),
                view=IPLManualXIView(self.ctx, self.channel, self.data, other, other_squad, self.selected)
            )
        elif not self.data.get(other+"_xi"):
            # Auto XI for the other team
            self.data[other+"_xi"] = self.data[other+"_team_info"]["players"]
            await _start_ipl_match(self.ctx, self.channel, self.data)
        else:
            await _start_ipl_match(self.ctx, self.channel, self.data)


async def _start_ipl_match(ctx, channel, data):
    """Kick off the IPL match after both XIs confirmed — goes to home/pitch/toss flow."""
    ch_key  = data["ch_team"];  ch_info = data["ch_team_info"]
    op_key  = data["op_team"];  op_info = data["op_team_info"]
    ch_xi   = data["ch_xi"];    op_xi   = data["op_xi"]

    ch_list, unk1 = build_player_list(ch_info["full"], ch_xi)
    op_list, unk2 = build_player_list(op_info["full"], op_xi)

    data["t1n"]      = f"{ch_info['emoji']} {ch_key}"
    data["t1_list"]  = ch_list
    data["t1_uid"]   = data["challenger_id"]
    data["t2n"]      = f"{op_info['emoji']} {op_key}"
    data["t2_list"]  = op_list
    data["t2_uid"]   = data.get("opponent_id")
    data["stadium"]  = f"{ch_info['full']} Home Ground"
    data["extra_note"] = ("Generic stats: " + ", ".join(unk1+unk2)) if (unk1 or unk2) else None
    data["ipl_mode"] = True

    em = discord.Embed(
        title=f"🏟️ {ch_info['emoji']} {ch_key} vs {op_info['emoji']} {op_key}",
        description=(
            f"Both XIs confirmed! Now set the **home team** and **pitch**.\n\n"
            f"**{ch_info['emoji']} {ch_key}:** {', '.join(ch_xi[:5])}... +6\n"
            f"**{op_info['emoji']} {op_key}:** {', '.join(op_xi[:5])}... +6"
        ),
        color=0xf7c200
    )
    await channel.send(embed=em, view=IMatchHomeView(ctx, channel, data))



@bot.command(name='stats')
async def player_stats(ctx, *, player_name: str):
    """View a player card's career match stats. Usage: +stats Virat Kohli"""
    name, pdata = find_player(player_name)
    if not name:
        return await ctx.send(f"❌ Player **{player_name}** not found. Use `+players` to browse.")

    stats = load_json(STATS_FILE) if os.path.exists(STATS_FILE) else {}
    s     = stats.get(name)
    rarity = pdata['rarity']
    em = discord.Embed(title=f"📊 {name} — Career Stats", color=RARITY_COLORS[rarity])
    em.add_field(name="⭐ Rarity", value=f"{RARITY_EMOJI[rarity]} {rarity}", inline=True)
    em.add_field(name=f"{ROLE_META[pdata['role']]['emoji']} Role",
                 value=ROLE_META[pdata['role']]['label'], inline=True)
    em.add_field(name="🏏 Team", value=pdata['team'], inline=True)

    if s and s.get('matches', 0) > 0:
        avg = round(s['runs'] / s['matches'], 1)
        em.add_field(name="🎮 Matches",    value=str(s['matches']),          inline=True)
        em.add_field(name="🏃 Total Runs", value=f"{s['runs']} (avg {avg})", inline=True)
        em.add_field(name="🎯 Wickets",    value=str(s.get('wickets', 0)),   inline=True)
        if s.get('balls_faced', 0):
            sr = round(s['runs'] / s['balls_faced'] * 100, 1)
            em.add_field(name="⚡ Strike Rate", value=str(sr), inline=True)
        if s.get('balls_bowled', 0):
            econ = round(s['runs_conceded'] / s['balls_bowled'] * 6, 2)
            em.add_field(name="💨 Economy", value=str(econ), inline=True)
    else:
        em.description = (
            f"**{name}** hasn't played any NEXUS matches yet.\n"
            f"Use `+simulate` to start a custom simulated match!"
        )

    img_path = PLAYER_IMAGES.get(name)
    if img_path and os.path.exists(img_path):
        fn = os.path.basename(img_path)
        em.set_image(url=f"attachment://{fn}")
        await ctx.send(embed=em, file=discord.File(img_path, filename=fn))
    else:
        await ctx.send(embed=em)


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────
@bot.command(name='fixtures')
async def fixtures(ctx):
    data          = load_json(FIXTURES_FILE)
    fixtures_list = data.get("fixtures", [])
    if not fixtures_list:
        return await ctx.send("📅 No fixtures scheduled yet! Admins can use `+addfixture @RCB @MI 8.30 pm ist`.")
    embed = discord.Embed(title="📅 Upcoming Fixtures", color=0x00aaff,
                          description=f"**{len(fixtures_list)}** fixture(s) scheduled")
    for i, fx in enumerate(fixtures_list, 1):
        team1_mention = fx.get("team1_mention", "Unknown")
        team2_mention = fx.get("team2_mention", "Unknown")
        time_str = fx.get("time_str", "Unknown")
        embed.add_field(
            name=f"🏟️ Match #{i}",
            value=f"{team1_mention} vs {team2_mention}\n⏰ {time_str}\n📅 Channel: <#{fx['channel_id']}>",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name='addfixture')
async def add_fixture(ctx):
    """(Admin) Add a fixture. Usage: +addfixture @RCB @MI 8.30 pm ist"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    
    parts = ctx.message.content.split()
    if len(parts) < 4:
        return await ctx.send("❌ Usage: +addfixture @team1 @team2 time (e.g., +addfixture @RCB @MI 8.30 pm ist)")
    
    role_mentions = ctx.message.role_mentions
    if len(role_mentions) != 2:
        return await ctx.send("❌ You must mention exactly two team roles.")
    
    team1, team2 = role_mentions
    time_str = ' '.join(parts[3:])
    
    scheduled_utc = parse_ist_time(time_str)
    if not scheduled_utc:
        return await ctx.send("❌ Invalid time format. Use like '8.30 pm ist'")
    
    # Check if already a fixture in this channel
    data = load_json(FIXTURES_FILE)
    for f in data["fixtures"]:
        if f["channel_id"] == ctx.channel.id:
            return await ctx.send("❌ There's already a fixture scheduled in this channel.")
    
    # Ping teams
    await ctx.send(f"🏟️ {team1.mention} vs {team2.mention} fixture scheduled for {time_str}")
    
    # Lock channel
    channel = ctx.channel
    everyone = ctx.guild.default_role
    await channel.set_permissions(everyone, send_messages=False)
    await channel.set_permissions(team1, send_messages=True)
    await channel.set_permissions(team2, send_messages=True)
    
    # Save fixture
    fixture = {
        "team1_id": team1.id,
        "team2_id": team2.id,
        "team1_mention": team1.mention,
        "team2_mention": team2.mention,
        "time_str": time_str,
        "channel_id": channel.id,
        "scheduled_utc": scheduled_utc.isoformat(),
        "locked": True
    }
    data["fixtures"].append(fixture)
    save_json(data, FIXTURES_FILE)
    
    # Schedule reopen
    async def reopen():
        delay = (scheduled_utc - datetime.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await channel.set_permissions(everyone, send_messages=None)
        await channel.send(f"🏟️ {team1.mention} vs {team2.mention} - Match time! {time_str}")
        # Remove from json
        data = load_json(FIXTURES_FILE)
        data["fixtures"] = [f for f in data["fixtures"] if f["channel_id"] != channel.id]
        save_json(data, FIXTURES_FILE)
        if channel.id in scheduled_tasks:
            del scheduled_tasks[channel.id]
    
    task = bot.loop.create_task(reopen())
    scheduled_tasks[channel.id] = task
    
    await ctx.send(f"✅ Fixture added and channel locked until {time_str}.")

@bot.command(name='removefixture')
async def remove_fixture(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    
    data = load_json(FIXTURES_FILE)
    fixtures = data.get("fixtures", [])
    fixture = next((f for f in fixtures if f["channel_id"] == ctx.channel.id), None)
    if not fixture:
        return await ctx.send("❌ No fixture found in this channel.")
    
    # Cancel task if exists
    if ctx.channel.id in scheduled_tasks:
        scheduled_tasks[ctx.channel.id].cancel()
        del scheduled_tasks[ctx.channel.id]
    
    # Unlock channel
    channel = ctx.channel
    everyone = ctx.guild.default_role
    await channel.set_permissions(everyone, send_messages=None)
    
    # Remove from json
    data["fixtures"].remove(fixture)
    save_json(data, FIXTURES_FILE)
    
    await ctx.send(f"✅ Removed fixture: {fixture['team1_mention']} vs {fixture['team2_mention']} and unlocked the channel.")

# ─────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────
@bot.command(name='nexushelp', aliases=['help2','commands','cmds'])
async def nexus_help(ctx):
    embed = discord.Embed(title="📖 NEXUS Bot Commands  |  prefix: `+`", color=0x00aaff)
    embed.add_field(name="💰 Economy", value=(
        "`+balance [@user]` — Check balance\n"
        "`+addcoins @user <amt>` — (Admin) Add coins\n"
        "`+addtickets @user <amt>` — (Admin) Add tickets\n"
        "`+addbalance @user <coins> <tickets>` — (Admin) Add both"
    ), inline=False)
    embed.add_field(name="🎁 Packs", value=(
        "`+bundle` — Choose & buy IPL or T20 WC pack\n"
        "`+open` — Open your purchased pack\n"
        "`+mypacks` — See your pending packs\n"
        "`+activebundles` — Recent opens"
    ), inline=False)
    embed.add_field(name="🛒 Players", value=(
        "`+shop` — Daily deals with discounts\n"
        "`+buy <name>` — Buy any player by name\n"
        "`+sell <name>` — Sell a player (60% value)\n"
        "`+players [rarity]` — Browse all 100+ players\n"
        "`+addplayer @user <name>` — (Admin) Add player to squad\n"
        "`+removeplayer @user <name>` — (Admin) Remove player from squad"
    ), inline=False)
    embed.add_field(name="🎭 Role Showrooms", value=(
        "`+battershower` 🏏 · `+bowlershower` 🎯\n"
        "`+wkshower` 🧤 · `+alrshower` ⚡"
    ), inline=False)
    embed.add_field(name="📋 Squad", value=(
        "`+squad [@user]` — View player collection with role breakdown\n"
        "`+autobuild` — Auto-build a best XI from your squad"
    ), inline=False)
    embed.add_field(name="🏏 Matches & Stats", value=(
        "`+simulate` — Simulate a custom match from two teams\n"
        "`+stats <player name>` — View a player card's career stats"
    ), inline=False)
    embed.add_field(name="📅 Fixtures", value=(
        "`+fixtures` — View upcoming fixtures\n"
        "`+addfixture @team1 @team2 time` — (Admin) Add fixture and lock channel\n"
        "`+removefixture` — (Admin) Remove fixture and unlock channel"
    ), inline=False)
    await ctx.send(embed=embed)

# ─────────────────────────────────────────────
# TOURNAMENT SYSTEM
# ─────────────────────────────────────────────
TOURNEY_FILE = 'tournaments.json'

def load_tourneys():
    if not os.path.exists(TOURNEY_FILE):
        save_json({}, TOURNEY_FILE)
    return load_json(TOURNEY_FILE)

def save_tourney(data):
    save_json(data, TOURNEY_FILE)

def get_tourney(name):
    data = load_tourneys()
    return data.get(name.lower())

def set_tourney(name, tourney):
    data = load_tourneys()
    data[name.lower()] = tourney
    save_tourney(data)

def delete_tourney(name):
    data = load_tourneys()
    if name.lower() in data:
        del data[name.lower()]
        save_tourney(data)

def parse_score_str(score_str):
    m = re.search(r'(\d+)/(\d+)', score_str or '')
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0

def run_tourney_match(team1_name, team1_xi, team2_name, team2_xi):
    """Simulate a match between two teams, returns match result dict."""
    t1_list, _ = build_player_list(team1_name, team1_xi)
    t2_list, _ = build_player_list(team2_name, team2_xi)
    t1_list = t1_list[:11]
    t2_list = t2_list[:11]

    if random.random() < 0.5:
        bat_name, bat_list = team1_name, t1_list
        bowl_name, bowl_list = team2_name, t2_list
    else:
        bat_name, bat_list = team2_name, t2_list
        bowl_name, bowl_list = team1_name, t1_list

    match = MatchState(
        channel_id=0,
        batting_uid='sim', bowling_uid='sim',
        batting_name=bat_name, bowling_name=bowl_name,
        batting_squad=bat_list, bowling_squad=bowl_list
    )
    simulate_full_match(match)

    s1_str = match.innings_scores.get(1, '0/0')
    s2_str = match.innings_scores.get(2, '0/0')
    s1_runs, s1_wkts = parse_score_str(s1_str)
    s2_runs, s2_wkts = parse_score_str(s2_str)

    if s2_runs > s1_runs:
        winner = bowl_name
        margin = f"by {10 - s2_wkts} wkts"
    elif s1_runs > s2_runs:
        winner = bat_name
        margin = f"by {s1_runs - s2_runs} runs"
    else:
        winner = bat_name  # tie goes to team1
        margin = "tie (D/L)"

    # Collect batting stats
    bat_stats = {}
    for name, s in match.match_bat_stats.items():
        bat_stats[name] = {'runs': s['runs'], 'balls': s['balls']}

    # Collect bowling stats
    bowl_stats = {}
    for name, s in match.match_bowl_stats.items():
        bowl_stats[name] = {'wickets': s['wickets'], 'runs': s['runs'], 'balls': s['balls']}

    return {
        'team1': team1_name, 'team2': team2_name,
        'bat_first': bat_name,
        'score1': f"{s1_runs}/{s1_wkts}",
        'score2': f"{s2_runs}/{s2_wkts}",
        'winner': winner,
        'margin': margin,
        'bat_stats': bat_stats,
        'bowl_stats': bowl_stats,
    }

def generate_round_robin(teams):
    """Generate all round-robin fixtures (each team plays every other team once)."""
    fixtures = []
    for i in range(len(teams)):
        for j in range(i+1, len(teams)):
            fixtures.append((teams[i], teams[j]))
    return fixtures

def generate_tourney_scorecard_image(result):
    """Generate scorecard image for a tournament match."""
    if not PILLOW_AVAILABLE:
        return None

    t1 = result['team1']; t2 = result['team2']
    s1r, s1w = parse_score_str(result['score1'])
    s2r, s2w = parse_score_str(result['score2'])

    bat_first = result['bat_first']
    bowl_first = t2 if bat_first == t1 else t1

    t1_players_batting  = [k for k in result['bat_stats'] if k in [p['name'] for p in build_player_list(bat_first, [])[0]]] if False else list(result['bat_stats'].keys())

    # Split stats by who played for which team — use bat_first/bowl_first
    # Since we can't easily split by team in run_tourney_match, show top scorers/bowlers globally
    all_bat = sorted(result['bat_stats'].items(), key=lambda x: -x[1]['runs'])
    all_bowl = sorted(result['bowl_stats'].items(), key=lambda x: (-x[1]['wickets'], x[1]['runs']))

    t1_bat  = [(n, s['runs'], s['balls'], False) for n, s in all_bat[:4]]
    t1_bowl = [(n, s['wickets'], s['runs'], f"{s['balls']//6}.{s['balls']%6}") for n, s in all_bowl[:4]]
    t2_bat  = [(n, s['runs'], s['balls'], False) for n, s in all_bat[4:8]]
    t2_bowl = [(n, s['wickets'], s['runs'], f"{s['balls']//6}.{s['balls']%6}") for n, s in all_bowl[4:8]]

    result_text = f"{result['winner']} won {result['margin']}"
    return generate_scorecard_image(
        bat_first, s1r, s1w, "20.0", t1_bat, t1_bowl,
        bowl_first, s2r, s2w, "20.0", t2_bat, t2_bowl,
        result_text, pom_name=None
    )

@bot.command(name='tournament')
async def create_tournament(ctx, *, name: str):
    """Create a new tournament. Usage: +tournament IPL 2026"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can create tournaments!")
    existing = get_tourney(name)
    if existing:
        return await ctx.send(f"❌ Tournament **{name}** already exists! Use `+deltourney {name}` to delete it first.")
    tourney = {
        'name': name,
        'guild_id': ctx.guild.id,
        'status': 'setup',   # setup → group → playoffs → done
        'teams': [],
        'xis': {},           # team_name -> [player names]
        'fixtures': [],      # list of {team1, team2, played, result}
        'points_table': {},  # team -> {played, won, lost, pts, nrr}
        'results': [],       # completed match results
        'orange_cap': {},    # player -> total runs
        'purple_cap': {},    # player -> total wickets
        'created_by': str(ctx.author.id),
    }
    set_tourney(name, tourney)
    em = discord.Embed(
        title=f"🏆 Tournament Created: {name}",
        description="Set up your tournament step by step!",
        color=0xffd700
    )
    em.add_field(name="Next Steps", value=(
        f"`+addteams {name} RCB, CSK, MI, KKR` — Add teams\n"
        f"`+addxi {name} RCB = Virat Kohli, Phil Salt...` — Add XI per team\n"
        f"`+startourney {name}` — Start the tournament!\n"
        f"`+tourney {name}` — View tournament status"
    ), inline=False)
    await ctx.send(embed=em)

@bot.command(name='addteams')
async def add_teams(ctx, name: str, *, teams_str: str):
    """Add teams to a tournament. Usage: +addteams IPL2026 RCB, CSK, MI, KKR"""
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    if tourney['status'] != 'setup':
        return await ctx.send(f"❌ Tournament already started!")
    teams = [t.strip() for t in teams_str.replace(',', ' ').split() if t.strip()]
    if len(teams) < 2:
        return await ctx.send("❌ Need at least 2 teams!")
    for t in teams:
        if t not in tourney['teams']:
            tourney['teams'].append(t)
            tourney['points_table'][t] = {'played':0,'won':0,'lost':0,'pts':0,'nrr':0.0,'runs_for':0,'balls_for':0,'runs_against':0,'balls_against':0}
    set_tourney(name, tourney)
    em = discord.Embed(title=f"✅ Teams Added to {name}", color=0x00ff00)
    em.add_field(name=f"Teams ({len(tourney['teams'])})", value="\n".join(f"• {t}" for t in tourney['teams']), inline=False)
    em.set_footer(text=f"Now add XI for each team using +addxi {name} TEAM = player1, player2...")
    await ctx.send(embed=em)

@bot.command(name='addxi')
async def add_xi(ctx, name: str, *, xi_str: str):
    """Add XI for a team. Usage: +addxi IPL2026 RCB = Virat Kohli, Phil Salt, ..."""
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    if '=' not in xi_str:
        return await ctx.send("❌ Format: `+addxi TourneyName TEAM = player1, player2, ...`")
    team_part, players_part = xi_str.split('=', 1)
    team_name = team_part.strip()
    # Find matching team (case-insensitive)
    matched = next((t for t in tourney['teams'] if t.lower() == team_name.lower()), None)
    if not matched:
        return await ctx.send(f"❌ Team **{team_name}** not in this tournament! Teams: {', '.join(tourney['teams'])}")
    players = [p.strip() for p in players_part.split(',') if p.strip()]
    if len(players) < 11:
        return await ctx.send(f"❌ Need exactly 11 players, you gave {len(players)}!")
    players = players[:11]
    tourney['xis'][matched] = players
    set_tourney(name, tourney)
    missing = [t for t in tourney['teams'] if t not in tourney['xis']]
    em = discord.Embed(title=f"✅ XI Added: {matched}", color=0x00aaff)
    em.add_field(name="Players", value="\n".join(f"{i+1}. {p}" for i,p in enumerate(players)), inline=False)
    if missing:
        em.set_footer(text=f"Still need XI for: {', '.join(missing)}")
    else:
        em.set_footer(text=f"All teams have XI! Use +startourney {name} to begin!")
    await ctx.send(embed=em)

@bot.command(name='startourney')
async def start_tourney(ctx, *, name: str):
    """Start the tournament simulation. Usage: +startourney IPL 2026"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can start tournaments!")
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    if tourney['status'] != 'setup':
        return await ctx.send(f"❌ Tournament already started!")
    missing_xi = [t for t in tourney['teams'] if t not in tourney['xis']]
    if missing_xi:
        return await ctx.send(f"❌ Missing XI for: **{', '.join(missing_xi)}**\nUse `+addxi {name} TEAM = players...`")
    if len(tourney['teams']) < 2:
        return await ctx.send("❌ Need at least 2 teams!")

    fixtures = generate_round_robin(tourney['teams'])
    tourney['fixtures'] = [{'team1': f[0], 'team2': f[1], 'played': False, 'result': None} for f in fixtures]
    tourney['status'] = 'group'
    set_tourney(name, tourney)

    total = len(fixtures)
    em = discord.Embed(
        title=f"🏆 {name} — Group Stage Begins!",
        description=f"**{len(tourney['teams'])} teams · {total} matches** to be played!",
        color=0xffd700
    )
    em.add_field(name="Teams", value=" · ".join(tourney['teams']), inline=False)
    em.set_footer(text=f"Use +simtourney {name} to simulate all matches!")
    await ctx.send(embed=em)

@bot.command(name='simtourney')
async def sim_tourney(ctx, *, name: str):
    """Simulate all remaining tournament matches. Usage: +simtourney IPL 2026"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can simulate tournaments!")
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    if tourney['status'] == 'setup':
        return await ctx.send(f"❌ Start the tournament first with `+startourney {name}`!")

    pending = [f for f in tourney['fixtures'] if not f['played']]
    if not pending:
        return await ctx.send(f"✅ All group stage matches already simulated! Use `+tourney {name}` to view standings.")

    await ctx.send(f"⚙️ Simulating **{len(pending)}** matches for **{name}**... This may take a moment!")

    match_summaries = []
    for fixture in pending:
        t1, t2 = fixture['team1'], fixture['team2']
        xi1 = tourney['xis'].get(t1, [])
        xi2 = tourney['xis'].get(t2, [])

        result = run_tourney_match(t1, xi1, t2, xi2)
        fixture['played'] = True
        fixture['result'] = result

        # Update points table
        winner = result['winner']
        loser = t2 if winner == t1 else t1
        s1r, _ = parse_score_str(result['score1'])
        s2r, _ = parse_score_str(result['score2'])

        for team in [t1, t2]:
            pt = tourney['points_table'][team]
            pt['played'] += 1
            if team == winner:
                pt['won'] += 1; pt['pts'] += 2
            else:
                pt['lost'] += 1

        # Update orange/purple cap
        for pname, s in result['bat_stats'].items():
            tourney['orange_cap'][pname] = tourney['orange_cap'].get(pname, 0) + s['runs']
        for pname, s in result['bowl_stats'].items():
            tourney['purple_cap'][pname] = tourney['purple_cap'].get(pname, 0) + s['wickets']

        tourney['results'].append(result)
        match_summaries.append(f"• **{t1}** vs **{t2}** → 🏆 **{winner}** won {result['margin']} | {result['score1']} vs {result['score2']}")

    set_tourney(name, tourney)

    # Send results in chunks
    chunk = []
    for line in match_summaries:
        chunk.append(line)
        if len(chunk) >= 10:
            em = discord.Embed(title=f"🏏 {name} — Match Results", color=0x00aaff)
            em.description = "\n".join(chunk)
            await ctx.send(embed=em)
            chunk = []
    if chunk:
        em = discord.Embed(title=f"🏏 {name} — Match Results", color=0x00aaff)
        em.description = "\n".join(chunk)
        await ctx.send(embed=em)

    # Check if group stage done
    all_done = all(f['played'] for f in tourney['fixtures'])
    if all_done and tourney['status'] == 'group':
        tourney['status'] = 'playoffs'
        set_tourney(name, tourney)
        await ctx.send(f"✅ Group stage complete! Use `+tourney {name}` for standings and `+playoffs {name}` to run playoffs!")

@bot.command(name='playoffs')
async def run_playoffs(ctx, *, name: str):
    """Run IPL-style playoffs (Top 4). Usage: +playoffs IPL 2026"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can run playoffs!")
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    if tourney['status'] not in ('playoffs', 'group'):
        return await ctx.send(f"❌ Playoffs not available yet!")

    # Sort standings
    table = tourney['points_table']
    standings = sorted(table.items(), key=lambda x: (-x[1]['pts'], -x[1]['won']))
    if len(standings) < 4:
        return await ctx.send("❌ Need at least 4 teams for playoffs!")

    t1_name = standings[0][0]
    t2_name = standings[1][0]
    t3_name = standings[2][0]
    t4_name = standings[3][0]

    await ctx.send(embed=discord.Embed(
        title=f"🏆 {name} — PLAYOFFS",
        description=(
            f"**Qualifier 1:** 🥇{t1_name} vs 🥈{t2_name}\n"
            f"**Eliminator:** 🥉{t3_name} vs 4️⃣{t4_name}\n"
            f"*(Winners of Q1 go to Final, loser gets another chance)*"
        ),
        color=0xffd700
    ))

    xis = tourney['xis']

    # Qualifier 1: 1st vs 2nd
    q1 = run_tourney_match(t1_name, xis[t1_name], t2_name, xis[t2_name])
    q1_winner = q1['winner']
    q1_loser  = t2_name if q1_winner == t1_name else t1_name

    # Eliminator: 3rd vs 4th
    elim = run_tourney_match(t3_name, xis[t3_name], t4_name, xis[t4_name])
    elim_winner = elim['winner']

    # Qualifier 2: Q1 loser vs Eliminator winner
    q2 = run_tourney_match(q1_loser, xis[q1_loser], elim_winner, xis[elim_winner])
    q2_winner = q2['winner']

    # Final: Q1 winner vs Q2 winner
    final = run_tourney_match(q1_winner, xis[q1_winner], q2_winner, xis[q2_winner])
    champion = final['winner']

    # Update cap stats
    for res in [q1, elim, q2, final]:
        for pname, s in res['bat_stats'].items():
            tourney['orange_cap'][pname] = tourney['orange_cap'].get(pname, 0) + s['runs']
        for pname, s in res['bowl_stats'].items():
            tourney['purple_cap'][pname] = tourney['purple_cap'].get(pname, 0) + s['wickets']

    tourney['status'] = 'done'
    tourney['champion'] = champion
    set_tourney(name, tourney)

    # Show results
    playoff_lines = [
        f"⚡ **Qualifier 1:** {t1_name} vs {t2_name} → **{q1_winner}** won {q1['margin']}",
        f"⚡ **Eliminator:** {t3_name} vs {t4_name} → **{elim_winner}** won {elim['margin']}",
        f"⚡ **Qualifier 2:** {q1_loser} vs {elim_winner} → **{q2_winner}** won {q2['margin']}",
        f"🏆 **FINAL:** {q1_winner} vs {q2_winner} → **{champion}** won {final['margin']}",
    ]
    em = discord.Embed(title=f"🏆 {name} — PLAYOFF RESULTS", color=0xffd700)
    em.description = "\n\n".join(playoff_lines)
    await ctx.send(embed=em)

    # Champion announcement
    champ_em = discord.Embed(
        title=f"🎉 {name} CHAMPIONS!",
        description=f"# 🏆 {champion} 🏆\nCongratulations to the champions!",
        color=0xffd700
    )
    # Orange cap
    orange = sorted(tourney['orange_cap'].items(), key=lambda x: -x[1])
    if orange:
        champ_em.add_field(name="🟠 Orange Cap", value=f"**{orange[0][0]}** — {orange[0][1]} runs", inline=True)
    # Purple cap
    purple = sorted(tourney['purple_cap'].items(), key=lambda x: -x[1])
    if purple:
        champ_em.add_field(name="🟣 Purple Cap", value=f"**{purple[0][0]}** — {purple[0][1]} wickets", inline=True)
    await ctx.send(embed=champ_em)

    # Full stats embed
    await ctx.invoke(bot.get_command('tourney'), name=name)

@bot.command(name='tourney')
async def view_tourney(ctx, *, name: str):
    """View tournament standings and stats. Usage: +tourney IPL 2026"""
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")

    status_map = {'setup':'⚙️ Setup','group':'🏏 Group Stage','playoffs':'⚡ Playoffs','done':'✅ Complete'}
    em = discord.Embed(
        title=f"🏆 {tourney['name']}",
        description=f"Status: {status_map.get(tourney['status'], tourney['status'])}",
        color=0xffd700
    )

    # Points table
    table = tourney['points_table']
    standings = sorted(table.items(), key=lambda x: (-x[1]['pts'], -x[1]['won']))
    medals = ['🥇','🥈','🥉','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
    table_lines = ["```", f"{'#':<3} {'Team':<22} {'P':<4} {'W':<4} {'L':<4} {'PTS':<5}", "-"*43]
    for i, (team, s) in enumerate(standings):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        table_lines.append(f"{i+1:<3} {team:<22} {s['played']:<4} {s['won']:<4} {s['lost']:<4} {s['pts']:<5}")
    table_lines.append("```")
    em.add_field(name="📊 Points Table", value="\n".join(table_lines), inline=False)

    # Orange cap top 5
    orange = sorted(tourney['orange_cap'].items(), key=lambda x: -x[1])[:5]
    if orange:
        em.add_field(name="🟠 Orange Cap", value="\n".join(f"**{n}** — {r} runs" for n,r in orange), inline=True)

    # Purple cap top 5
    purple = sorted(tourney['purple_cap'].items(), key=lambda x: -x[1])[:5]
    if purple:
        em.add_field(name="🟣 Purple Cap", value="\n".join(f"**{n}** — {w} wkts" for n,w in purple), inline=True)

    if tourney.get('champion'):
        em.add_field(name="🏆 Champion", value=f"**{tourney['champion']}**", inline=False)

    pending = len([f for f in tourney.get('fixtures',[]) if not f['played']])
    played  = len([f for f in tourney.get('fixtures',[]) if f['played']])
    em.set_footer(text=f"Matches played: {played} | Pending: {pending}")
    await ctx.send(embed=em)

@bot.command(name='tourneyresults')
async def tourney_results(ctx, *, name: str):
    """View all match results. Usage: +tourneyresults IPL 2026"""
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    results = tourney.get('results', [])
    if not results:
        return await ctx.send("❌ No results yet!")

    chunks = []
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"`M{i}` **{r['team1']}** vs **{r['team2']}** — 🏆 **{r['winner']}** {r['margin']} | {r['score1']} vs {r['score2']}")
        if len(lines) >= 12:
            chunks.append(lines[:])
            lines = []
    if lines:
        chunks.append(lines)

    for chunk in chunks:
        em = discord.Embed(title=f"📋 {tourney['name']} — Results", color=0x00aaff)
        em.description = "\n".join(chunk)
        await ctx.send(embed=em)

@bot.command(name='autoaddxi')
async def auto_add_xi(ctx, *, name: str):
    """Auto-add best XI for all 10 IPL 2025 teams. Usage: +autoaddxi IPL 2026"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can use this!")
    tourney = get_tourney(name)
    if not tourney:
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    if tourney['status'] != 'setup':
        return await ctx.send("❌ Tournament already started!")

    # Best XI for each IPL 2025 team (curated, role-balanced)
    BEST_XI = {
        "CSK": [
            "Ruturaj Gaikwad", "Devon Conway", "Rahul Tripathi",
            "Shivam Dube", "Rachin Ravindra", "MS Dhoni",
            "Sam Curran", "Ravindra Jadeja", "R Ashwin",
            "Matheesha Pathirana", "Khaleel Ahmed"
        ],
        "RCB": [
            "Virat Kohli", "Phil Salt", "Devdutt Padikkal",
            "Rajat Patidar", "Tim David", "Jitesh Sharma",
            "Liam Livingstone", "Krunal Pandya", "Romario Shepherd",
            "Bhuvneshwar Kumar", "Josh Hazlewood"
        ],
        "MI": [
            "Rohit Sharma", "Ryan Rickelton", "Suryakumar Yadav",
            "Tilak Varma", "Hardik Pandya", "Naman Dhir",
            "Will Jacks", "Mitchell Santner", "Jasprit Bumrah",
            "Allah Ghazanfar", "Karn Sharma"
        ],
        "KKR": [
            "Sunil Narine", "Rahmanullah Gurbaz", "Quinton de Kock",
            "Ajinkya Rahane", "Rinku Singh", "Venkatesh Iyer",
            "Andre Russell", "Ramandeep Singh", "Varun Chakravarthy",
            "Harshit Rana", "Anrich Nortje"
        ],
        "SRH": [
            "Travis Head", "Abhishek Sharma", "Ishan Kishan",
            "Heinrich Klaasen", "Nitish Reddy", "Kamindu Mendis",
            "Pat Cummins", "Harshal Patel", "Mohammad Shami",
            "Adam Zampa", "Rahul Chahar"
        ],
        "GT": [
            "Shubman Gill", "Jos Buttler", "Sai Sudharsan",
            "Shahrukh Khan", "Rahul Tewatia", "Anuj Rawat",
            "Washington Sundar", "Rashid Khan", "Kagiso Rabada",
            "Mohammed Siraj", "Prasidh Krishna"
        ],
        "RR": [
            "Yashasvi Jaiswal", "Sanju Samson", "Jos Buttler",
            "Riyan Parag", "Shimron Hetmyer", "Dhruv Jurel",
            "Wanindu Hasaranga", "Jofra Archer", "Maheesh Theekshana",
            "Fazal Farooqi", "Tushar Deshpande"
        ],
        "DC": [
            "Jake Fraser-McGurk", "KL Rahul", "Faf du Plessis",
            "Karun Nair", "Axar Patel", "Tristan Stubbs",
            "Abishek Porel", "Kuldeep Yadav", "Mitchell Starc",
            "T Natarajan", "Mohit Sharma"
        ],
        "LSG": [
            "Rishabh Pant", "Nicholas Pooran", "David Miller",
            "Aiden Markram", "Mitchell Marsh", "Abdul Samad",
            "Shahbaz Ahmed", "Ravi Bishnoi", "Mayank Yadav",
            "Avesh Khan", "Akash Deep"
        ],
        "PBKS": [
            "Shreyas Iyer", "Prabhsimran Singh", "Josh Inglis",
            "Shashank Singh", "Priyansh Arya", "Marcus Stoinis",
            "Glenn Maxwell", "Marco Jansen", "Arshdeep Singh",
            "Lockie Ferguson", "Yuzvendra Chahal"
        ],
    }

    # Match tourney teams to BEST_XI keys (case-insensitive short name match)
    SHORT_NAME_MAP = {
        "csk": "CSK", "chennai": "CSK", "chennai super kings": "CSK",
        "rcb": "RCB", "royal challengers": "RCB", "bengaluru": "RCB", "bangalore": "RCB",
        "mi":  "MI",  "mumbai": "MI", "mumbai indians": "MI",
        "kkr": "KKR", "kolkata": "KKR", "kolkata knight riders": "KKR",
        "srh": "SRH", "sunrisers": "SRH", "hyderabad": "SRH", "sunrisers hyderabad": "SRH",
        "gt":  "GT",  "gujarat": "GT", "gujarat titans": "GT",
        "rr":  "RR",  "rajasthan": "RR", "rajasthan royals": "RR",
        "dc":  "DC",  "delhi": "DC", "delhi capitals": "DC",
        "lsg": "LSG", "lucknow": "LSG", "lucknow super giants": "LSG",
        "pbks":"PBKS","punjab": "PBKS", "punjab kings": "PBKS",
    }

    added = []
    skipped = []
    for team in tourney['teams']:
        key = SHORT_NAME_MAP.get(team.lower())
        if not key:
            # Try partial match
            for k, v in SHORT_NAME_MAP.items():
                if k in team.lower() or team.lower() in k:
                    key = v
                    break
        if key and key in BEST_XI:
            tourney['xis'][team] = BEST_XI[key]
            added.append(team)
        else:
            skipped.append(team)

    set_tourney(name, tourney)

    em = discord.Embed(
        title=f"✅ Auto XI Added — {name}",
        description=f"Best XI loaded for **{len(added)}** team(s)!",
        color=0x00ff00
    )
    if added:
        xi_preview = []
        for team in added:
            xi = tourney['xis'][team]
            xi_preview.append(f"**{team}:** {', '.join(xi[:5])}... +6 more")
        em.add_field(name="🏏 Teams Set", value="\n".join(xi_preview), inline=False)
    if skipped:
        em.add_field(
            name="⚠️ Not Recognized",
            value="\n".join(f"• {t} — add manually with `+addxi {name} {t} = players...`" for t in skipped),
            inline=False
        )
    missing = [t for t in tourney['teams'] if t not in tourney['xis']]
    if not missing:
        em.set_footer(text=f"All teams ready! Use +startourney {name} to begin!")
    else:
        em.set_footer(text=f"Still need XI for: {', '.join(missing)}")
    await ctx.send(embed=em)

@bot.command(name='deltourney')
async def del_tourney(ctx, *, name: str):
    """Delete a tournament. Usage: +deltourney IPL 2026"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can delete tournaments!")
    if not get_tourney(name):
        return await ctx.send(f"❌ Tournament **{name}** not found!")
    delete_tourney(name)
    await ctx.send(f"✅ Tournament **{name}** deleted!")

@bot.command(name='listtourneys')
async def list_tourneys(ctx):
    """List all tournaments."""
    data = load_tourneys()
    if not data:
        return await ctx.send("❌ No tournaments found!")
    em = discord.Embed(title="🏆 All Tournaments", color=0xffd700)
    for tname, t in data.items():
        status_map = {'setup':'⚙️ Setup','group':'🏏 Group','playoffs':'⚡ Playoffs','done':'✅ Done'}
        em.add_field(
            name=t['name'],
            value=f"Status: {status_map.get(t['status'],'?')} | Teams: {len(t['teams'])} | Use `+tourney {t['name']}`",
            inline=False
        )
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
# TRADING CARD SYSTEM
# ─────────────────────────────────────────────
CARDS_FILE    = 'cards.json'
TEMPLATE_FILE = 'card_template.png'   # admin uploads this once via +settemplate

COUNTRY_FLAGS = {
    "India":"🇮🇳","Australia":"🇦🇺","England":"🇬🇧","Pakistan":"🇵🇰",
    "South Africa":"🇿🇦","New Zealand":"🇳🇿","West Indies":"🏴‍☠️",
    "Sri Lanka":"🇱🇰","Bangladesh":"🇧🇩","Afghanistan":"🇦🇫",
    "Zimbabwe":"🇿🇼","Ireland":"🇮🇪","Netherlands":"🇳🇱",
    "UAE":"🇦🇪","Nepal":"🇳🇵","Namibia":"🇳🇦","Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Papua New Guinea":"🇵🇬",
}

CARD_TYPES = {
    "potm":   {"label":"POTM",    "color": 0xf59e0b, "badge": "🥇"},   # Player of the Month
    "legend": {"label":"Legend",  "color": 0xdc2626, "badge": "👑"},   # Legend card
    "base":   {"label":"Base",    "color": 0x6b7280, "badge": "🃏"},   # Base card
    "odiwc":  {"label":"ODI WC",  "color": 0x059669, "badge": "🏆"},   # ODI World Cup
    "toty":   {"label":"TOTY",    "color": 0x3b82f6, "badge": "⭐"},   # Team of the Year
}
# Backwards-compat aliases for old card types already saved
_CARD_TYPE_COMPAT = {
    "rd1":  "base",
    "potd": "potm",
}
def _resolve_card_type(t):
    return _CARD_TYPE_COMPAT.get(t, t) if t not in CARD_TYPES else t

CARD_STYLES = [
    "Right-Handed Batter","Left-Handed Batter",
    "Right-Arm Pacer","Left-Arm Pacer",
    "Right-Arm Spinner","Left-Arm Spinner",
    "WK-Batter","All-Rounder",
]

COUNTRIES = sorted(COUNTRY_FLAGS.keys())

# ── CARD ZONES (calibrated for 842×1264 template) ──────────────────
STAD_X0,STAD_Y0 = 148,125
STAD_X1,STAD_Y1 = 730,825
NAME_CX,NAME_CY = 421,846
STYLE_CX,STYLE_CY = 421,916
STAT_Y           = 1155
BAT_CX,OVR_CX,BOWL_CX = 154,421,688


def load_cards():
    if not os.path.exists(CARDS_FILE): return {}
    with open(CARDS_FILE) as f: return json.load(f)

def save_cards(data):
    with open(CARDS_FILE,'w') as f: json.dump(data,f,indent=2)


def compose_card(player_img_bytes, name, bat, ovr, bowl, style):
    """If template exists: paste player PNG into template and draw stats.\nIf no template: return the player image as-is (it IS the card)."""
    if not PILLOW_AVAILABLE: return None

    # No template — treat the attached image as the final card directly
    if not os.path.exists(TEMPLATE_FILE):
        if player_img_bytes:
            return io.BytesIO(player_img_bytes)
        return None

    tpath = TEMPLATE_FILE

    template = Image.open(tpath).convert("RGBA")
    card     = template.copy()
    STAD_W   = STAD_X1 - STAD_X0
    STAD_H   = STAD_Y1 - STAD_Y0

    # ── Player image ──────────────────────────────────────────────
    if player_img_bytes:
        try:
            pimg = Image.open(io.BytesIO(player_img_bytes)).convert("RGBA")
            # Scale to fill stadium height, keeping aspect; align bottom-center
            scale = STAD_H / pimg.height
            nw,nh = int(pimg.width*scale), STAD_H
            if nw > STAD_W:
                scale = STAD_W / pimg.width
                nw,nh = STAD_W, int(pimg.height*scale)
            pimg = pimg.resize((nw,nh), Image.LANCZOS)
            px = STAD_X0 + (STAD_W-nw)//2
            py = STAD_Y1 - nh
            card.paste(pimg, (px,py), pimg)
        except Exception as e:
            print(f"[Card] player img error: {e}")

    draw = ImageDraw.Draw(card)

    # ── Name ──────────────────────────────────────────────────────
    fn = _fnt(52)
    tw = draw.textlength(name.upper(), font=fn)
    draw.text((NAME_CX - tw//2, NAME_CY - 32), name.upper(),
              font=fn, fill=(255,215,0), stroke_width=2, stroke_fill=(0,0,0))

    # ── Style ─────────────────────────────────────────────────────
    fs = _fnt(26, bold=False)
    tw2 = draw.textlength(style, font=fs)
    draw.text((STYLE_CX - tw2//2, STYLE_CY - 15), style,
              font=fs, fill=(200,200,255), stroke_width=1, stroke_fill=(0,0,0))

    # ── Stats ─────────────────────────────────────────────────────
    fst = _fnt(88)
    for val, cx in [(str(bat),BAT_CX),(str(ovr),OVR_CX),(str(bowl),BOWL_CX)]:
        tw3 = draw.textlength(val, font=fst)
        draw.text((cx - tw3//2, STAT_Y-52), val,
                  font=fst, fill=(255,255,255), stroke_width=3, stroke_fill=(0,0,0))

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_buy_card(name, ovr, bat, bowl, role, player_bytes=None):
    """Cricket Go style card — dark navy, diagonal stripes, name top, OVR badge, stats bottom."""
    if not PILLOW_AVAILABLE: return None
    W, H = 500, 680
    ROLE_COLORS = {
        "Right-Handed Batter":(220,30,100),"Left-Handed Batter":(220,30,100),
        "Right-Arm Pacer":(30,140,255),"Left-Arm Pacer":(30,140,255),
        "Right-Arm Spinner":(255,140,0),"Left-Arm Spinner":(255,140,0),
        "WK-Batter":(0,180,160),"All-Rounder":(160,50,220),
        "BATTER":(220,30,100),"BOWLER":(30,140,255),"ALL-ROUNDER":(160,50,220),
    }
    accent = ROLE_COLORS.get(role, (220,30,100))
    card = Image.new("RGB",(W,H),(8,12,35))
    draw = ImageDraw.Draw(card)
    draw.rectangle([0,0,W,6], fill=accent)
    draw.rectangle([0,H-5,W,H], fill=accent)
    # Name banner
    draw.rectangle([0,6,W,70], fill=(14,20,58))
    # OVR gold circle
    draw.ellipse([W-78,8,W-8,66], fill=(255,200,0))
    fnt_ovr=_fnt(30)
    ovr_s=str(ovr); ow=draw.textlength(ovr_s,font=fnt_ovr)
    draw.text((W-43-ow//2,20),ovr_s,font=fnt_ovr,fill=(10,10,10))
    # Name
    fnt_name=_fnt(28)
    nm=name.upper(); nw=draw.textlength(nm,font=fnt_name)
    if nw>W-96: fnt_name=_fnt(21); nw=draw.textlength(nm,font=fnt_name)
    draw.text(((W-90-nw)//2+4,22),nm,font=fnt_name,fill=(255,255,255))
    draw.rectangle([0,70,W,76],fill=accent)
    # Image area diagonal stripes
    img_y0,img_y1=76,492
    for x in range(-H,W+H,20):
        draw.polygon([(x,img_y0),(x+H,img_y1),(x+H+16,img_y1),(x+16,img_y0)],fill=(20,30,82))
    # Central glow
    cxm,cym=W//2,(img_y0+img_y1)//2
    for r in range(160,0,-18):
        draw.ellipse([cxm-r,cym-r,cxm+r,cym+r],
            fill=(max(12,38-r//6),max(22,68-r//4),max(70,125-r//3)))
    # Player image
    if player_bytes:
        try:
            pimg=Image.open(io.BytesIO(player_bytes)).convert("RGBA")
            ph=img_y1-img_y0; pw2=int(pimg.width*ph/pimg.height)
            if pw2>W: pw2=W; ph=int(pimg.height*W/pimg.width)
            pimg=pimg.resize((pw2,ph),Image.LANCZOS)
            card.paste(pimg,((W-pw2)//2,img_y1-ph),pimg)
        except Exception as e: print(f"[BuyCard] {e}")
    # Role pill
    draw.rectangle([0,492,W,536],fill=(10,16,46))
    rl=role.upper()[:14]; pw3=min(200,len(rl)*14+30); px2=(W-pw3)//2
    draw.rounded_rectangle([px2,497,px2+pw3,531],radius=14,fill=accent)
    fnt_r=_fnt(20); rw2=draw.textlength(rl,font=fnt_r)
    draw.text((px2+(pw3-rw2)//2,505),rl,font=fnt_r,fill=(255,255,255))
    # Stats
    stats_y=536
    draw.rectangle([0,stats_y,W,H-5],fill=(8,12,35))
    draw.line([(W//3,stats_y+8),(W//3,H-14)],fill=(35,46,88),width=2)
    draw.line([(2*W//3,stats_y+8),(2*W//3,H-14)],fill=(35,46,88),width=2)
    fnt_sv=_fnt(40); fnt_sl=_fnt(16,bold=False)
    for i,(lbl,val,col) in enumerate([
        ("BAT",bat,(220,30,100)),("BOWL",bowl,(255,120,0)),
        ("FIELDING",min(99,(bat+bowl)//2+5),(0,180,80))
    ]):
        scx=(i*W//3)+W//6
        draw.ellipse([scx-8,stats_y+8,scx+8,stats_y+24],fill=col)
        vs=str(val); vw=draw.textlength(vs,font=fnt_sv)
        draw.text((scx-vw//2,stats_y+24),vs,font=fnt_sv,fill=(255,255,255))
        lw2=draw.textlength(lbl,font=fnt_sl)
        draw.text((scx-lw2//2,H-26),lbl,font=fnt_sl,fill=(130,140,185))
    buf=io.BytesIO(); card.save(buf,format="PNG"); buf.seek(0)
    return buf


# ── Step 3 — Style ───────────────────────────────────────────────────────────
class AddCardStyleView(discord.ui.View):
    def __init__(self, ctx, name, country, ovr, bat, bowl, card_type, player_bytes, price=0):
        super().__init__(timeout=120)
        self.ctx=ctx; self.name=name; self.country=country; self.price=price
        self.ovr=ovr; self.bat=bat; self.bowl=bowl
        self.card_type=card_type; self.player_bytes=player_bytes
        sel=discord.ui.Select(placeholder="🧢 Select player style…",
            options=[discord.SelectOption(label=s,value=s) for s in CARD_STYLES])
        sel.callback=self._on
        self.add_item(sel)

    async def _on(self, interaction:discord.Interaction):
        if interaction.user.id!=self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your command!",ephemeral=True)
        style=interaction.data["values"][0]
        await interaction.response.edit_message(content="⚙️ Generating card…",embed=None,view=None)

        loop=asyncio.get_event_loop()
        buf=await loop.run_in_executor(None,compose_card,
            self.player_bytes,self.name,self.bat,self.ovr,self.bowl,style)

        import base64
        cards=load_cards()
        cid=f"{self.name.lower().replace(' ','_')}_{self.card_type}"
        cards[cid]={
            "name":self.name,"country":self.country,
            "ovr":self.ovr,"bat":self.bat,"bowl":self.bowl,
            "style":style,"type":self.card_type,"price":self.price,
            "player_b64":base64.b64encode(self.player_bytes).decode() if self.player_bytes else "",
        }
        save_cards(cards)

        cinfo=CARD_TYPES.get(self.card_type,CARD_TYPES["rd1"])
        flag=COUNTRY_FLAGS.get(self.country,"🌍")
        em=discord.Embed(
            title=f"{cinfo['badge']} {self.name}  —  {cinfo['label']}",
            description=f"{flag} **{self.country}**  ·  {style}\n"
                        f"**BAT** {self.bat}  |  **OVR** {self.ovr}  |  **BOWL** {self.bowl}",
            color=cinfo["color"]
        )
        if buf:
            await self.ctx.channel.send(embed=em,file=discord.File(buf,filename="card.png"))
        else:
            await self.ctx.channel.send(embed=em)


# ── Step 2 — Card Type ───────────────────────────────────────────────────────
class AddCardTypeView(discord.ui.View):
    def __init__(self, ctx, name, country, ovr, bat, bowl, player_bytes, price=0):
        super().__init__(timeout=120)
        self.ctx=ctx; self.name=name; self.country=country; self.price=price
        self.ovr=ovr; self.bat=bat; self.bowl=bowl; self.player_bytes=player_bytes
        TYPE_DESCS = {
            "potm":   "Player of the Month award",
            "legend": "All-time legend special edition",
            "base":   "Standard base card",
            "odiwc":  "ODI World Cup special edition",
            "toty":   "Team of the Year selection",
        }
        options = [discord.SelectOption(
            label=f"{v['badge']} {v['label']}",
            value=k,
            description=TYPE_DESCS.get(k,"")
        ) for k, v in CARD_TYPES.items()]
        sel=discord.ui.Select(placeholder="🏷️ Select card type…",options=options)
        sel.callback=self._on
        self.add_item(sel)

    async def _on(self, interaction:discord.Interaction):
        if interaction.user.id!=self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your command!",ephemeral=True)
        ct=interaction.data["values"][0]
        cinfo=CARD_TYPES[ct]
        flag=COUNTRY_FLAGS.get(self.country,"🌍")
        em=discord.Embed(title=f"{cinfo['badge']} {cinfo['label']} selected",
            description=f"**{self.name}**  ·  {flag} {self.country}\nNow pick the **player style**.",
            color=cinfo["color"])
        await interaction.response.edit_message(embed=em,
            view=AddCardStyleView(self.ctx,self.name,self.country,
                                   self.ovr,self.bat,self.bowl,ct,self.player_bytes,price=self.price))


# ── Step 1 — Country ─────────────────────────────────────────────────────────
class AddCardCountryView(discord.ui.View):
    def __init__(self, ctx, name, ovr, bat, bowl, player_bytes, price=0):
        super().__init__(timeout=120)
        self.ctx=ctx; self.name=name; self.price=price
        self.ovr=ovr; self.bat=bat; self.bowl=bowl; self.player_bytes=player_bytes
        options=[discord.SelectOption(label=f"{COUNTRY_FLAGS.get(c,'🌍')} {c}",value=c)
                 for c in COUNTRIES[:25]]
        sel=discord.ui.Select(placeholder="🌍 Select country…",options=options)
        sel.callback=self._on
        self.add_item(sel)

    async def _on(self, interaction:discord.Interaction):
        if interaction.user.id!=self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your command!",ephemeral=True)
        country=interaction.data["values"][0]
        flag=COUNTRY_FLAGS.get(country,"🌍")
        em=discord.Embed(title=f"{flag} {country} selected",
            description=f"**{self.name}**\nNow pick the **card type**.",color=0x00aaff)
        await interaction.response.edit_message(embed=em,
            view=AddCardTypeView(self.ctx,self.name,country,
                                  self.ovr,self.bat,self.bowl,self.player_bytes,price=self.price))


# ── COMMANDS ─────────────────────────────────────────────────────────────────

@bot.command(name='settemplate')
async def set_template(ctx):
    """(Admin) Upload the card template PNG. Usage: +settemplate (attach PNG)"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can set the template!")
    if not ctx.message.attachments:
        return await ctx.send("❌ Please attach the template PNG!")
    att = ctx.message.attachments[0]
    if not att.filename.lower().endswith(('.png','.jpg','.jpeg')):
        return await ctx.send("❌ Please attach a PNG/JPG file!")
    await att.save(TEMPLATE_FILE)
    await ctx.send(f"✅ Card template saved as `{TEMPLATE_FILE}`! ({att.filename})")


@bot.command(name='addcard')
async def add_card(ctx, name:str, ovr:int, bat:int, bowl:int, price:int=0):
    """(Admin) Create a cricket trading card.\nUsage: +addcard "Player Name" <ovr> <bat> <bowl> <price>\nAttach player PNG. Follow 3 dropdowns: Country → Type → Style."""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can create cards!")
    if not (1<=ovr<=99 and 1<=bat<=99 and 1<=bowl<=99):
        return await ctx.send("❌ OVR, BAT and BOWL must each be 1–99.")
    player_bytes=None
    if ctx.message.attachments:
        att=ctx.message.attachments[0]
        if att.filename.lower().endswith(('.png','.jpg','.jpeg','.webp')):
            player_bytes=await att.read()

    em=discord.Embed(title=f"🃏 Creating card — {name}",
        description=(
            f"**BAT** {bat}  |  **OVR** {ovr}  |  **BOWL** {bowl}"
            + (f"  |  💰 **{price:,}**" if price else "") + "\n"
            f"{'✅ Player image attached!' if player_bytes else '⚠️ No image — stadium bg only.'}\n\n"
            "**Step 1:** Pick the player's **country** ↓"
        ),color=0x9b59b6)
    await ctx.send(embed=em,view=AddCardCountryView(ctx,name,ovr,bat,bowl,player_bytes,price=price))


@bot.command(name='card')
async def view_card(ctx, *, name:str):
    """View a saved card. Usage: +card Virat Kohli"""
    import base64
    cards=load_cards()
    matches={k:v for k,v in cards.items() if name.lower() in v["name"].lower()}
    if not matches:
        return await ctx.send(f"❌ No card found for **{name}**.")
    card=list(matches.values())[0]
    cinfo=CARD_TYPES.get(card["type"],CARD_TYPES["rd1"])
    flag=COUNTRY_FLAGS.get(card["country"],"🌍")

    pb=card.get("player_b64","")
    player_bytes=base64.b64decode(pb) if pb else None

    loop=asyncio.get_event_loop()
    buf=await loop.run_in_executor(None,compose_card,
        player_bytes,card["name"],card["bat"],card["ovr"],card["bowl"],card["style"])

    em=discord.Embed(
        title=f"{cinfo['badge']} {card['name']}  —  {cinfo['label']}",
        description=f"{flag} **{card['country']}**  ·  {card['style']}\n"
                    f"**BAT** {card['bat']}  |  **OVR** {card['ovr']}  |  **BOWL** {card['bowl']}",
        color=cinfo["color"])
    if buf:
        await ctx.send(embed=em,file=discord.File(buf,filename="card.png"))
    else:
        await ctx.send(embed=em)


# ─────────────────────────────────────────────
# MILESTONE GIFs (50 / 100)
# ─────────────────────────────────────────────
def _load_gifs():
    if not os.path.exists(GIFS_FILE):
        return {}
    try:
        return load_json(GIFS_FILE)
    except Exception:
        return {}

def _save_gifs(d):
    save_json(d, GIFS_FILE)

def get_milestone_gif(player_name: str, milestone):
    """Return a random GIF URL for a player event (50, 100, or 'wicket'), or None.
    Uses fuzzy name matching so 'Jasprit Bumrah' matches 'bumrah' etc."""
    import random as _rand
    gifs = _load_gifs()
    key = (player_name or "").strip().lower()

    # 1) Exact key match
    entry = gifs.get(key)

    # 2) Fuzzy: stored key is substring of player name or vice versa
    if not entry:
        for sk, sv in gifs.items():
            if sk.startswith("_"):
                continue
            skl = sk.strip().lower()
            if skl in key or key in skl:
                entry = sv
                break

    # 3) Any word in common (e.g. "bumrah" in "jasprit bumrah")
    if not entry:
        kparts = set(key.split())
        for sk, sv in gifs.items():
            if sk.startswith("_"):
                continue
            if kparts & set(sk.strip().lower().split()):
                entry = sv
                break

    # 4) Global wicket pool fallback
    if not entry and str(milestone) == "wicket":
        entry = gifs.get("_global_wicket")

    if not entry:
        return None
    val = entry.get(str(milestone))
    if not val:
        return None
    if isinstance(val, list):
        return _rand.choice(val) if val else None
    return val

async def post_wicket_gif(channel, bowler_name: str, batter_name: str, match):
    """Post a wicket celebration GIF for the bowler."""
    print(f"[WicketGIF] bowler='{bowler_name}' searching gifs...")
    gif_url = get_milestone_gif(bowler_name, "wicket")
    print(f"[WicketGIF] url={gif_url!r}")
    if not gif_url:
        return
    bw = match.bowl_stats.get(bowler_name, {})
    wkts = bw.get("wickets", 0)
    em = discord.Embed(
        title=f"🎳 WICKET! {bowler_name} strikes!",
        description=f"**{batter_name}** is OUT!  |  {bowler_name}: **{wkts}W**",
        color=0xe74c3c,
    )
    try:
        # Send GIF URL as message content — the ONLY way Discord shows animated GIFs from bots
        # set_image() only shows static thumbnails for Tenor URLs
        await channel.send(content=gif_url, embed=em)
    except Exception as e:
        print(f"[Wicket GIF error] {e}")


async def post_milestone_gifs(channel, match):
    """Check all batters for newly-crossed 50/100 milestones and post their GIFs.\nUses match._milestones_announced to avoid duplicates."""
    if not hasattr(match, "_milestones_announced"):
        match._milestones_announced = set()
    inn_stats = match.innings_bat_stats.get(match.innings, {})
    for bname, s in list(inn_stats.items()):
        runs = s.get("runs", 0)
        for ms in (150, 100, 50):
            if runs >= ms and (bname, ms) not in match._milestones_announced:
                match._milestones_announced.add((bname, ms))
                if ms == 100:
                    match._milestones_announced.add((bname, 50))
                if ms == 150:
                    match._milestones_announced.add((bname, 100))
                    match._milestones_announced.add((bname, 50))
                gif_url = get_milestone_gif(bname, ms)
                if ms == 150:   title, color = "🚀 150!", 0x9b59b6
                elif ms == 100: title, color = "💯 CENTURY!", 0xFFD700
                else:           title, color = "🎉 FIFTY!",   0x00BFFF
                em = discord.Embed(
                    title=f"{title} — {bname} ({runs})",
                    description=f"**{bname}** brings up **{ms}**!",
                    color=color,
                )
                try:
                    if gif_url:
                        em.set_image(url=gif_url)
                    await channel.send(embed=em)
                except Exception as e:
                    print(f"[Milestone GIF Error] {e}")
                break


def _resolve_gif_url(url: str) -> str:
    """Resolve a Tenor/Giphy share URL to a direct .gif media URL
    that Discord bots can use in embed set_image()."""
    import re as _re
    import urllib.request as _ulr
    import json as _json

    url = url.strip().strip("<>")
    low = url.lower().split("?")[0]

    # Already a direct media file — use as-is
    if low.endswith((".gif", ".webp", ".mp4", ".png")):
        return url

    # ── TENOR ────────────────────────────────────────────────────────────────
    if "tenor.com" in low:
        # Try Tenor API v2 with anonymous key — extract GIF ID from URL first
        try:
            gif_id_match = _re.search(r"-(\d+)(?:\?|$)", url)
            if gif_id_match:
                gif_id = gif_id_match.group(1)
                api_url = (
                    f"https://tenor.googleapis.com/v2/posts"
                    f"?ids={gif_id}"
                    f"&key=AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCyk"
                    f"&client_key=nexus_bot&media_filter=gif"
                )
                req = _ulr.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                with _ulr.urlopen(req, timeout=8) as resp:
                    data = _json.loads(resp.read().decode())
                results = data.get("results", [])
                if results:
                    media = results[0].get("media_formats", {})
                    for fmt in ("gif", "mediumgif", "tinygif"):
                        if fmt in media:
                            direct = media[fmt]["url"]
                            print(f"[GIF API] Resolved {url} -> {direct[:60]}...")
                            return direct
        except Exception as _e:
            print(f"[GIF Tenor API] {_e}")

        # Fallback: scrape the page for a direct media URL in JSON blob
        try:
            req = _ulr.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with _ulr.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            for pat in [
                r'"gif"\s*:\s*\{[^}]*?"url"\s*:\s*"(https://media\.tenor\.com/[^"]+\.gif)"',
                r'"url"\s*:\s*"(https://media\.tenor\.com/[A-Za-z0-9_-]+/[^"]+\.gif)"',
                r'(https://media\.tenor\.com/[A-Za-z0-9_-]+/[^"\'<>\s]+\.gif)',
            ]:
                m = _re.search(pat, html, _re.I | _re.S)
                if m:
                    found = _re.sub(r"https?://media\d+\.tenor\.com/",
                                    "https://media.tenor.com/", m.group(1))
                    if found.startswith("https://media.tenor.com/"):
                        print(f"[GIF scrape] Resolved -> {found[:60]}...")
                        return found
        except Exception as _e2:
            print(f"[GIF Tenor scrape] {_e2}")

        return url  # last resort

    # ── GIPHY ────────────────────────────────────────────────────────────────
    if "giphy.com" in low:
        try:
            req = _ulr.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ulr.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            m = _re.search(r"(https://media\d*\.giphy\.com/media/[^\"\'<>\s]+\.gif)", html)
            if m:
                return m.group(1)
        except Exception:
            pass

    return url


@bot.command(name='cleargifs', aliases=['gifclear','gifdelete'])
async def clear_gifs(ctx, *, payload: str = None):
    """(Admin) Clear all GIFs for a player + event, or all events.
    Usage: +cleargifs Jasprit Bumrah wicket
           +cleargifs Virat Kohli all"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Admins only!")
    if not payload:
        return await ctx.send("Usage: `+cleargifs <Player Name> <wicket|50|100|all>`")
    parts = payload.strip().split()
    event_str = parts[-1].lower()
    name = " ".join(parts[:-1]).strip()
    if not name:
        return await ctx.send("❌ Player name required.")
    gifs = _load_gifs()
    key = name.lower()
    # Find matching key (fuzzy)
    matched_key = None
    for sk in gifs:
        if sk.startswith("_"): continue
        if sk == key or key in sk or sk in key:
            matched_key = sk; break
    if not matched_key:
        return await ctx.send(f"❌ No GIFs found for **{name}**.")
    if event_str == "all":
        del gifs[matched_key]
        _save_gifs(gifs)
        await ctx.send(f"🗑️ All GIFs for **{gifs.get(matched_key, {}).get('_display', name)}** deleted.")
    else:
        if event_str not in gifs[matched_key]:
            return await ctx.send(f"❌ No **{event_str}** GIF found for **{name}**.")
        del gifs[matched_key][event_str]
        _save_gifs(gifs)
        await ctx.send(f"🗑️ **{event_str}** GIF(s) for **{name}** cleared. Re-add with `+addgif`.")


@bot.command(name='addgif')
async def add_gif(ctx, *, payload: str = None):
    """(Admin) Add a GIF for a player event. Multiple GIFs supported — one random plays each time.\nUsage:\n+addgif <Player Name> wicket <gif url>   — plays when that bowler takes a wicket\n+addgif <Player Name> 50 <gif url>       — plays when that batter hits a fifty\n+addgif <Player Name> 100 <gif url>      — plays when that batter hits a century\nTip: Run the command multiple times with different URLs to build a random pool!\n"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can add GIFs!")
    if not payload or not payload.strip():
        return await ctx.send(
            "❌ **Usage:**\n"
            "`+addgif Jasprit Bumrah wicket https://tenor.com/view/...`\n"
            "`+addgif Virat Kohli 50 https://tenor.com/view/...`\n"
            "`+addgif Virat Kohli 100 https://tenor.com/view/...`\n"
            "Run multiple times with different URLs to build a random pool!"
        )
    parts = payload.strip().split()
    if len(parts) < 3:
        return await ctx.send("❌ Need: `<Player Name> <wicket|50|100> <gif url>`")

    raw_url = parts[-1].strip("<>")
    event_str = parts[-2].lower()
    name = " ".join(parts[:-2]).strip()

    VALID_EVENTS = ("wicket", "50", "100", "150")
    if event_str not in VALID_EVENTS:
        return await ctx.send(f"❌ Event must be one of: **wicket**, **50**, **100**, **150**.")
    if not (raw_url.startswith("http://") or raw_url.startswith("https://")):
        return await ctx.send("❌ GIF URL must start with `http://` or `https://`.")
    if not name:
        return await ctx.send("❌ Player name is required.")

    # Find player — check cards DB first, then ALL_PLAYERS
    cards   = load_cards() if os.path.exists(CARDS_FILE) else {}
    name_lc = name.lower()
    matched_display = None

    # 1) Exact match in cards DB
    for cid, c in cards.items():
        cname = (c.get("name") or "").strip()
        if cname.lower() == name_lc:
            matched_display = cname; break

    # 2) Substring match in cards DB
    if not matched_display:
        subs = [(cid, c) for cid, c in cards.items()
                if name_lc in (c.get("name") or "").lower()]
        if len(subs) == 1:
            matched_display = subs[0][1].get("name") or name
        elif len(subs) > 1:
            opts = ", ".join(f"`{c.get('name')}`" for _, c in subs[:8])
            return await ctx.send(f"❌ Multiple matches for **{name}**: {opts}")

    # 3) Check ALL_PLAYERS DB
    if not matched_display:
        found_name, _ = find_player(name)
        if found_name:
            matched_display = found_name

    if not matched_display:
        return await ctx.send(
            f"❌ **{name}** not found in cards DB or player pool.\n"
            f"Either add with `+addcard \"{name}\" <ovr> <bat> <bowl> <price>` "
            f"or check spelling."
        )

    # Resolve Tenor/Giphy share links → direct media URL
    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, _resolve_gif_url, raw_url)

    # Save — store as list so multiple GIFs are supported
    gifs  = _load_gifs()
    key   = matched_display.lower()
    entry = gifs.setdefault(key, {"_display": matched_display})
    entry["_display"] = matched_display

    existing = entry.get(event_str)
    if existing is None:
        entry[event_str] = [url]       # first GIF — start list
        added_count = 1
    elif isinstance(existing, str):
        entry[event_str] = [existing, url]  # upgrade string → list
        added_count = 2
    else:
        existing.append(url)
        entry[event_str] = existing
        added_count = len(existing)

    _save_gifs(gifs)

    event_labels = {
        "wicket": "🎳 Wicket",
        "50":     "🎉 Fifty",
        "100":    "💯 Century",
        "150":    "🚀 150",
    }
    event_label = event_labels.get(event_str, event_str)

    em = discord.Embed(
        title=f"✅ GIF Added — {matched_display}",
        description=(
            f"**Event:** {event_label}\n"
            f"**Pool size:** {added_count} GIF(s) (random will play each time)\n\n"
            f"This GIF will fire when **{matched_display}** "
            + ("takes a **wicket**." if event_str=="wicket" else f"reaches **{event_str}** runs.")
        ),
        color=0x00e676,
    )
    em.set_image(url=url)
    if url != raw_url:
        em.set_footer(text="✅ Resolved share link → direct media URL")
    await ctx.send(embed=em)


@bot.command(name='gifs', aliases=['listgifs'])
async def list_gifs(ctx):
    """List all configured GIFs."""
    gifs = _load_gifs()
    if not gifs:
        return await ctx.send("📭 No GIFs configured yet.\nUse `+addgif <player> <wicket|50|100> <url>`.")
    em = discord.Embed(title="🎬 Configured GIFs", color=0x9b59b6,
        description="Run `+addgif` multiple times to build a random pool per event.")
    for key, entry in list(gifs.items())[:25]:
        if key == "_global_wicket": continue
        disp = entry.get("_display", key.title())
        bits = []
        for evt, label in [("wicket","🎳 Wicket"),("50","🎉 50"),("100","💯 100"),("150","🚀 150")]:
            val = entry.get(evt)
            if val:
                cnt = len(val) if isinstance(val, list) else 1
                bits.append(f"{label} ×{cnt}")
        em.add_field(name=disp, value="  ·  ".join(bits) if bits else "—", inline=False)
    await ctx.send(embed=em)


# Old removegif replaced by +cleargifs


@bot.command(name='deletecard', aliases=['delcard','removecard'])
async def delete_card(ctx, *, name: str):
    """(Admin) Delete a card from the database. Usage: +deletecard Rohit Sharma"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can delete cards!")
    cards = load_cards()
    q = name.strip().lower()
    # Exact match by card ID first (handles disambiguation like rohit_sharma_odiwc)
    if q in cards:
        cid = q
        c = cards[cid]
        em = discord.Embed(title=f"🗑️ Delete **{c['name']}**?",
            description=f"Type: {c['type']}  ·  OVR {c['ovr']}  ·  ID: `{cid}`\nThis cannot be undone!",
            color=0xff0000)
        view = DeleteCardConfirmView(ctx.author.id, cid, c["name"])
        return await ctx.send(embed=em, view=view)
    # Fall back to substring match across name OR card id
    matches = {k: v for k, v in cards.items()
               if q in v["name"].lower() or q in k.lower()}
    if not matches:
        return await ctx.send(f"❌ No card found matching **{name}**.")
    if len(matches) > 1:
        em = discord.Embed(title="⚠️ Multiple matches found — be more specific:",
                           color=0xff9900)
        for cid, c in list(matches.items())[:10]:
            cinfo = CARD_TYPES.get(_resolve_card_type(c.get("type","base")), CARD_TYPES["base"])
            em.add_field(name=f"{cinfo['badge']} {c['name']}",
                         value=f"ID: `{cid}` · {c['type']} · OVR {c['ovr']}", inline=False)
        return await ctx.send(embed=em)
    cid, c = list(matches.items())[0]
    # Confirm view
    em = discord.Embed(title=f"🗑️ Delete **{c['name']}**?",
        description=f"Type: {c['type']}  ·  OVR {c['ovr']}  ·  ID: `{cid}`\nThis cannot be undone!",
        color=0xff0000)
    view = DeleteCardConfirmView(ctx.author.id, cid, c["name"])
    await ctx.send(embed=em, view=view)


class DeleteCardConfirmView(discord.ui.View):
    def __init__(self, admin_id, card_id, card_name):
        super().__init__(timeout=30)
        self.admin_id  = admin_id
        self.card_id   = card_id
        self.card_name = card_name

    @discord.ui.button(label="✅ Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.admin_id:
            return await interaction.response.send_message("❌ Not your command!", ephemeral=True)
        cards = load_cards()
        if self.card_id in cards:
            del cards[self.card_id]
            save_cards(cards)
            await interaction.response.edit_message(
                content=f"🗑️ **{self.card_name}** has been deleted.", embed=None, view=None)
        else:
            await interaction.response.edit_message(
                content="❌ Card not found (already deleted?).", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)
        self.stop()


@bot.command(name='cards')
async def list_cards(ctx):
    """List all created cards. Usage: +cards"""
    cards=load_cards()
    if not cards:
        return await ctx.send("❌ No cards yet! Use `+addcard` to create one.")
    em=discord.Embed(title="🃏 Cricket Card Collection",color=0xf1c40f)
    for cid,c in list(cards.items())[:20]:
        cinfo=CARD_TYPES.get(_resolve_card_type(c.get("type","base")),CARD_TYPES["base"])
        flag=COUNTRY_FLAGS.get(c["country"],"🌍")
        em.add_field(name=f"{cinfo['badge']} {c['name']}",
            value=f"{flag} {c['country']}  ·  OVR **{c['ovr']}**  BAT **{c['bat']}**  BOWL **{c['bowl']}**  ·  _{c['style']}_",
            inline=False)
    if len(cards)>20: em.set_footer(text=f"Showing 20 of {len(cards)} cards.")
    await ctx.send(embed=em)


# ── GIVE COMMANDS ─────────────────────────────────────────────────────────────
@bot.command(name='givecoins')
async def give_coins(ctx, member:discord.Member, amount:int):
    """(Admin) Give coins to a user. Usage: +givecoins @user 500"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can give coins!")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
    uid=str(member.id)
    b=get_balance(uid)
    b["coins"]+=amount
    set_balance(uid,b["coins"],b["tickets"])
    em=discord.Embed(
        title="🪙 Coins Given!",
        description=f"**{amount:,}** coins given to {member.mention}",
        color=0xf1c40f)
    em.add_field(name="New Balance",value=f"🪙 {b['coins']:,} coins",inline=True)
    em.set_footer(text=f"Given by {ctx.author.display_name}")
    await ctx.send(embed=em)


@bot.command(name='givetics')
async def give_tics(ctx, member:discord.Member, amount:int):
    """(Admin) Give tics (tickets) to a user. Usage: +givetics @user 10"""
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Only admins can give tics!")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
    uid=str(member.id)
    b=get_balance(uid)
    b["tickets"]+=amount
    set_balance(uid,b["coins"],b["tickets"])
    em=discord.Embed(
        title="🎟️ Tics Given!",
        description=f"**{amount:,}** tics given to {member.mention}",
        color=0x00e5ff)
    em.add_field(name="New Balance",value=f"🎟️ {b['tickets']:,} tics",inline=True)
    em.set_footer(text=f"Given by {ctx.author.display_name}")
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
# DAILY & SPECIAL QUESTS
# ─────────────────────────────────────────────
import pytz
from datetime import datetime as _dt

QUESTS_FILE = "quests.json"
IST = pytz.timezone("Asia/Kolkata")

DAILY_QUESTS = [
    {"id":"dq1","desc":"Count **20** Times",           "target":20,  "type":"count",   "reward":40_000},
    {"id":"dq2","desc":"Send **200** Messages",         "target":200, "type":"messages","reward":60_000},
    {"id":"dq3","desc":"Win **1** Simulation Match",    "target":1,   "type":"sim_win", "reward":10_000},
    {"id":"dq4","desc":"Score a **Half Century** (Century = 40k)","target":1,"type":"fifty","reward":20_000},
    {"id":"dq5","desc":"Take a **3-fer** in bowling",   "target":1,   "type":"threfer", "reward":20_000},
]
DAILY_BONUS  = {"min_complete":3, "reward":20_000, "id":"daily_bonus"}

SPECIAL_QUESTS = [
    {"id":"sq1","desc":"Send **2000** Messages",        "target":2000,"type":"messages","reward":100_000},
    {"id":"sq2","desc":"Win **5** Simulation Matches",  "target":5,   "type":"sim_win", "reward":80_000},
    {"id":"sq3","desc":"Score **3 Centuries**",         "target":3,   "type":"century", "reward":80_000},
    {"id":"sq4","desc":"Take **3 Five-fers** in bowling","target":3,  "type":"fivefer", "reward":40_000},
    {"id":"sq5","desc":"Claim **3 MVPs** from one player","target":3, "type":"mvp",     "reward":60_000},
]
SPECIAL_BONUS = {"min_complete":5, "reward":60_000, "id":"special_bonus"}


def _ist_today():
    return _dt.now(IST).strftime("%Y-%m-%d")

def _ist_saturday():
    """Return this week's Saturday date string (IST)."""
    now = _dt.now(IST)
    days_ahead = 5 - now.weekday()  # Saturday = 5
    if days_ahead < 0: days_ahead += 7
    return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def load_quests():
    if not os.path.exists(QUESTS_FILE): return {}
    with open(QUESTS_FILE) as f: return json.load(f)

def save_quests(data):
    with open(QUESTS_FILE, "w") as f: json.dump(data, f, indent=2)

def get_user_quests(uid):
    data  = load_quests()
    today = _ist_today()
    week_end = _ist_saturday()
    user  = data.get(uid, {})
    # Reset daily quests if new day
    if user.get("daily_date") != today:
        user["daily_date"]   = today
        user["daily_prog"]   = {q["id"]: 0 for q in DAILY_QUESTS}
        user["daily_claimed"]= []
        user["daily_bonus"]  = False
    # Reset special quests if new week (Saturday boundary)
    if user.get("special_week") != week_end:
        user["special_week"]  = week_end
        user["special_prog"]  = {q["id"]: 0 for q in SPECIAL_QUESTS}
        user["special_claimed"]= []
        user["special_bonus"] = False
    data[uid] = user
    save_quests(data)
    return user

def update_quest_progress(uid, quest_type, amount=1):
    """Call this from match/message events. Returns list of newly completed quest ids."""
    user   = get_user_quests(uid)
    newly  = []
    # Daily
    for q in DAILY_QUESTS:
        if q["type"] == quest_type and q["id"] not in user["daily_claimed"]:
            user["daily_prog"][q["id"]] = user["daily_prog"].get(q["id"], 0) + amount
            if user["daily_prog"][q["id"]] >= q["target"]:
                newly.append(("daily", q))
    # Special
    for q in SPECIAL_QUESTS:
        if q["type"] == quest_type and q["id"] not in user.get("special_claimed", []):
            user["special_prog"][q["id"]] = user["special_prog"].get(q["id"], 0) + amount
            if user["special_prog"][q["id"]] >= q["target"]:
                newly.append(("special", q))
    data = load_quests()
    data[uid] = user
    save_quests(data)
    return newly


@bot.command(name="count")
async def count_cmd(ctx):
    """Count once — contributes to the 'Count 20 Times' daily quest."""
    uid  = str(ctx.author.id)
    user = get_user_quests(uid)
    q    = next(q for q in DAILY_QUESTS if q["id"] == "dq1")
    prog = user["daily_prog"].get("dq1", 0)
    if prog >= q["target"] or "dq1" in user["daily_claimed"]:
        return await ctx.send(f"✅ {ctx.author.mention} Count quest already complete! Use `+claimdaily`.")
    update_quest_progress(uid, "count", 1)
    user = get_user_quests(uid)
    new_prog = user["daily_prog"].get("dq1", 0)
    em = discord.Embed(
        title="🔢 Counted!",
        description=f"{ctx.author.mention} counted! Progress: **{new_prog}/{q['target']}**",
        color=0x00bcd4)
    if new_prog >= q["target"]:
        em.add_field(name="✅ Quest Complete!", value="Use `+claimdaily` to claim your **40k** 🪙!", inline=False)
    await ctx.send(embed=em)


@bot.command(name="quests", aliases=["quest","q"])
async def quests_cmd(ctx):
    """View your daily & special quests."""
    uid  = str(ctx.author.id)
    user = get_user_quests(uid)
    today     = _ist_today()
    week_end  = _ist_saturday()

    em = discord.Embed(
        title="⏱️ Daily Quests",
        description=f"Reset: **12am IST** daily  ·  Today: {today}",
        color=0x00bcd4)

    completed_daily = 0
    for q in DAILY_QUESTS:
        prog    = user["daily_prog"].get(q["id"], 0)
        claimed = q["id"] in user["daily_claimed"]
        done    = prog >= q["target"]
        if done: completed_daily += 1
        bar     = "✅" if claimed else ("🔵" if done else "⬜")
        prog_str = f"{min(prog, q['target'])}/{q['target']}"
        em.add_field(
            name=f"{bar} {q['desc']}",
            value=f"Progress: `{prog_str}` · Reward: **{q['reward']//1000}k** 🪙"
                  + (" · *Claimed!*" if claimed else " · *Use +claimdaily*" if done else ""),
            inline=False)

    bonus_done = completed_daily >= DAILY_BONUS["min_complete"]
    bonus_claimed = user.get("daily_bonus", False)
    em.add_field(
        name=f"{'✅' if bonus_claimed else '🌟'} Complete **{DAILY_BONUS['min_complete']}** Daily Quests",
        value=f"Bonus: **{DAILY_BONUS['reward']//1000}k** 🪙"
              + (" · *Claimed!*" if bonus_claimed else " · *+claimdaily*" if bonus_done else ""),
        inline=False)

    em2 = discord.Embed(
        title="✨ Special Quests",
        description=f"End: **Saturday 11:59pm IST**  ({week_end})",
        color=0x9c27b0)

    completed_special = 0
    for q in SPECIAL_QUESTS:
        prog    = user["special_prog"].get(q["id"], 0)
        claimed = q["id"] in user.get("special_claimed", [])
        done    = prog >= q["target"]
        if done: completed_special += 1
        bar     = "✅" if claimed else ("🔵" if done else "⬜")
        prog_str = f"{min(prog, q['target'])}/{q['target']}"
        em2.add_field(
            name=f"{bar} {q['desc']}",
            value=f"Progress: `{prog_str}` · Reward: **{q['reward']//1000}k** 🪙"
                  + (" · *Claimed!*" if claimed else " · *+claimspecial*" if done else ""),
            inline=False)

    sbonus_done   = completed_special >= SPECIAL_BONUS["min_complete"]
    sbonus_claimed = user.get("special_bonus", False)
    em2.add_field(
        name=f"{'✅' if sbonus_claimed else '🌟'} Complete **All** Special Quests",
        value=f"Bonus: **{SPECIAL_BONUS['reward']//1000}k** 🪙"
              + (" · *Claimed!*" if sbonus_claimed else " · *+claimspecial*" if sbonus_done else ""),
        inline=False)

    await ctx.send(embeds=[em, em2])


@bot.command(name="claimdaily")
async def claim_daily(ctx):
    """Claim all completed daily quest rewards."""
    uid    = str(ctx.author.id)
    user   = get_user_quests(uid)
    b      = get_balance(uid)
    earned = 0
    msgs   = []

    for q in DAILY_QUESTS:
        prog = user["daily_prog"].get(q["id"], 0)
        if prog >= q["target"] and q["id"] not in user["daily_claimed"]:
            earned += q["reward"]
            user["daily_claimed"].append(q["id"])
            msgs.append(f"✅ {q['desc']} — +**{q['reward']//1000}k** 🪙")

    # Bonus
    if len(user["daily_claimed"]) >= DAILY_BONUS["min_complete"] and not user.get("daily_bonus"):
        earned += DAILY_BONUS["reward"]
        user["daily_bonus"] = True
        msgs.append(f"🌟 Bonus (3 quests) — +**{DAILY_BONUS['reward']//1000}k** 🪙")

    if not msgs:
        return await ctx.send("❌ No completed daily quests to claim right now!")

    b["coins"] += earned
    set_balance(uid, b["coins"], b["tickets"])
    data       = load_quests()
    data[uid]  = user
    save_quests(data)

    em = discord.Embed(title="🎉 Daily Quests Claimed!", color=0x00e676)
    em.description = "\n".join(msgs)
    em.add_field(name="Total Earned",  value=f"**{earned:,}** 🪙",        inline=True)
    em.add_field(name="New Balance",   value=f"**{b['coins']:,}** 🪙",    inline=True)
    await ctx.send(embed=em)


@bot.command(name="claimspecial")
async def claim_special(ctx):
    """Claim all completed special quest rewards."""
    uid    = str(ctx.author.id)
    user   = get_user_quests(uid)
    b      = get_balance(uid)
    earned = 0
    msgs   = []

    for q in SPECIAL_QUESTS:
        prog = user["special_prog"].get(q["id"], 0)
        if prog >= q["target"] and q["id"] not in user.get("special_claimed", []):
            earned += q["reward"]
            user.setdefault("special_claimed", []).append(q["id"])
            msgs.append(f"✅ {q['desc']} — +**{q['reward']//1000}k** 🪙")

    # All-complete bonus
    if len(user.get("special_claimed", [])) >= len(SPECIAL_QUESTS) and not user.get("special_bonus"):
        earned += SPECIAL_BONUS["reward"]
        user["special_bonus"] = True
        msgs.append(f"🌟 All Specials Bonus — +**{SPECIAL_BONUS['reward']//1000}k** 🪙")

    if not msgs:
        return await ctx.send("❌ No completed special quests to claim right now!")

    b["coins"] += earned
    set_balance(uid, b["coins"], b["tickets"])
    data      = load_quests()
    data[uid] = user
    save_quests(data)

    em = discord.Embed(title="🎉 Special Quests Claimed!", color=0x9c27b0)
    em.description = "\n".join(msgs)
    em.add_field(name="Total Earned", value=f"**{earned:,}** 🪙",      inline=True)
    em.add_field(name="New Balance",  value=f"**{b['coins']:,}** 🪙",  inline=True)
    await ctx.send(embed=em)



# ═══════════════════════════════════════════════════════════════════════════════
# 🎮  NEXUS ARCADE — MINI GAMES & ENGAGEMENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# 🔮  CRICKET TRIVIA
# ─────────────────────────────────────────────
TRIVIA_QUESTIONS = [
    {"q":"Who holds the record for the highest individual ODI score?","opts":["Rohit Sharma","Martin Guptill","Chris Gayle","Sachin Tendulkar"],"ans":0,"fact":"Rohit Sharma scored 264 vs Sri Lanka in 2014!"},
    {"q":"Which country won the first ever Cricket World Cup (1975)?","opts":["Australia","West Indies","England","India"],"ans":1,"fact":"West Indies beat Australia in the final at Lord's."},
    {"q":"Who was the first bowler to take 800 Test wickets?","opts":["Shane Warne","Glenn McGrath","Muttiah Muralitharan","Anil Kumble"],"ans":2,"fact":"Murali finished with 800 Test wickets — an all-time record!"},
    {"q":"What is the maximum number of overs a bowler can bowl in a T20?","opts":["4","5","3","6"],"ans":0,"fact":"Each bowler is capped at 4 overs in a T20 match."},
    {"q":"Who hit the first ever T20 World Cup six on the last ball to win?","opts":["MS Dhoni","Yuvraj Singh","Darren Sammy","Shahid Afridi"],"ans":0,"fact":"MS Dhoni's six off Joginder Sharma won India the 2007 T20 WC!"},
    {"q":"Which player has the most T20I centuries?","opts":["Rohit Sharma","Babar Azam","Glenn Maxwell","Suryakumar Yadav"],"ans":0,"fact":"Rohit Sharma has the most T20I centuries with 5!"},
    {"q":"Who scored 100 international centuries?","opts":["Ricky Ponting","Brian Lara","Sachin Tendulkar","Virat Kohli"],"ans":2,"fact":"Sachin Tendulkar is the only player with 100 international hundreds."},
    {"q":"Which ground has the highest altitude in Test cricket?","opts":["Dharamshala","Johannesburg","Bogota","Pallekele"],"ans":1,"fact":"Johannesburg's New Wanderers Stadium sits at 1753m above sea level."},
    {"q":"Who holds the record for most sixes in a single T20I innings?","opts":["Chris Gayle","Rohit Sharma","Hazratullah Zazai","Aaron Finch"],"ans":2,"fact":"Zazai hit 16 sixes in a single T20I innings vs Ireland in 2019!"},
    {"q":"What does 'Duckworth-Lewis' method calculate?","opts":["Player ratings","Revised target in rain-affected matches","Bowler economy","Batting average"],"ans":1,"fact":"D/L method sets revised targets when weather interrupts a match."},
    {"q":"Which team chased the highest total in ODI history?","opts":["India","South Africa","England","Australia"],"ans":2,"fact":"England chased 444/3 vs Pakistan at Headingley in 2016!"},
    {"q":"What is a 'hat-trick' in cricket?","opts":["3 sixes in a row","3 wickets in 3 balls","3 boundaries in an over","Scoring 50 in 3 matches"],"ans":1,"fact":"Hat-tricks are extremely rare — even rarer across innings or matches!"},
    {"q":"Who has the most Test runs of all time?","opts":["Ricky Ponting","Jacques Kallis","Sachin Tendulkar","Brian Lara"],"ans":2,"fact":"Sachin Tendulkar has 15,921 Test runs — a record that may never be broken."},
    {"q":"Which bowler has the best figures in a single Test innings?","opts":["Jim Laker","Shane Warne","Anil Kumble","Muttiah Muralitharan"],"ans":0,"fact":"Jim Laker took 10/53 vs Australia at Old Trafford in 1956!"},
    {"q":"What is the 'Ashes' series contested between?","opts":["India & Pakistan","Australia & England","South Africa & Zimbabwe","New Zealand & Australia"],"ans":1,"fact":"The Ashes began in 1882 after a satirical obituary for English cricket."},
]

TRIVIA_REWARD       = 5_000   # coins per correct answer
TRIVIA_STREAK_BONUS = 20_000  # bonus for 3 correct in a row
TRIVIA_COOLDOWN     = 30      # seconds between questions per user
_trivia_cooldowns: dict = {}
_trivia_streaks:   dict = {}

@bot.command(name="trivia", aliases=["cgtrivia","nexustrivia"])
async def trivia(ctx):
    """Answer a cricket trivia question and earn coins!\nCorrect = +5,000 🪙 | 3-in-a-row streak = +20,000 🪙 bonus"""
    uid = str(ctx.author.id)
    now = datetime.utcnow().timestamp()
    last = _trivia_cooldowns.get(uid, 0)
    if now - last < TRIVIA_COOLDOWN:
        left = int(TRIVIA_COOLDOWN - (now - last))
        return await ctx.send(f"⏳ Cooldown! Try again in **{left}s**.", delete_after=5)

    q = random.choice(TRIVIA_QUESTIONS)
    letters = ["🇦","🇧","🇨","🇩"]
    opts_text = "\n".join(f"{letters[i]} {opt}" for i, opt in enumerate(q["opts"]))
    streak = _trivia_streaks.get(uid, 0)
    streak_bar = "🔥" * min(streak, 5) if streak > 0 else ""

    em = discord.Embed(
        title="🏏 Cricket Trivia",
        description=f"**{q['q']}**\n\n{opts_text}",
        color=0x3498db)
    em.set_footer(text=f"You have 20 seconds to answer! {streak_bar} Streak: {streak}")
    msg = await ctx.send(embed=em)

    for emoji in letters[:len(q["opts"])]:
        await msg.add_reaction(emoji)

    def check(reaction, user):
        return (user == ctx.author and str(reaction.emoji) in letters
                and reaction.message.id == msg.id)
    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=20.0, check=check)
        chosen = letters.index(str(reaction.emoji))
        _trivia_cooldowns[uid] = now

        if chosen == q["ans"]:
            streak = _trivia_streaks.get(uid, 0) + 1
            _trivia_streaks[uid] = streak
            earned = TRIVIA_REWARD
            bonus_msg = ""
            if streak > 0 and streak % 3 == 0:
                earned += TRIVIA_STREAK_BONUS
                bonus_msg = f"\n🔥 **{streak}-streak BONUS! +{TRIVIA_STREAK_BONUS:,} 🪙**"
            b = get_balance(uid)
            b["coins"] += earned
            set_balance(uid, b["coins"], b["tickets"])
            result_em = discord.Embed(
                title="✅ Correct!",
                description=f"**{q['fact']}**{bonus_msg}\n\n+**{earned:,}** 🪙  ·  Balance: **{b['coins']:,}** 🪙",
                color=0x00e676)
            result_em.set_footer(text=f"🔥 Streak: {streak}")
        else:
            _trivia_streaks[uid] = 0
            correct = q["opts"][q["ans"]]
            result_em = discord.Embed(
                title="❌ Wrong!",
                description=f"The answer was **{correct}**\n_{q['fact']}_",
                color=0xe74c3c)
            result_em.set_footer(text="Streak reset! Try again in 30s.")
        await msg.edit(embed=result_em)
        try: await msg.clear_reactions()
        except: pass
    except asyncio.TimeoutError:
        _trivia_streaks[uid] = 0
        timeout_em = discord.Embed(title="⏰ Time's up!", description="You didn't answer in time. Streak reset!", color=0x95a5a6)
        await msg.edit(embed=timeout_em)
        try: await msg.clear_reactions()
        except: pass


# ─────────────────────────────────────────────
# 🎯  CRICKET WORDLE — GUESS THE PLAYER
# ─────────────────────────────────────────────
WORDLE_PLAYERS = [
    {"name":"Virat Kohli",    "country":"India",        "role":"BAT","age":35,"caps":250},
    {"name":"Rohit Sharma",   "country":"India",        "role":"BAT","age":37,"caps":245},
    {"name":"Jasprit Bumrah", "country":"India",        "role":"BOWL","age":30,"caps":160},
    {"name":"MS Dhoni",       "country":"India",        "role":"WK","age":42,"caps":350},
    {"name":"Babar Azam",     "country":"Pakistan",     "role":"BAT","age":29,"caps":200},
    {"name":"Shaheen Afridi", "country":"Pakistan",     "role":"BOWL","age":24,"caps":110},
    {"name":"Steve Smith",    "country":"Australia",    "role":"BAT","age":35,"caps":200},
    {"name":"Pat Cummins",    "country":"Australia",    "role":"BOWL","age":31,"caps":150},
    {"name":"Joe Root",       "country":"England",      "role":"BAT","age":33,"caps":240},
    {"name":"Ben Stokes",     "country":"England",      "role":"ALR","age":33,"caps":200},
    {"name":"Kane Williamson","country":"New Zealand",  "role":"BAT","age":34,"caps":230},
    {"name":"Trent Boult",    "country":"New Zealand",  "role":"BOWL","age":35,"caps":180},
    {"name":"Rashid Khan",    "country":"Afghanistan",  "role":"BOWL","age":26,"caps":170},
    {"name":"Kagiso Rabada",  "country":"South Africa", "role":"BOWL","age":29,"caps":140},
    {"name":"David Warner",   "country":"Australia",    "role":"BAT","age":38,"caps":240},
    {"name":"Hardik Pandya",  "country":"India",        "role":"ALR","age":31,"caps":150},
    {"name":"Suryakumar Yadav","country":"India",       "role":"BAT","age":34,"caps":80},
    {"name":"Glenn Maxwell",  "country":"Australia",    "role":"ALR","age":36,"caps":180},
    {"name":"Andre Russell",  "country":"West Indies",  "role":"ALR","age":36,"caps":80},
    {"name":"Kieron Pollard", "country":"West Indies",  "role":"ALR","age":37,"caps":220},
]
WORDLE_FILE = "wordle_state.json"

def _get_daily_wordle_player():
    import math
    day_num = int(datetime.utcnow().timestamp() // 86400)
    return WORDLE_PLAYERS[day_num % len(WORDLE_PLAYERS)]

def _load_wordle():
    if not os.path.exists(WORDLE_FILE): return {}
    with open(WORDLE_FILE) as f: return json.load(f)

def _save_wordle(data):
    with open(WORDLE_FILE,"w") as f: json.dump(data,f,indent=2)

def _wordle_hint(guess_p, target_p):
    """Return a hint string comparing guess to target player."""
    hints = []
    g_role = guess_p.get("role","?"); t_role = target_p.get("role","?")
    hints.append(("Role",    g_role,                  "✅" if g_role==t_role else "❌"))
    hints.append(("Country", guess_p.get("country","?"), "✅" if guess_p.get("country")==target_p.get("country") else "❌"))
    g_age = guess_p.get("age",0); t_age = target_p.get("age",0)
    age_icon = "✅" if g_age==t_age else ("⬆️" if g_age<t_age else "⬇️")
    hints.append(("Age", str(g_age), age_icon))
    g_caps = guess_p.get("caps",0); t_caps = target_p.get("caps",0)
    cap_icon = "✅" if abs(g_caps-t_caps)<20 else ("⬆️" if g_caps<t_caps else "⬇️")
    hints.append(("Caps~", str(g_caps), cap_icon))
    return hints

@bot.command(name="wordle", aliases=["crickle","playerwordle"])
async def cricket_wordle(ctx, *, guess: str = None):
    """Guess the mystery cricket player! New player every day.\nUsage: +wordle Virat Kohli\n🟢 = correct | ⬆️/⬇️ = higher/lower | ❌ = wrong"""
    uid      = str(ctx.author.id)
    target   = _get_daily_wordle_player()
    today    = datetime.utcnow().strftime("%Y-%m-%d")
    wdata    = _load_wordle()
    ustate   = wdata.setdefault(uid, {})

    if ustate.get("date") != today:
        ustate["date"]    = today
        ustate["guesses"] = []
        ustate["won"]     = False

    MAX_GUESSES = 6

    # Show status if no guess
    if not guess:
        guesses_left = MAX_GUESSES - len(ustate["guesses"])
        em = discord.Embed(
            title="🏏 Cricket Wordle — Guess the Player!",
            description=(
                f"Guess today's mystery cricket player!\n"
                f"**{MAX_GUESSES - len(ustate['guesses'])}** guess(es) remaining.\n\n"
                f"**Usage:** `+wordle Virat Kohli`\n"
                f"**Hints:** ✅ = correct  ⬆️/⬇️ = higher/lower  ❌ = wrong\n\n"
                f"**Guess History:**\n" +
                ("\n".join(f"• **{g['name']}**" for g in ustate["guesses"]) or "_No guesses yet_")
            ),
            color=0x9b59b6)
        em.set_footer(text=f"New player resets daily at midnight UTC")
        return await ctx.send(embed=em)

    if ustate["won"]:
        return await ctx.send(f"✅ You already got today's player! Come back tomorrow.")
    if len(ustate["guesses"]) >= MAX_GUESSES:
        return await ctx.send(f"❌ No more guesses today! The answer was **{target['name']}**.")

    # Find guess player
    guess_p = None
    gl = guess.strip().lower()
    for p in WORDLE_PLAYERS:
        if p["name"].lower() == gl or gl in p["name"].lower():
            guess_p = p; break

    if not guess_p:
        # Also check ALL_PLAYERS
        fn, _ = find_player(guess)
        if fn:
            guess_p = {"name":fn,"country":"Unknown","role":"BAT","age":30,"caps":100}
        else:
            return await ctx.send(f"❓ **{guess}** not in the player list. Try a well-known player!")

    hints = _wordle_hint(guess_p, target)
    hint_lines = "\n".join(f"{icon} **{label}:** {val}" for label, val, icon in hints)
    correct = guess_p["name"].lower() == target["name"].lower()

    ustate["guesses"].append({"name": guess_p["name"]})

    if correct:
        ustate["won"] = True
        earned = (MAX_GUESSES - len(ustate["guesses"]) + 1) * 10_000
        b = get_balance(uid); b["coins"] += earned
        set_balance(uid, b["coins"], b["tickets"])
        em = discord.Embed(
            title=f"🎉 Correct! The player was **{target['name']}**!",
            description=f"{hint_lines}\n\n+**{earned:,}** 🪙 earned!",
            color=0x00e676)
        em.set_footer(text=f"Guessed in {len(ustate['guesses'])}/{MAX_GUESSES}")
    else:
        left = MAX_GUESSES - len(ustate["guesses"])
        color = 0xf39c12 if left > 2 else 0xe74c3c
        em = discord.Embed(
            title=f"❌ Not {guess_p['name']}! ({left} guesses left)",
            description=hint_lines,
            color=color)
        if left == 0:
            em.add_field(name="💀 Game Over",
                value=f"The answer was **{target['name']}**! Better luck tomorrow.", inline=False)

    _save_wordle(wdata)
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
# 🎲  COIN FLIP BET
# ─────────────────────────────────────────────
_flip_cooldowns: dict = {}

@bot.command(name="flip", aliases=["coinflip","bet"])
async def coin_flip(ctx, amount: str = None, side: str = None):
    """Bet coins on a coin flip! Usage: +flip 5000 heads/tails\nWin = double your bet | Lose = lose bet amount"""
    uid = str(ctx.author.id)
    now = datetime.utcnow().timestamp()
    if now - _flip_cooldowns.get(uid, 0) < 10:
        return await ctx.send("⏳ Cooldown! Wait 10 seconds between flips.", delete_after=5)

    if not amount or not side:
        return await ctx.send(
            "**Usage:** `+flip <amount> <heads/tails>`\n"
            "Example: `+flip 10000 heads`\n💡 Win = 2x your bet!")

    b = get_balance(uid)
    try:
        bet = int(amount.replace(",","").replace("k","000").replace("K","000"))
    except ValueError:
        return await ctx.send("❌ Invalid amount! Use a number like `5000` or `5k`.")

    if bet <= 0: return await ctx.send("❌ Bet must be positive!")
    if bet > b["coins"]:
        return await ctx.send(f"❌ Not enough coins! You have **{b['coins']:,}** 🪙")
    if bet > 500_000:
        return await ctx.send("❌ Max bet is **500,000** 🪙 per flip!")

    side = side.lower()
    if side not in ("heads","tails","h","t"):
        return await ctx.send("❌ Choose **heads** or **tails**!")
    side_full = "heads" if side in ("heads","h") else "tails"

    _flip_cooldowns[uid] = now

    # Animated flip message
    flip_em = discord.Embed(title="🪙 Flipping...", description="The coin is in the air!", color=0xf1c40f)
    msg = await ctx.send(embed=flip_em)
    await asyncio.sleep(1.5)

    result = random.choice(["heads","tails"])
    won = result == side_full

    if won:
        b["coins"] += bet
        set_balance(uid, b["coins"], b["tickets"])
        em = discord.Embed(
            title=f"{'👑 HEADS' if result=='heads' else '🦅 TAILS'} — You Won!",
            description=f"You bet **{side_full}** and won **{bet:,}** 🪙!\nBalance: **{b['coins']:,}** 🪙",
            color=0x00e676)
    else:
        b["coins"] -= bet
        set_balance(uid, b["coins"], b["tickets"])
        em = discord.Embed(
            title=f"{'👑 HEADS' if result=='heads' else '🦅 TAILS'} — You Lost!",
            description=f"You bet **{side_full}** but got **{result}**. Lost **{bet:,}** 🪙.\nBalance: **{b['coins']:,}** 🪙",
            color=0xe74c3c)
    await msg.edit(embed=em)

@bot.command(name="leaderboard", aliases=["lb","richest","top"])
async def leaderboard(ctx):
    """See the top 10 richest players on the server!"""
    balance_file = "balances.json"
    if not os.path.exists(balance_file):
        return await ctx.send("❌ No balance data found!")

    with open(balance_file) as f:
        all_bals = json.load(f)

    # Sort by coins
    sorted_users = sorted(all_bals.items(), key=lambda x: x[1].get("coins",0), reverse=True)[:10]

    em = discord.Embed(title="🏆 Richest Players — Sports Nexus", color=0xf1c40f)
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    lines = []
    for i, (uid, bal) in enumerate(sorted_users):
        try:
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"User#{uid[-4:]}"
        except Exception:
            name = f"User#{uid[-4:]}"
        coins   = bal.get("coins", 0)
        tickets = bal.get("tickets", 0)
        lines.append(f"{medals[i]} **{name}** — {coins:,} 🪙  ·  {tickets} 🎟️")

    em.description = "\n".join(lines) if lines else "No data yet!"
    em.set_footer(text="Use +bal to check your own balance!")
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
# 🎁  DAILY REWARD (free coins every 24h)
# ─────────────────────────────────────────────
DAILY_REWARD_FILE = "daily_rewards.json"
DAILY_AMOUNTS = [10_000, 15_000, 20_000, 25_000, 30_000, 40_000, 50_000]  # day 1-7

def _load_daily_rewards():
    if not os.path.exists(DAILY_REWARD_FILE): return {}
    with open(DAILY_REWARD_FILE) as f: return json.load(f)

def _save_daily_rewards(data):
    with open(DAILY_REWARD_FILE,"w") as f: json.dump(data,f,indent=2)

@bot.command(name="daily", aliases=["claim","reward"])
async def daily_reward(ctx):
    """Claim your free daily coins! Streak bonuses for consecutive days!\nDay 7 streak = 50,000 🪙!"""
    uid  = str(ctx.author.id)
    now  = datetime.utcnow()
    data = _load_daily_rewards()
    user = data.get(uid, {"streak":0,"last":None})

    last_str = user.get("last")
    streak   = user.get("streak", 0)

    if last_str:
        last_dt = datetime.fromisoformat(last_str)
        hours_since = (now - last_dt).total_seconds() / 3600
        if hours_since < 24:
            next_claim = last_dt + timedelta(hours=24)
            left = next_claim - now
            h, m = divmod(int(left.total_seconds())//60, 60)
            return await ctx.send(
                f"⏰ Already claimed today! Come back in **{h}h {m}m**.\n"
                f"🔥 Current streak: **{streak}** days")
        elif hours_since > 48:
            streak = 0  # streak broken

    streak = min(streak + 1, 7)
    reward = DAILY_AMOUNTS[streak - 1]

    b = get_balance(uid)
    b["coins"] += reward
    set_balance(uid, b["coins"], b["tickets"])

    user["streak"] = streak
    user["last"]   = now.isoformat()
    data[uid]      = user
    _save_daily_rewards(data)

    # Build streak bar
    streak_bar = "".join("🟡" if i < streak else "⚫" for i in range(7))
    next_reward = DAILY_AMOUNTS[min(streak, 6)]

    em = discord.Embed(
        title="🎁 Daily Reward Claimed!",
        description=f"+**{reward:,}** 🪙  ·  Balance: **{b['coins']:,}** 🪙",
        color=0xf1c40f)
    em.add_field(name="🔥 Streak", value=f"**{streak}/7** days", inline=True)
    em.add_field(name="📅 Progress", value=streak_bar, inline=True)
    em.add_field(name="Tomorrow", value=f"+{next_reward:,} 🪙" if streak < 7 else "MAX reward! 🎉", inline=True)
    em.set_footer(text="Come back every day to build your streak! Day 7 = 50k 🪙")
    em.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
# 🎰  SPIN THE WHEEL (Slot Machine)
# ─────────────────────────────────────────────
SPIN_COST    = 2_000
SPIN_SYMBOLS = ["🏏","⭐","💎","🔥","🏆","🎯","💰","🍀"]
SPIN_PAYOUTS = {
    "💎💎💎": 200_000,
    "🏆🏆🏆": 100_000,
    "💰💰💰":  80_000,
    "🍀🍀🍀":  60_000,
    "🏏🏏🏏":  50_000,
    "⭐⭐⭐":   40_000,
    "🔥🔥🔥":  30_000,
    "🎯🎯🎯":  20_000,
}
_spin_cooldowns: dict = {}

@bot.command(name="spin", aliases=["slot","slots"])
async def spin_wheel(ctx):
    """Spin the slot machine! Costs 2,000 🪙 per spin.\nMatch 3 symbols to win big! 💎💎💎 = 200,000 🪙!"""
    uid = str(ctx.author.id)
    now = datetime.utcnow().timestamp()
    if now - _spin_cooldowns.get(uid, 0) < 8:
        return await ctx.send("⏳ Cooldown! Wait before spinning again.", delete_after=4)

    b = get_balance(uid)
    if b["coins"] < SPIN_COST:
        return await ctx.send(f"❌ Need **{SPIN_COST:,}** 🪙 to spin! You have **{b['coins']:,}** 🪙")

    b["coins"] -= SPIN_COST
    set_balance(uid, b["coins"], b["tickets"])
    _spin_cooldowns[uid] = now

    # Spin animation
    spin_em = discord.Embed(title="🎰 Spinning...", description="🎰 | ? ? ? | 🎰", color=0x9b59b6)
    msg = await ctx.send(embed=spin_em)
    await asyncio.sleep(1)

    # Weighted random — jackpots rare
    weights = [8,12,3,10,4,8,6,6]
    result = random.choices(SPIN_SYMBOLS, weights=weights, k=3)
    result_str = " ".join(result)
    combo_key  = "".join(result)

    payout = SPIN_PAYOUTS.get(combo_key, 0)
    # Two of a kind = small consolation
    if payout == 0:
        counts = {s: result.count(s) for s in set(result)}
        if max(counts.values()) >= 2:
            payout = 5_000

    if payout > 0:
        b = get_balance(uid)
        b["coins"] += payout
        set_balance(uid, b["coins"], b["tickets"])
        net = payout - SPIN_COST
        if payout >= 50_000:
            title = f"🎉 JACKPOT! {result_str}"
            color = 0xf1c40f
        else:
            title = f"✨ Winner! {result_str}"
            color = 0x00e676
        em = discord.Embed(title=title,
            description=f"Won **{payout:,}** 🪙 (net +{net:,})!\nBalance: **{b['coins']:,}** 🪙",
            color=color)
    else:
        em = discord.Embed(
            title=f"😔 No match — {result_str}",
            description=f"Lost **{SPIN_COST:,}** 🪙\nBalance: **{b['coins']:,}** 🪙",
            color=0x95a5a6)
        em.set_footer(text="Try again! 💎💎💎 = 200,000 🪙")
    await msg.edit(embed=em)

# ─────────────────────────────────────────────
# 📊  PLAYER DUEL — HEAD TO HEAD
# ─────────────────────────────────────────────
@bot.command(name="duel", aliases=["h2h","versus","vs"])
async def player_duel(ctx, *, players: str = None):
    """Compare two players head-to-head! Usage: +duel Virat Kohli vs Babar Azam"""
    if not players or " vs " not in players.lower():
        return await ctx.send("**Usage:** `+duel Player1 vs Player2`\nExample: `+duel Virat Kohli vs Babar Azam`")

    parts = players.lower().split(" vs ", 1)
    p1_q, p2_q = parts[0].strip(), parts[1].strip()

    # Check addcard DB first, then ALL_PLAYERS
    cards_db = load_cards()
    def find_any(query):
        ql = query.lower()
        for c in cards_db.values():
            if ql == c["name"].lower() or ql in c["name"].lower():
                return {"name":c["name"],"bat":c.get("bat",70),"bowl":c.get("bowl",60),
                        "ovr":c.get("ovr",75),"style":c.get("style","BAT"),
                        "country":c.get("country","Unknown"),"source":"card"}
        fn, pdata = find_player(query)
        if fn and pdata:
            return {"name":fn,"bat":pdata.get("bat",70),"bowl":pdata.get("bowl",60),
                    "ovr":pdata.get("ovr",75),"style":pdata.get("role","BAT"),
                    "country":pdata.get("country","Unknown"),"source":"db"}
        return None

    p1 = find_any(p1_q)
    p2 = find_any(p2_q)

    if not p1: return await ctx.send(f"❌ **{p1_q.title()}** not found!")
    if not p2: return await ctx.send(f"❌ **{p2_q.title()}** not found!")

    def stat_bar(val, max_val=99, length=10):
        filled = round(val / max_val * length)
        return "█" * filled + "░" * (length - filled)

    def cmp(a, b):
        if a > b: return "🟢", "🔴"
        if a < b: return "🔴", "🟢"
        return "🟡","🟡"

    bat_c1, bat_c2   = cmp(p1["bat"],  p2["bat"])
    bowl_c1, bowl_c2 = cmp(p1["bowl"], p2["bowl"])
    ovr_c1, ovr_c2   = cmp(p1["ovr"],  p2["ovr"])

    flag1 = COUNTRY_FLAGS.get(p1["country"],"🌍")
    flag2 = COUNTRY_FLAGS.get(p2["country"],"🌍")

    em = discord.Embed(title=f"⚔️ {p1['name']} vs {p2['name']}", color=0xe74c3c)
    em.add_field(name=f"{flag1} {p1['name']}", value=(
        f"{bat_c1} BAT  `{p1['bat']:>2}` `{stat_bar(p1['bat'])}`\n"
        f"{bowl_c1} BOWL `{p1['bowl']:>2}` `{stat_bar(p1['bowl'])}`\n"
        f"{ovr_c1} OVR  `{p1['ovr']:>2}` `{stat_bar(p1['ovr'])}`"
    ), inline=True)
    em.add_field(name="\u200b", value="**BAT**\n**BOWL**\n**OVR**", inline=True)
    em.add_field(name=f"{flag2} {p2['name']}", value=(
        f"`{stat_bar(p2['bat'])}` `{p2['bat']:>2}` {bat_c2}\n"
        f"`{stat_bar(p2['bowl'])}` `{p2['bowl']:>2}` {bowl_c2}\n"
        f"`{stat_bar(p2['ovr'])}` `{p2['ovr']:>2}` {ovr_c2}"
    ), inline=True)

    p1_score = p1["bat"] + p1["bowl"] + p1["ovr"]
    p2_score = p2["bat"] + p2["bowl"] + p2["ovr"]
    if p1_score > p2_score:
        verdict = f"🏆 **{p1['name']}** wins the comparison!"
    elif p2_score > p1_score:
        verdict = f"🏆 **{p2['name']}** wins the comparison!"
    else:
        verdict = "🤝 It's a **DRAW**!"
    em.add_field(name="📊 Verdict", value=verdict, inline=False)
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
# 🤖  +NEXUSHELP  (fancy help menu)
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# ERROR HANDLING
# ─────────────────────────────────────────────
@bot.event
async def on_message(message):
    """Track message count quests."""
    if message.author.bot:
        await bot.process_commands(message)
        return
    uid = str(message.author.id)
    # Track message count for quests (silently)
    try:
        update_quest_progress(uid, "messages", 1)
    except Exception:
        pass
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing argument! Use `+nexushelp` for help.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument!")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ Error: {str(error)}")

if __name__ == '__main__':
    bot.run(os.getenv('DISCORD_TOKEN'))