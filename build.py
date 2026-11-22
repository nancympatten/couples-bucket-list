import os
import re
import csv
import json
import html
import math
import shutil
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import quote

BASE_URL = os.environ.get("BASE_URL", "https://couples-bucket-list.velvetgrid.workers.dev").rstrip("/")
SITE_NAME = "Couples Bucket List"
NICHE_TOPIC = "Interactive Couples Bucket Lists, Romantic Challenges & Date Night Checklists"
CONTACT_EMAIL = "nancympatten@gmail.com"
AFFILIATE_URL = "#affiliate-link"
AFFILIATE_CTA_TEXT = "Explore Live Interactive Experiences & Shows for Couples"
CURRENT_YEAR = datetime.utcnow().year

# ============================================================
# CONFIGURATION
# ============================================================

DATA_FILE = "data.csv"
OUTPUT_DIR = "dist"
ITEMS_PER_PAGE = 24
RELATED_ITEMS = 8
SITEMAP_LIMIT = 45000

EXPECTED_COLUMNS = [
    "slug",
    "title",
    "category",
    "subcategory",
    "target_keyword",
    "checklist_items",
    "planning_tips",
    "description",
    "tags",
    "faq_q1",
    "faq_a1",
    "faq_q2",
    "faq_a2",
    "upload_date",
]

REQUIRED_COLUMNS = EXPECTED_COLUMNS

# ============================================================
# UTILITIES
# ============================================================

def esc(value):
    return html.escape(str(value or ""), quote=True)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slugify(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "uncategorized"


def unique_slug(value, existing):
    base = slugify(value)
    candidate = base
    number = 2

    while candidate in existing:
        candidate = f"{base}-{number}"
        number += 1

    existing.add(candidate)
    return candidate


def safe_json(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def make_url(path=""):
    path = str(path).lstrip("/")
    return f"{BASE_URL}/{path}" if path else BASE_URL + "/"


def write_file(path, content):
    os.makedirs(os.path.dirname(path) or OUTPUT_DIR, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(content)


def parse_date(value):
    value = clean_text(value)

    if not value:
        return datetime(CURRENT_YEAR, 1, 1)

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except ValueError:
        return datetime(CURRENT_YEAR, 1, 1)


def parse_tags(value):
    if not value:
        return []

    parts = re.split(r"[,;|]", str(value))

    result = []
    seen = set()

    for part in parts:
        tag = clean_text(part)

        if tag and tag.lower() not in seen:
            result.append(tag)
            seen.add(tag.lower())

    return result


def parse_checklist(value):
    items = [
        clean_text(item)
        for item in str(value or "").split("|")
    ]

    return [item for item in items if item]


def truncate(value, length=160):
    value = clean_text(value)

    if len(value) <= length:
        return value

    return value[:length - 3].rsplit(" ", 1)[0] + "..."


def safe_filename(value):
    return slugify(value)


def format_date(value):
    return value.strftime("%B %d, %Y")


def get_description(row):
    return truncate(
        row["description"] or row["target_keyword"] or row["title"],
        160
    )


def normalize_row(row):
    normalized = {}

    for column in EXPECTED_COLUMNS:
        normalized[column] = clean_text(row.get(column, ""))

    normalized["slug"] = slugify(normalized["slug"] or normalized["title"])

    if not normalized["title"]:
        normalized["title"] = normalized["slug"].replace("-", " ").title()

    if not normalized["category"]:
        normalized["category"] = "Couples Bucket Lists"

    if not normalized["subcategory"]:
        normalized["subcategory"] = normalized["category"]

    if not normalized["target_keyword"]:
        normalized["target_keyword"] = normalized["title"]

    if not normalized["description"]:
        normalized["description"] = (
            f"Discover {normalized['title']}, an interactive couples "
            "bucket list filled with romantic challenges, memorable "
            "experiences, and ideas to enjoy together."
        )

    if not normalized["checklist_items"]:
        normalized["checklist_items"] = (
            "Plan a surprise date|Cook a meal together|"
            "Watch the sunset|Take a weekend adventure|"
            "Create a shared playlist|Explore somewhere new|"
            "Have a technology-free evening|"
            "Write appreciation notes|Try a new activity|"
            "Plan your next dream experience"
        )

    normalized["_items"] = parse_checklist(normalized["checklist_items"])
    normalized["_tags"] = parse_tags(normalized["tags"])
    normalized["_date"] = parse_date(normalized["upload_date"])

    return normalized


# ============================================================
# CSV LOADING
# ============================================================

def load_data():
    if not os.path.isfile(DATA_FILE):
        raise FileNotFoundError(
            f"Missing {DATA_FILE}. Create data.csv using the required "
            "Couples Bucket List CSV schema."
        )

    rows = []

    with open(DATA_FILE, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("data.csv is empty or has no header.")

        missing = [
            column for column in REQUIRED_COLUMNS
            if column not in reader.fieldnames
        ]

        if missing:
            raise ValueError(
                "Missing required CSV columns: " + ", ".join(missing)
            )

        used_slugs = set()

        for line_number, raw_row in enumerate(reader, start=2):
            if not any(clean_text(v) for v in raw_row.values()):
                continue

            row = normalize_row(raw_row)

            original_slug = row["slug"]
            row["slug"] = unique_slug(original_slug, used_slugs)

            if len(row["_items"]) != 10:
                print(
                    f"WARNING: CSV row {line_number} has "
                    f"{len(row['_items'])} checklist items instead of 10."
                )

            if len(row["_items"]) < 2:
                raise ValueError(
                    f"CSV row {line_number} must contain at least "
                    "two checklist items."
                )

            rows.append(row)

    if not rows:
        raise ValueError("No usable bucket lists found in data.csv.")

    return rows


# ============================================================
# GLOBAL STYLES
# ============================================================

CSS = r"""
:root {
    color-scheme: dark;
    --bg: #09080d;
    --surface: #15121e;
    --surface2: #1d1828;
    --surface3: #241d30;
    --gold: #f59e0b;
    --rose: #ec4899;
    --text: #f7f2fa;
    --muted: #a9a0b6;
    --border: rgba(255,255,255,.09);
    --success: #34d399;
    --radius: 18px;
    --max: 1160px;
}

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.7;
}

a {
    color: var(--gold);
    text-decoration: none;
}

a:hover {
    color: var(--rose);
}

button, input {
    font: inherit;
}

button {
    cursor: pointer;
}

.container {
    width: min(100% - 36px, var(--max));
    margin-inline: auto;
}

.site-header {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(9,8,13,.94);
    backdrop-filter: blur(18px);
    border-bottom: 1px solid var(--border);
}

.nav {
    min-height: 72px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
}

.logo {
    color: var(--text);
    font-weight: 900;
    font-size: 19px;
    letter-spacing: -.7px;
}

.logo span {
    color: var(--gold);
}

.nav-links {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    font-size: 13px;
}

.nav-links a {
    color: var(--muted);
}

.hero {
    padding: 76px 0 54px;
    text-align: center;
    background:
        radial-gradient(ellipse at 50% 0%, rgba(236,72,153,.13), transparent 60%),
        radial-gradient(ellipse at 10% 30%, rgba(245,158,11,.08), transparent 50%);
}

.eyebrow {
    color: var(--gold);
    font-size: 12px;
    text-transform: uppercase;
    font-weight: 900;
    letter-spacing: 2px;
}

h1, h2, h3 {
    line-height: 1.2;
    letter-spacing: -.7px;
}

h1 {
    font-size: clamp(34px, 6vw, 58px);
    margin: 16px 0;
}

h2 {
    font-size: clamp(23px, 4vw, 32px);
}

h3 {
    font-size: 19px;
}

.lead {
    color: var(--muted);
    max-width: 760px;
    margin: 0 auto 26px;
}

.search-box {
    max-width: 650px;
    margin: 28px auto 0;
}

.search-box input {
    width: 100%;
    padding: 17px 20px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--surface);
    color: var(--text);
    outline: none;
}

.search-box input:focus,
.name-input:focus {
    border-color: var(--gold);
}

.section {
    padding: 48px 0;
}

.section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 23px;
}

.section-heading h2 {
    margin: 0;
}

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr));
    gap: 17px;
}

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px;
    transition: transform .2s, border-color .2s;
}

.card:hover {
    transform: translateY(-3px);
    border-color: rgba(245,158,11,.4);
}

.card h3 {
    margin: 8px 0;
}

.card h3 a {
    color: var(--text);
}

.card p {
    color: var(--muted);
    font-size: 14px;
}

.card-meta {
    color: var(--gold);
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 800;
    letter-spacing: 1px;
}

.count {
    display: inline-block;
    padding: 4px 10px;
    background: var(--surface3);
    color: var(--gold);
    border-radius: 30px;
    font-size: 12px;
}

.pills, .tag-cloud {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}

.pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 13px;
    border: 1px solid var(--border);
    border-radius: 30px;
    background: var(--surface);
    color: var(--muted);
    font-size: 13px;
}

.pill:hover {
    border-color: var(--gold);
    color: var(--gold);
}

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 12px 18px;
    border: 0;
    border-radius: 11px;
    background: linear-gradient(135deg, #f59e0b, #ec4899);
    color: #170d16;
    font-weight: 900;
    font-size: 13px;
    text-align: center;
    transition: opacity .2s;
}

.btn:hover {
    color: #170d16;
    opacity: .88;
}

.btn-secondary {
    background: var(--surface3);
    border: 1px solid var(--border);
    color: var(--text);
}

.btn-secondary:hover {
    color: var(--gold);
}

.btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}

.breadcrumb {
    padding: 20px 0;
    color: var(--muted);
    font-size: 13px;
}

.breadcrumb a {
    color: var(--gold);
}

.detail-hero {
    padding: 40px 0 32px;
}

.detail-hero h1 {
    font-size: clamp(30px, 5vw, 48px);
}

.edition-badge {
    display: inline-block;
    margin-top: 10px;
    padding: 8px 13px;
    background: rgba(245,158,11,.12);
    border: 1px solid rgba(245,158,11,.3);
    color: var(--gold);
    border-radius: 30px;
    font-size: 12px;
    font-weight: 800;
}

.studio {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 22px;
    padding: clamp(18px, 4vw, 32px);
}

.personalizer {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin: 20px 0;
}

.name-input {
    width: 100%;
    padding: 13px;
    margin-top: 7px;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 10px;
    outline: none;
}

.progress-track {
    height: 12px;
    background: var(--surface3);
    border-radius: 20px;
    overflow: hidden;
    margin: 15px 0 10px;
}

.progress-fill {
    height: 100%;
    width: 0;
    background: linear-gradient(90deg, var(--gold), var(--rose));
    transition: width .3s;
    border-radius: 20px;
}

.progress-label {
    color: var(--gold);
    font-weight: 800;
    font-size: 14px;
}

.checklist {
    list-style: none;
    padding: 0;
    margin: 22px 0;
    display: grid;
    gap: 10px;
}

.checklist li {
    padding: 15px;
    display: flex;
    gap: 12px;
    align-items: flex-start;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 12px;
}

.checklist input {
    width: 19px;
    height: 19px;
    margin-top: 4px;
    accent-color: var(--gold);
    flex-shrink: 0;
}

.checklist label {
    flex: 1;
    cursor: pointer;
}

.checklist li.completed label {
    text-decoration: line-through;
    color: var(--muted);
}

.random-result {
    margin-top: 15px;
    padding: 17px;
    border-radius: 12px;
    background: var(--surface3);
    color: var(--gold);
    display: none;
}

.tips-card {
    margin-top: 22px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
}

.tips-card summary {
    cursor: pointer;
    padding: 19px;
    color: var(--gold);
    font-weight: 800;
}

.tips-content {
    padding: 0 20px 20px;
    color: var(--muted);
    white-space: pre-line;
}

.affiliate-card {
    margin: 24px 0;
    padding: 28px;
    text-align: center;
    border: 1px solid rgba(236,72,153,.3);
    border-radius: 19px;
    background:
        radial-gradient(ellipse at top, rgba(236,72,153,.14), transparent 70%),
        var(--surface);
}

.affiliate-card h2 {
    font-size: 24px;
}

.affiliate-card p {
    color: var(--muted);
}

.faq-item {
    padding: 18px 0;
    border-bottom: 1px solid var(--border);
}

.faq-item h3 {
    font-size: 16px;
}

.faq-item p {
    color: var(--muted);
}

.pagination {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 10px;
    margin: 35px 0;
}

.pagination a, .pagination span {
    padding: 9px 15px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 9px;
}

.site-footer {
    padding: 45px 0 30px;
    border-top: 1px solid var(--border);
    background: #0c0a11;
}

.footer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 25px;
}

.site-footer p, .site-footer a {
    color: var(--muted);
    font-size: 13px;
}

.site-footer a:hover {
    color: var(--gold);
}

.empty-state {
    display: none;
    padding: 30px;
    text-align: center;
    color: var(--muted);
}

.age-overlay {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: none;
    place-items: center;
    padding: 20px;
    background: rgba(0,0,0,.92);
    backdrop-filter: blur(12px);
}

.age-dialog {
    width: min(100%, 440px);
    padding: 32px;
    text-align: center;
    background: var(--surface);
    border: 1px solid rgba(245,158,11,.4);
    border-radius: 22px;
}

.age-dialog h2 {
    color: var(--gold);
}

.age-dialog p {
    color: var(--muted);
    font-size: 14px;
}

.hidden {
    display: none !important;
}

@media(max-width:600px) {
    .nav {
        align-items: flex-start;
        flex-direction: column;
        padding: 14px 0;
    }

    .nav-links {
        gap: 13px;
    }

    .hero {
        padding: 50px 0 35px;
    }

    .btn-group .btn {
        width: 100%;
    }
}
"""

# ============================================================
# GLOBAL JAVASCRIPT
# ============================================================

GLOBAL_JS = r"""
(function () {
    "use strict";

    function updateLiveYear() {
        var year = new Date().getFullYear();

        document.querySelectorAll(".live-year").forEach(function (el) {
            el.textContent = year;
        });

        document.querySelectorAll(".edition-badge").forEach(function (el) {
            var month = new Intl.DateTimeFormat("en", {
                month: "long"
            }).format(new Date());

            el.textContent =
                "Updated Bucket List Edition \u2022 " +
                month + " " + year;
        });
    }

    function initializeAgeVerification() {
        var key = "couples_bucket_list_age_verified_v1";
        var overlay = document.getElementById("age-overlay");

        if (!overlay) return;

        if (localStorage.getItem(key) === "yes") return;

        overlay.style.display = "grid";

        var accept = document.getElementById("age-accept");
        var decline = document.getElementById("age-decline");

        if (accept) {
            accept.addEventListener("click", function () {
                localStorage.setItem(key, "yes");
                overlay.style.display = "none";
            });
        }

        if (decline) {
            decline.addEventListener("click", function () {
                document.body.innerHTML =
                    '<main style="padding:60px;text-align:center;' +
                    'font-family:sans-serif;color:white;background:#09080d;' +
                    'min-height:100vh"><h1>Access Restricted</h1>' +
                    '<p>You must be at least 18 years old to access this site.</p>' +
                    '</main>';
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        updateLiveYear();
        initializeAgeVerification();
    });

    window.addEventListener("pageshow", updateLiveYear);
})();
"""

# ============================================================
# HTML COMPONENTS
# ============================================================

def metadata(title, description, canonical, image=None):
    title = esc(title)
    description = esc(description)
    canonical = esc(canonical)
    image = esc(image or make_url(""))

    return f"""
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="rating" content="RTA-5042-1996-1400-1577-RTA" />
<meta name="google-site-verification" content="Ee2L9A2G2nVVNtBt7HiplcBJf1nSen-Rcz4sNqLuAdc" />
<meta name="msvalidate.01" content="4573069C62AEC27DA4F08DC57760BAD4" />
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{image}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="theme-color" content="#09080d">
"""

def header():
    return """
<header class="site-header">
    <div class="container nav">
        <a class="logo" href="/">COUPLES <span>BUCKET LIST</span></a>
        <nav class="nav-links" aria-label="Main navigation">
            <a href="/">Home</a>
            <a href="/#categories">Categories</a>
            <a href="/#newest">Newest Lists</a>
            <a href="/#topics">Topics</a>
        </nav>
    </div>
</header>
"""

def age_modal():
    return """
<div class="age-overlay" id="age-overlay" role="dialog"
     aria-modal="true" aria-labelledby="age-title">
    <div class="age-dialog">
        <div class="eyebrow">Welcome to Couples Bucket List</div>
        <h2 id="age-title">Are you 18 or older?</h2>
        <p>
            This website provides romantic relationship ideas and
            interactive experiences intended for adult visitors.
            Please confirm your age before continuing.
        </p>
        <div class="btn-group" style="justify-content:center">
            <button class="btn" id="age-accept">Yes, I'm 18+</button>
            <button class="btn btn-secondary" id="age-decline">
                No, leave site
            </button>
        </div>
    </div>
</div>
"""

def footer():
    return f"""
<footer class="site-footer">
    <div class="container">
        <div class="footer-grid">
            <div>
                <a class="logo" href="/">COUPLES <span>BUCKET LIST</span></a>
                <p>
                    Romantic ideas, shared adventures, meaningful
                    challenges, and memorable experiences for couples.
                </p>
            </div>
            <div>
                <h3>Explore</h3>
                <p><a href="/">All Bucket Lists</a></p>
                <p><a href="/#categories">Categories</a></p>
                <p><a href="/#newest">Newest Ideas</a></p>
            </div>
            <div>
                <h3>Information</h3>
                <p><a href="/dmca.html">DMCA Policy</a></p>
                <p><a href="/2257.html">18 U.S.C. 2257 Statement</a></p>
                <p><a href="mailto:{CONTACT_EMAIL}">Contact</a></p>
            </div>
            <div>
                <h3>Our Mission</h3>
                <p>
                    Helping couples discover new ways to connect,
                    communicate, explore, and create lasting memories.
                </p>
            </div>
        </div>
        <p style="margin-top:35px;border-top:1px solid var(--border);
                  padding-top:20px">
            &copy; <span class="live-year">{CURRENT_YEAR}</span>
            {SITE_NAME}. All rights reserved.
        </p>
        <p>
            This website provides general entertainment and
            relationship inspiration. All activities should be
            consensual, safe, and appropriate for everyone involved.
        </p>
        <section style="margin-top:35px;padding:28px 0;border-top:1px solid rgba(255,255,255,.10);">
            <h3 style="margin:0 0 18px;color:#f7f2fa;font-size:20px;">
                Explore Our Interactive Network
            </h3>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;">
                <a href="https://ai-girlfriend-prompts.velvetgrid.workers.dev" target="_blank" rel="noopener">AI Girlfriend Prompts</a>
                <a href="https://couples-intimacy-games.velvetgrid.workers.dev" target="_blank" rel="noopener">Couples Intimacy Games</a>
                <a href="https://fantasy-roleplay-hub.velvetgrid.workers.dev" target="_blank" rel="noopener">Fantasy Roleplay Hub</a>
                <a href="https://character-persona-hub.velvetgrid.workers.dev" target="_blank" rel="noopener">Character Persona Hub</a>
                <a href="https://flirty-chat-openers.velvetgrid.workers.dev" target="_blank" rel="noopener">Flirty Chat Openers</a>
                <a href="https://midnight-audio-stories.velvetgrid.workers.dev" target="_blank" rel="noopener">Midnight Audio Stories</a>
                <a href="https://spicy-party-games.velvetgrid.workers.dev" target="_blank" rel="noopener">Spicy Party Games</a>
                <a href="https://intimacy-quiz-hub.velvetgrid.workers.dev" target="_blank" rel="noopener">Intimacy Quiz Hub</a>
                <a href="https://couples-bucket-list.velvetgrid.workers.dev" target="_blank" rel="noopener">Couples Bucket List</a>
                <a href="https://adult-ai-art-prompts.velvetgrid.workers.dev" target="_blank" rel="noopener">Adult AI Art Prompts</a>
            </div>
        </section>
    </div>
</footer>
"""

def base_document(title, description, canonical, body, scripts="",
                  extra_head="", image=None):

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{metadata(title, description, canonical, image)}
<style>{CSS}</style>
{extra_head}
</head>
<body>
<!-- AD_SLOT_POPUNDER -->
{header()}
{body}
{footer()}
{age_modal()}
<script>{GLOBAL_JS}</script>
{scripts}
</body>
</html>
"""


# ============================================================
# SEARCH ENGINE AND LIST CARDS
# ============================================================

def card_html(row):
    tags = " ".join(row["_tags"])

    return f"""
<article class="card list-card"
    data-title="{esc(row['title'].lower())}"
    data-keyword="{esc(row['target_keyword'].lower())}"
    data-tags="{esc(tags.lower())}">
    <div class="card-meta">{esc(row['category'])}</div>
    <h3><a href="/list/{esc(row['slug'])}.html">{esc(row['title'])}</a></h3>
    <p>{esc(truncate(row['description'], 115))}</p>
    <div class="pills">
        <span class="count">{len(row['_items'])} ideas</span>
        <span class="count">{esc(row['subcategory'])}</span>
    </div>
    <p><a href="/list/{esc(row['slug'])}.html">Explore this bucket list &rarr;</a></p>
</article>
"""

def search_javascript():
    return r"""
<script>
(function () {
    var input = document.getElementById("site-search");
    if (!input) return;

    var cards = Array.from(document.querySelectorAll(".list-card"));
    var empty = document.getElementById("search-empty");
    var count = document.getElementById("search-count");

    input.addEventListener("input", function () {
        var query = input.value.toLowerCase().trim();
        var visible = 0;

        cards.forEach(function (card) {
            var text = [
                card.dataset.title || "",
                card.dataset.keyword || "",
                card.dataset.tags || ""
            ].join(" ");

            var match = text.includes(query);

            card.style.display = match ? "" : "none";

            if (match) visible++;
        });

        if (count) {
            count.textContent = query
                ? visible + " matching bucket lists"
                : cards.length + " bucket lists";
        }

        if (empty) {
            empty.style.display = visible === 0 ? "block" : "none";
        }
    });
})();
</script>
"""


# ============================================================
# CATEGORY, TOPIC AND TAG INDEXING
# ============================================================

def build_indexes(rows):
    categories = defaultdict(list)
    subcategories = defaultdict(list)
    tags = defaultdict(list)

    for row in rows:
        category_key = slugify(row["category"])
        subcategory_key = slugify(row["subcategory"])

        row["_category_slug"] = category_key
        row["_subcategory_slug"] = subcategory_key

        categories[category_key].append(row)
        subcategories[subcategory_key].append(row)

        for tag in row["_tags"]:
            tags[slugify(tag)].append(row)

    return categories, subcategories, tags


def category_display_name(rows):
    return rows[0]["category"] if rows else "Category"


def topic_display_name(rows):
    return rows[0]["subcategory"] if rows else "Topic"


# ============================================================
# HOMEPAGE
# ============================================================

def homepage(rows, categories, subcategories, tags):
    category_html = []

    for key, grouped_rows in sorted(
        categories.items(),
        key=lambda item: item[0]
    ):
        category_html.append(f"""
<div class="card">
    <h3>
        <a href="/category/{esc(key)}/page-1.html">
            {esc(category_display_name(grouped_rows))}
        </a>
    </h3>
    <span class="count">{len(grouped_rows)} bucket lists</span>
</div>
""")

    subcategory_html = []

    for key, grouped_rows in sorted(
        subcategories.items(),
        key=lambda item: item[0]
    ):
        subcategory_html.append(f"""
<a class="pill" href="/topic/{esc(key)}.html">
    {esc(topic_display_name(grouped_rows))}
    <span class="count">{len(grouped_rows)}</span>
</a>
""")

    tag_html = []

    for key, grouped_rows in sorted(
        tags.items(),
        key=lambda item: (-len(item[1]), item[0])
    ):
        tag_name = next(
            (
                tag
                for row in grouped_rows
                for tag in row["_tags"]
                if slugify(tag) == key
            ),
            key.replace("-", " ").title()
        )

        tag_html.append(f"""
<a class="pill" href="/tag/{esc(key)}.html">
    #{esc(tag_name)} <span>{len(grouped_rows)}</span>
</a>
""")

    newest = sorted(
        rows,
        key=lambda row: row["_date"],
        reverse=True
    )[:30]

    newest_html = "\n".join(card_html(row) for row in newest)
    all_cards = "\n".join(card_html(row) for row in rows)

    body = f"""
<main>
<section class="hero">
    <div class="container">
        <div class="eyebrow">A Lifetime of Adventures Starts Together</div>
        <h1>Create Your Ultimate <span style="color:var(--gold)">
            Couples Bucket List
        </span></h1>
        <p class="lead">
            Discover romantic challenges, exciting date-night ideas,
            unforgettable adventures, and meaningful experiences.
            Build memories together, one checked box at a time.
        </p>
        <div class="edition-badge">Updated Bucket List Edition</div>
        <div class="search-box">
            <input type="search" id="site-search"
                placeholder="Search romantic ideas, challenges, adventures..."
                aria-label="Search couples bucket lists">
            <p id="search-count" style="color:var(--muted);font-size:13px">
                {len(rows)} bucket lists available
            </p>
        </div>
        <div class="btn-group" style="justify-content:center">
            <a class="btn" href="#newest">Explore Bucket Lists</a>
            <a class="btn btn-secondary" href="#categories">
                Browse Categories
            </a>
        </div>
    </div>
</section>

<!-- AD_SLOT_TOP_BANNER -->

<section class="section container" id="categories">
    <div class="section-heading">
        <h2>Browse Bucket List Categories</h2>
        <span class="count">{len(categories)} unique categories</span>
    </div>
    <div class="grid">
        {"".join(category_html)}
    </div>
</section>

<section class="section container" id="topics">
    <div class="section-heading">
        <h2>Explore Popular Subcategories</h2>
    </div>
    <div class="pills">
        {"".join(subcategory_html)}
    </div>
</section>

<section class="section container">
    <div class="section-heading">
        <h2>Discover Bucket List Tags</h2>
    </div>
    <div class="tag-cloud">
        {"".join(tag_html)}
    </div>
</section>

<!-- AD_SLOT_MID_CONTENT -->

<section class="section container" id="newest">
    <div class="section-heading">
        <h2>30 Newest Couples Bucket Lists</h2>
        <span class="count">Latest adventures</span>
    </div>
    <div class="grid" id="newest-grid">
        {newest_html}
    </div>
</section>

<section class="section container">
    <div class="section-heading">
        <h2>All Couples Bucket Lists</h2>
        <span class="count">{len(rows)} total lists</span>
    </div>
    <div class="grid" id="all-lists">
        {all_cards}
    </div>
    <div id="search-empty" class="empty-state">
        <h3>No matching bucket lists found.</h3>
        <p>Try another keyword or explore our categories.</p>
    </div>
</section>

<section class="section container">
    <div class="affiliate-card">
        <div class="eyebrow">Make Every Moment Count</div>
        <h2>Turn Your Next Date Into a Memory</h2>
        <p>
            Discover new experiences and ideas to make your time
            together more meaningful.
        </p>
        <a class="btn" href="{esc(AFFILIATE_URL)}" rel="nofollow sponsored">
            {esc(AFFILIATE_CTA_TEXT)}
        </a>
    </div>
</section>
</main>
"""

    return base_document(
        f"{SITE_NAME} | Romantic Couples Bucket Lists & Date Ideas",
        "Explore interactive couples bucket lists, romantic challenges, "
        "date-night ideas, and unforgettable adventures to enjoy together.",
        make_url(""),
        body,
        search_javascript()
    )


# ============================================================
# RELATED CONTENT
# ============================================================

def get_related(row, rows):
    candidates = []

    for other in rows:
        if other["slug"] == row["slug"]:
            continue

        same_subcategory = (
            other["_subcategory_slug"] == row["_subcategory_slug"]
        )

        shared_tags = (
            set(tag.lower() for tag in row["_tags"])
            & set(tag.lower() for tag in other["_tags"])
        )

        same_category = (
            other["_category_slug"] == row["_category_slug"]
        )

        score = (
            (100 if same_subcategory else 0)
            + len(shared_tags) * 15
            + (10 if same_category else 0)
        )

        candidates.append((score, other["_date"], other))

    candidates.sort(
        key=lambda item: (item[0], item[1]),
        reverse=True
    )

    return [item[2] for item in candidates[:RELATED_ITEMS]]


# ============================================================
# STRUCTURED DATA
# ============================================================

def detail_structured_data(row, related):
    page_url = make_url(f"list/{row['slug']}.html")

    items = []

    for index, item in enumerate(row["_items"], start=1):
        items.append({
            "@type": "ListItem",
            "position": index,
            "name": item
        })

    article = {
        "@type": "Article",
        "@id": page_url + "#article",
        "headline": row["title"],
        "description": get_description(row),
        "mainEntityOfPage": page_url,
        "datePublished": row["_date"].strftime("%Y-%m-%d"),
        "dateModified": datetime.utcnow().strftime("%Y-%m-%d"),
        "author": {
            "@type": "Organization",
            "name": SITE_NAME
        },
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME
        },
        "articleSection": row["category"],
        "keywords": ", ".join(
            [row["target_keyword"]] + row["_tags"]
        )
    }

    item_list = {
        "@type": "ItemList",
        "@id": page_url + "#bucket-list",
        "name": row["title"],
        "numberOfItems": len(items),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": items
    }

    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": make_url("")
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": row["category"],
                "item": make_url(
                    f"category/{row['_category_slug']}/page-1.html"
                )
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": row["title"],
                "item": page_url
            }
        ]
    }

    faq_entities = []

    for question, answer in [
        (row["faq_q1"], row["faq_a1"]),
        (row["faq_q2"], row["faq_a2"])
    ]:
        if question and answer:
            faq_entities.append({
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": answer
                }
            })

    faq_schema = None

    if faq_entities:
        faq_schema = {
            "@type": "FAQPage",
            "mainEntity": faq_entities
        }

    graph = [article, item_list, breadcrumb]

    if faq_schema:
        graph.append(faq_schema)

    return {
        "@context": "https://schema.org",
        "@graph": graph
    }


# ============================================================
# INTERACTIVE CHECKLIST JAVASCRIPT
# ============================================================

CHECKLIST_JS = r"""
<script>
(function () {
    "use strict";

    var root = document.getElementById("couples-studio");
    if (!root) return;

    var slug = root.dataset.slug;
    var storageKey = "couples_bucket_list_" + slug + "_v1";

    var items = Array.from(
        root.querySelectorAll(".checklist input[type=checkbox]")
    );

    var progress = document.getElementById("progress-fill");
    var progressLabel = document.getElementById("progress-label");
    var randomResult = document.getElementById("random-result");
    var partner1 = document.getElementById("partner1");
    var partner2 = document.getElementById("partner2");
    var checklistTitle = document.getElementById("checklist-title");
    var shareSummary = document.getElementById("share-summary");

    var originalTitle = checklistTitle
        ? checklistTitle.dataset.original
        : "Our Couples Bucket List";

    function getNames() {
        var first = partner1 && partner1.value.trim()
            ? partner1.value.trim()
            : "Partner 1";

        var second = partner2 && partner2.value.trim()
            ? partner2.value.trim()
            : "Partner 2";

        return [first, second];
    }

    function updateNames() {
        var names = getNames();

        if (checklistTitle) {
            checklistTitle.textContent =
                names[0] + " & " + names[1] + ": " + originalTitle;
        }

        updateShareSummary();
    }

    function completedItems() {
        return items.filter(function (item) {
            return item.checked;
        });
    }

    function saveState() {
        var state = items.map(function (item) {
            return item.checked;
        });

        try {
            localStorage.setItem(storageKey, JSON.stringify(state));
        } catch (error) {
            console.warn("Checklist progress could not be saved.", error);
        }
    }

    function loadState() {
        try {
            var saved = JSON.parse(localStorage.getItem(storageKey) || "null");

            if (Array.isArray(saved)) {
                items.forEach(function (item, index) {
                    item.checked = saved[index] === true;
                });
            }
        } catch (error) {
            console.warn("Saved checklist data could not be loaded.", error);
        }
    }

    function updateShareSummary() {
        if (!shareSummary) return;

        var names = getNames();
        var done = completedItems().length;
        var total = items.length;

        shareSummary.textContent =
            names[0] + " & " + names[1] +
            " completed " + done + " of " + total +
            " adventures (" +
            Math.round(done / Math.max(total, 1) * 100) +
            "%) on their couples bucket list!";
    }

    function updateProgress() {
        var done = completedItems().length;
        var total = items.length;
        var percent = Math.round(done / Math.max(total, 1) * 100);

        if (progress) {
            progress.style.width = percent + "%";
        }

        if (progressLabel) {
            progressLabel.textContent =
                done + " of " + total +
                " Completed \u2014 " + percent + "%";
        }

        items.forEach(function (item) {
            var li = item.closest("li");
            if (li) {
                li.classList.toggle("completed", item.checked);
            }
        });

        saveState();
        updateShareSummary();
    }

    function pickRandom() {
        var unchecked = items.filter(function (item) {
            return !item.checked;
        });

        if (!unchecked.length) {
            randomResult.textContent =
                "Amazing! You have completed every adventure on this list.";
            randomResult.style.display = "block";
            return;
        }

        var selected = unchecked[
            Math.floor(Math.random() * unchecked.length)
        ];

        selected.checked = true;
        updateProgress();

        var label = selected.closest("li").querySelector("label");

        randomResult.textContent =
            "Your next adventure: " + label.textContent;

        randomResult.style.display = "block";

        selected.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    function copyUnchecked() {
        var names = getNames();

        var unchecked = items.filter(function (item) {
            return !item.checked;
        }).map(function (item) {
            return "- " + item.closest("li").querySelector("label").textContent;
        });

        var message =
            "Our Couples Bucket List\n" +
            names[0] + " & " + names[1] + "\n\n" +
            (unchecked.length
                ? "Adventures still waiting for us:\n" + unchecked.join("\n")
                : "We completed every adventure!");

        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(message).then(function () {
                alert("Your unchecked ideas are ready to send!");
            }).catch(function () {
                fallbackCopy(message);
            });
        } else {
            fallbackCopy(message);
        }
    }

    function fallbackCopy(text) {
        var textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";

        document.body.appendChild(textarea);
        textarea.select();

        try {
            document.execCommand("copy");
            alert("Your bucket list ideas have been copied!");
        } catch (error) {
            alert("Copy is unavailable in this browser.");
        }

        textarea.remove();
    }

    items.forEach(function (item) {
        item.addEventListener("change", updateProgress);
    });

    if (partner1) partner1.addEventListener("input", updateNames);
    if (partner2) partner2.addEventListener("input", updateNames);

    var randomButton = document.getElementById("random-adventure");
    var copyButton = document.getElementById("copy-unchecked");

    if (randomButton) {
        randomButton.addEventListener("click", pickRandom);
    }

    if (copyButton) {
        copyButton.addEventListener("click", copyUnchecked);
    }

    loadState();
    updateNames();
    updateProgress();
})();
</script>
"""


# ============================================================
# DETAIL PAGE
# ============================================================

def detail_page(row, rows):
    related = get_related(row, rows)

    checklist_items = []

    for index, item in enumerate(row["_items"]):
        item_id = f"adventure-{index + 1}"

        checklist_items.append(f"""
<li>
    <input type="checkbox" id="{item_id}">
    <label for="{item_id}">{esc(item)}</label>
</li>
""")

    related_html = "\n".join(
        card_html(item) for item in related
    )

    tag_links = []

    for tag in row["_tags"]:
        tag_links.append(
            f'<a class="pill" href="/tag/{esc(slugify(tag))}.html">'
            f'#{esc(tag)}</a>'
        )

    category_link = (
        f"/category/{row['_category_slug']}/page-1.html"
    )

    topic_link = (
        f"/topic/{row['_subcategory_slug']}.html"
    )

    faq_html = ""

    for question, answer in [
        (row["faq_q1"], row["faq_a1"]),
        (row["faq_q2"], row["faq_a2"])
    ]:
        if question and answer:
            faq_html += f"""
<div class="faq-item">
    <h3>{esc(question)}</h3>
    <p>{esc(answer)}</p>
</div>
"""

    schema = safe_json(detail_structured_data(row, related))

    body = f"""
<main>
<div class="container">
    <nav class="breadcrumb" aria-label="Breadcrumb">
        <a href="/">Home</a> /
        <a href="{esc(category_link)}">{esc(row['category'])}</a> /
        <span>{esc(row['title'])}</span>
    </nav>
</div>

<section class="detail-hero container">
    <div class="eyebrow">Your Next Shared Adventure</div>
    <h1>{esc(row['title'])}</h1>
    <p class="lead" style="margin:0">
        {esc(row['description'])}
    </p>
    <div class="edition-badge"></div>
    <div class="pills" style="margin-top:18px">
        <a class="pill" href="{esc(category_link)}">
            {esc(row['category'])}
        </a>
        <a class="pill" href="{esc(topic_link)}">
            {esc(row['subcategory'])}
        </a>
    </div>
</section>

<!-- AD_SLOT_TOP_BANNER -->

<section class="section container">
    <div class="studio" id="couples-studio"
         data-slug="{esc(row['slug'])}">
        <div class="eyebrow">Interactive Couples Studio</div>
        <h2 id="checklist-title"
            data-original="{esc(row['title'])}">
            Our Couples Bucket List: {esc(row['title'])}
        </h2>
        <p style="color:var(--muted)">
            Personalize your experience, check off adventures,
            and track your progress together.
        </p>

        <div class="personalizer">
            <label>
                Partner 1
                <input class="name-input" id="partner1"
                       type="text" maxlength="50"
                       placeholder="Enter partner's name">
            </label>
            <label>
                Partner 2
                <input class="name-input" id="partner2"
                       type="text" maxlength="50"
                       placeholder="Enter partner's name">
            </label>
        </div>

        <div style="margin-top:25px">
            <div class="progress-label" id="progress-label">
                0 of {len(row['_items'])} Completed — 0%
            </div>
            <div class="progress-track"
                 role="progressbar"
                 aria-label="Bucket list completion"
                 aria-valuemin="0"
                 aria-valuemax="100">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
        </div>

        <ul class="checklist">
            {"".join(checklist_items)}
        </ul>

        <div class="btn-group">
            <button class="btn" id="random-adventure">
                Pick Random Next Adventure
            </button>
            <button class="btn btn-secondary" id="copy-unchecked">
                Copy Unchecked Ideas to Send Partner
            </button>
        </div>

        <div class="random-result" id="random-result"
             aria-live="polite"></div>

        <div class="card" style="margin-top:25px">
            <div class="eyebrow">Your Shared Progress</div>
            <p id="share-summary" style="margin-bottom:0">
                Your couples bucket list progress will appear here.
            </p>
        </div>
    </div>

    <details class="tips-card">
        <summary>
            Date Planning & Mood Tips — Open Your Adventure Guide
        </summary>
        <div class="tips-content">
            {esc(row['planning_tips'] or
                'Choose a date that works for both partners. '
                'Discuss expectations, make a simple plan, and '
                'leave room for spontaneous moments.')}
        </div>
    </details>

    <!-- AD_SLOT_MID_CONTENT -->

    <div class="affiliate-card">
        <div class="eyebrow">Sponsored Experience</div>
        <h2>Make Your Next Adventure Unforgettable</h2>
        <p>
            Looking for fresh inspiration? Explore experiences
            designed to help couples enjoy more quality time together.
        </p>
        <a class="btn" href="{esc(AFFILIATE_URL)}"
           rel="nofollow sponsored">
            {esc(AFFILIATE_CTA_TEXT)}
        </a>
    </div>
</section>

<section class="section container">
    <div class="section-heading">
        <h2>About This Couples Bucket List</h2>
    </div>
    <div class="card">
        <p>{esc(row['description'])}</p>
        <p>
            This collection contains {len(row['_items'])} ideas
            for couples to explore at their own pace.
            Select activities that suit both partners and
            make every experience comfortable and enjoyable.
        </p>
        <div class="pills">
            {"".join(tag_links)}
        </div>
        <p style="color:var(--muted);font-size:13px">
            Originally published:
            {esc(format_date(row['_date']))}
        </p>
    </div>
</section>

<section class="section container">
    <div class="section-heading">
        <h2>Frequently Asked Questions</h2>
    </div>
    <div class="card">
        {faq_html or
        '<p>Choose the activities that work best for your relationship. '
        'Every couple can personalize their own experience.</p>'}
    </div>
</section>

<section class="section container">
    <div class="section-heading">
        <h2>Related Couples Bucket Lists</h2>
        <span class="count">{len(related)} related ideas</span>
    </div>
    <div class="grid">
        {related_html or '<p>More bucket lists coming soon.</p>'}
    </div>
</section>

</main>
"""

    extra_head = (
        '<script type="application/ld+json">'
        + schema
        + '</script>'
    )

    return base_document(
        f"{row['title']} | Couples Bucket List",
        get_description(row),
        make_url(f"list/{row['slug']}.html"),
        body,
        CHECKLIST_JS,
        extra_head
    )


# ============================================================
# GENERIC HUB PAGES
# ============================================================

def hub_page(title, description, canonical, rows, page_number=None,
             total_pages=None, previous_url=None, next_url=None):

    cards = "\n".join(card_html(row) for row in rows)

    pagination = ""

    if total_pages and total_pages > 1:
        links = []

        if previous_url:
            links.append(
                f'<a rel="prev" href="{esc(previous_url)}">Previous</a>'
            )

        for number in range(1, total_pages + 1):
            if number == page_number:
                links.append(f"<span>{number}</span>")
            else:
                if title.startswith("Category: "):
                    prefix = canonical.split("/category/")[1].split(
                        "/page-"
                    )[0]

                    url = f"/category/{prefix}/page-{number}.html"

                else:
                    url = canonical

                links.append(
                    f'<a href="{esc(url)}">{number}</a>'
                )

        if next_url:
            links.append(
                f'<a rel="next" href="{esc(next_url)}">Next</a>'
            )

        pagination = (
            '<nav class="pagination" aria-label="Pagination">'
            + "".join(links)
            + "</nav>"
        )

    body = f"""
<main>
<section class="hero">
    <div class="container">
        <div class="eyebrow">Explore Our Collection</div>
        <h1>{esc(title)}</h1>
        <p class="lead">{esc(description)}</p>
        <span class="count">{len(rows)} bucket lists</span>
    </div>
</section>

<section class="section container">
    <div class="grid">
        {cards or '<p>No bucket lists available in this collection yet.</p>'}
    </div>
    {pagination}
</section>
</main>
"""

    extra_head = ""

    if previous_url:
        extra_head += (
            f'<link rel="prev" href="{esc(make_url(previous_url))}">'
        )

    if next_url:
        extra_head += (
            f'<link rel="next" href="{esc(make_url(next_url))}">'
        )

    return base_document(
        f"{title} | {SITE_NAME}",
        description,
        canonical,
        body,
        extra_head=extra_head
    )


def build_category_pages(categories):
    for key, grouped_rows in categories.items():
        ordered = sorted(
            grouped_rows,
            key=lambda row: row["_date"],
            reverse=True
        )

        total_pages = max(
            1,
            math.ceil(len(ordered) / ITEMS_PER_PAGE)
        )

        category_name = category_display_name(ordered)

        for page in range(1, total_pages + 1):
            start = (page - 1) * ITEMS_PER_PAGE
            page_rows = ordered[start:start + ITEMS_PER_PAGE]

            path = f"category/{key}/page-{page}.html"

            previous_url = (
                f"/category/{key}/page-{page - 1}.html"
                if page > 1 else None
            )

            next_url = (
                f"/category/{key}/page-{page + 1}.html"
                if page < total_pages else None
            )

            title = f"Category: {category_name}"

            if total_pages > 1:
                title += f" — Page {page}"

            description = (
                f"Explore {len(ordered)} couples bucket lists in "
                f"{category_name}. Discover romantic challenges, "
                "shared adventures, and memorable date ideas."
            )

            canonical = make_url(path)

            content = hub_page(
                title,
                description,
                canonical,
                page_rows,
                page,
                total_pages,
                previous_url,
                next_url
            )

            write_file(
                os.path.join(OUTPUT_DIR, path),
                content
            )


def build_topic_pages(subcategories):
    for key, grouped_rows in subcategories.items():
        title = topic_display_name(grouped_rows)

        description = (
            f"Explore {len(grouped_rows)} couples bucket lists "
            f"about {title}, including romantic activities, "
            "date-night inspiration, and shared experiences."
        )

        path = f"topic/{key}.html"

        content = hub_page(
            f"{title} Couples Bucket Lists",
            description,
            make_url(path),
            sorted(
                grouped_rows,
                key=lambda row: row["_date"],
                reverse=True
            )
        )

        write_file(
            os.path.join(OUTPUT_DIR, path),
            content
        )


def build_tag_pages(tags):
    for key, grouped_rows in tags.items():
        tag_name = next(
            (
                tag
                for row in grouped_rows
                for tag in row["_tags"]
                if slugify(tag) == key
            ),
            key.replace("-", " ").title()
        )

        description = (
            f"Browse {len(grouped_rows)} couples bucket lists "
            f"tagged {tag_name}. Find more ideas for shared "
            "adventures and memorable dates."
        )

        path = f"tag/{key}.html"

        content = hub_page(
            f"{tag_name} Bucket Lists",
            description,
            make_url(path),
            sorted(
                grouped_rows,
                key=lambda row: row["_date"],
                reverse=True
            )
        )

        write_file(
            os.path.join(OUTPUT_DIR, path),
            content
        )


# ============================================================
# LEGAL AND INFORMATIONAL PAGES
# ============================================================

def legal_page(title, description, sections, path):
    content = "".join(
        f"""
<section class="section">
    <h2>{esc(heading)}</h2>
    <p>{esc(paragraph)}</p>
</section>
"""
        for heading, paragraph in sections
    )

    body = f"""
<main>
<section class="hero">
    <div class="container">
        <div class="eyebrow">{esc(SITE_NAME)}</div>
        <h1>{esc(title)}</h1>
        <p class="lead">{esc(description)}</p>
    </div>
</section>
<div class="container">
{content}
</div>
</main>
"""

    return base_document(
        f"{title} | {SITE_NAME}",
        description,
        make_url(path),
        body
    )


def build_legal_pages():
    dmca_sections = [
        (
            "Copyright Policy",
            "Couples Bucket List respects intellectual property rights "
            "and expects visitors and contributors to do the same. "
            "Content published on this website may be protected by "
            "applicable copyright laws."
        ),
        (
            "Submitting a DMCA Notice",
            "If you believe material on this website infringes your "
            "copyright, email " + CONTACT_EMAIL +
            " with the identification of the copyrighted work, the "
            "location of the allegedly infringing material, your "
            "contact information, a good-faith statement, and a "
            "statement made under penalty of perjury that the "
            "information is accurate and that you are authorized "
            "to act on behalf of the rights holder."
        ),
        (
            "Review and Removal",
            "We will review complete notices and take appropriate "
            "action where warranted. Incomplete notices may require "
            "additional information before they can be processed."
        ),
        (
            "Contact",
            "Copyright-related correspondence should be sent to "
            + CONTACT_EMAIL + "."
        )
    ]

    write_file(
        os.path.join(OUTPUT_DIR, "dmca.html"),
        legal_page(
            "DMCA Copyright Policy",
            "Information about copyright complaints and intellectual "
            "property rights.",
            dmca_sections,
            "dmca.html"
        )
    )

    sections_2257 = [
        (
            "Nature of This Website",
            SITE_NAME + " is an informational and entertainment "
            "website focused on relationship inspiration, romantic "
            "ideas, date-night checklists, and interactive couples "
            "activities."
        ),
        (
            "Content Statement",
            "This website does not produce, host, or publish "
            "photographic or video depictions of sexually explicit "
            "conduct. The website primarily contains text-based "
            "editorial content and interactive checklists."
        ),
        (
            "Age Restriction",
            "This website is intended for visitors who are at least "
            "18 years old. Visitors must confirm their age before "
            "accessing the website."
        ),
        (
            "Questions",
            "For questions about this statement, contact "
            + CONTACT_EMAIL + "."
        )
    ]

    write_file(
        os.path.join(OUTPUT_DIR, "2257.html"),
        legal_page(
            "18 U.S.C. 2257 Statement",
            "Record-keeping and content compliance information.",
            sections_2257,
            "2257.html"
        )
    )


# ============================================================
# XML SITEMAPS
# ============================================================

SITEMAP_XSL = r"""<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
 xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
 xmlns:s="http://www.sitemaps.org/schemas/sitemap/0.9">
<xsl:output method="html" encoding="UTF-8" indent="yes"/>
<xsl:template match="/">
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Couples Bucket List Sitemap</title>
<style>
*{box-sizing:border-box}
body{
background:#09080d;
color:#f7f2fa;
font-family:system-ui,sans-serif;
padding:35px;
margin:0;
line-height:1.6
}
main{max-width:1050px;margin:auto}
h1{color:#f59e0b}
p{color:#a9a0b6}
table{
width:100%;
border-collapse:collapse;
background:#15121e;
border-radius:14px;
overflow:hidden
}
th,td{
padding:14px;
border-bottom:1px solid #30283b;
text-align:left;
overflow-wrap:anywhere
}
th{color:#f59e0b}
a{color:#ec4899;text-decoration:none}
a:hover{color:#f59e0b}
</style>
</head>
<body>
<main>
<h1>Couples Bucket List XML Sitemap</h1>
<p>Search engine index of website pages.</p>
<table>
<tr><th>URL</th><th>Last Modified</th></tr>
<xsl:for-each select="s:urlset/s:url">
<tr>
<td>
<a href="{s:loc}">
<xsl:value-of select="s:loc"/>
</a>
</td>
<td><xsl:value-of select="s:lastmod"/></td>
</tr>
</xsl:for-each>
</table>
</main>
</body>
</html>
</xsl:template>
</xsl:stylesheet>
"""

def build_sitemaps(rows, categories, subcategories, tags):
    urls = []

    def add_url(path, priority="0.7", changefreq="monthly"):
        urls.append({
            "loc": make_url(path),
            "lastmod": datetime.utcnow().strftime("%Y-%m-%d"),
            "priority": priority,
            "changefreq": changefreq
        })

    add_url("", "1.0", "weekly")

    for row in rows:
        add_url(
            f"list/{row['slug']}.html",
            "0.9",
            "monthly"
        )

    for key, grouped_rows in categories.items():
        total_pages = max(
            1,
            math.ceil(len(grouped_rows) / ITEMS_PER_PAGE)
        )

        for page in range(1, total_pages + 1):
            add_url(
                f"category/{key}/page-{page}.html",
                "0.8",
                "weekly"
            )

    for key in subcategories:
        add_url(
            f"topic/{key}.html",
            "0.8",
            "weekly"
        )

    for key in tags:
        add_url(
            f"tag/{key}.html",
            "0.6",
            "weekly"
        )

    add_url("dmca.html", "0.2", "yearly")
    add_url("2257.html", "0.2", "yearly")

    write_file(
        os.path.join(OUTPUT_DIR, "sitemap.xsl"),
        SITEMAP_XSL
    )

    def url_xml(item):
        return f"""
    <url>
        <loc>{esc(item['loc'])}</loc>
        <lastmod>{item['lastmod']}</lastmod>
        <changefreq>{item['changefreq']}</changefreq>
        <priority>{item['priority']}</priority>
    </url>"""

    chunks = [
        urls[i:i + SITEMAP_LIMIT]
        for i in range(0, len(urls), SITEMAP_LIMIT)
    ]

    if not chunks:
        chunks = [[]]

    sitemap_files = []

    for index, chunk in enumerate(chunks, start=1):
        filename = f"sitemap-{index}.xml"
        sitemap_files.append(filename)

        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<?xml-stylesheet type="text/xsl" href="sitemap.xsl"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(url_xml(item) for item in chunk)
            + "\n</urlset>"
        )

        write_file(
            os.path.join(OUTPUT_DIR, filename),
            content
        )

    if len(sitemap_files) == 1:
        # Provide both a sitemap index and a directly usable sitemap.
        index_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<?xml-stylesheet type="text/xsl" href="sitemap.xsl"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'<sitemap><loc>{esc(make_url(sitemap_files[0]))}</loc>'
            f'<lastmod>{datetime.utcnow().strftime("%Y-%m-%d")}</lastmod>'
            '</sitemap></sitemapindex>'
        )
    else:
        index_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<?xml-stylesheet type="text/xsl" href="sitemap.xsl"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(
                f"""
<sitemap>
    <loc>{esc(make_url(filename))}</loc>
    <lastmod>{datetime.utcnow().strftime("%Y-%m-%d")}</lastmod>
</sitemap>"""
                for filename in sitemap_files
            )
            + "\n</sitemapindex>"
        )

    write_file(
        os.path.join(OUTPUT_DIR, "sitemap.xml"),
        index_content
    )


# ============================================================
# ROBOTS.TXT
# ============================================================

def build_robots():
    content = f"""User-agent: *
Allow: /

Disallow: /assets/
Disallow: /private/

Sitemap: {make_url('sitemap.xml')}
"""

    write_file(
        os.path.join(OUTPUT_DIR, "robots.txt"),
        content
    )


# ============================================================
# CLOUDFLARE PAGES / WORKERS COMPATIBILITY
# ============================================================

def build_headers():
    content = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: SAMEORIGIN
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Cross-Origin-Resource-Policy: same-origin

/*.html
  Cache-Control: public, max-age=3600, must-revalidate

/*.xml
  Content-Type: application/xml; charset=utf-8
  Cache-Control: public, max-age=3600

/*.xsl
  Content-Type: application/xslt+xml; charset=utf-8
"""

    write_file(
        os.path.join(OUTPUT_DIR, "_headers"),
        content
    )


# ============================================================
# BUILD REPORT
# ============================================================

def build_report(rows, categories, subcategories, tags):
    report = {
        "site": SITE_NAME,
        "base_url": BASE_URL,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "current_year": CURRENT_YEAR,
        "total_bucket_lists": len(rows),
        "unique_categories": len(categories),
        "unique_subcategories": len(subcategories),
        "unique_tags": len(tags),
        "total_checklist_ideas": sum(
            len(row["_items"]) for row in rows
        ),
        "pages_generated": (
            len(rows)
            + len(categories)
            + len(subcategories)
            + len(tags)
            + 3
        )
    }

    write_file(
        os.path.join(OUTPUT_DIR, "build-report.json"),
        json.dumps(report, indent=2, ensure_ascii=False)
    )


# ============================================================
# MAIN BUILD PIPELINE
# ============================================================

def build():
    print("=" * 65)
    print(f"BUILDING {SITE_NAME.upper()}")
    print("=" * 65)

    print("\n[1/10] Loading CSV data...")

    rows = load_data()

    print(f"Loaded {len(rows)} bucket lists.")

    print("\n[2/10] Preparing category, topic and tag indexes...")

    categories, subcategories, tags = build_indexes(rows)

    print(f"Unique categories: {len(categories)}")
    print(f"Unique subcategories: {len(subcategories)}")
    print(f"Unique tags: {len(tags)}")

    print("\n[3/10] Preparing output directory...")

    if os.path.isdir(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for directory in [
        "list",
        "category",
        "topic",
        "tag"
    ]:
        os.makedirs(
            os.path.join(OUTPUT_DIR, directory),
            exist_ok=True
        )

    print("\n[4/10] Generating homepage...")

    write_file(
        os.path.join(OUTPUT_DIR, "index.html"),
        homepage(rows, categories, subcategories, tags)
    )

    print("\n[5/10] Generating interactive bucket list pages...")

    for index, row in enumerate(rows, start=1):
        content = detail_page(row, rows)

        write_file(
            os.path.join(
                OUTPUT_DIR,
                "list",
                row["slug"] + ".html"
            ),
            content
        )

        if index % 100 == 0:
            print(f"Generated {index} detail pages.")

    print(f"Generated {len(rows)} detail pages.")

    print("\n[6/10] Generating paginated category hubs...")

    build_category_pages(categories)

    print("\n[7/10] Generating subcategory and tag hubs...")

    build_topic_pages(subcategories)
    build_tag_pages(tags)

    print("\n[8/10] Generating legal and compliance pages...")

    build_legal_pages()

    print("\n[9/10] Generating XML sitemaps and robots.txt...")

    build_sitemaps(rows, categories, subcategories, tags)
    build_robots()
    build_headers()

    print("\n[10/10] Generating build report...")

    build_report(rows, categories, subcategories, tags)

    total_pages = sum(
        len(files)
        for _, _, files in os.walk(OUTPUT_DIR)
    )

    print("\n" + "=" * 65)
    print("BUILD COMPLETED SUCCESSFULLY")
    print("=" * 65)
    print(f"Website:       {BASE_URL}")
    print(f"Output:        {os.path.abspath(OUTPUT_DIR)}")
    print(f"Bucket lists:  {len(rows)}")
    print(f"Categories:    {len(categories)}")
    print(f"Subcategories: {len(subcategories)}")
    print(f"Tags:          {len(tags)}")
    print(f"Total files:   {total_pages}")
    print("=" * 65)
    print("\nCloudflare deployment:")
    print("1. Upload the contents of dist/ to Cloudflare Pages.")
    print("2. Set the production custom domain or Workers URL.")
    print("3. Submit /sitemap.xml to Google Search Console.")
    print("4. Replace AFFILIATE_URL with your approved affiliate URL.")
    print("=" * 65)


if __name__ == "__main__":
    try:
        build()
    except Exception as error:
        print("\nBUILD FAILED")
        print(f"Error: {error}")
        raise
