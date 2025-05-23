import os
import requests
from supabase import create_client
import logging
import time
import threading
from flask import Flask, jsonify
import re
import json

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Validation
if not SUPABASE_URL or not SUPABASE_KEY or not OPENROUTER_API_KEY:
    raise ValueError("Missing environment variables: SUPABASE_URL, SUPABASE_KEY, or OPENROUTER_API_KEY")

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask app setup
app = Flask(__name__)
update_running = False

def replace_placeholders(content):
    """Content me placeholders ko replace karta hai."""
    replacements = {
        "[insert specific area of the bill]": "border security",
        "[insert potential negative impact]": "reduced access to healthcare for low-income families"
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content

def clean_content(content):
    """Markdown symbols hata kar plain text banata hai."""
    if not content:
        return content
    content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)  # Bold hatao
    content = re.sub(r'\*([^*]+)\*', r'\1', content)      # Italic hatao
    content = re.sub(r'#+\s*', '', content)               # Headings hatao
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)  # Links hatao
    content = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', content)  # Images hatao
    content = re.sub(r'```[\s\S]*?```', '', content)      # Code blocks hatao
    content = re.sub(r'`([^`]+)`', r'\1', content)        # Inline code hatao
    content = re.sub(r'^\s*[-*+]\s+', '', content, flags=re.MULTILINE)  # List bullets hatao
    content = re.sub(r'\n\s*\n+', '\n\n', content)        # Extra newlines normalize karo
    return content.strip()

def humanize_content(content):
    """Content ko OpenRouter API se humanize karta hai."""
    prompt = f"""Is Q&A content ko ek single, detailed, aur comprehensive answer me badlo. Naya content kam se kam 1000 words ka ho, natural, conversational, aur human-like tone me likha ho. Content engaging, informative, aur robotic ya AI-generated nahi lagna chahiye. Simple, SEO-friendly language use karo. Output plain text ho, koi markdown symbols (jaise **, *, #, ya links) nahi hone chahiye.

Original Content:
{content}"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://www.knowtivus.info",
        "X-Title": "Knowtivus Blog"
    }
    data = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        humanized_content = result["choices"][0]["message"]["content"].strip()
        return humanized_content
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("Rate limit hit, 12 ghante wait kar raha hoon")
            time.sleep(12 * 3600)  # 12 hours
            return humanize_content(content)  # Retry
        else:
            logger.error(f"HTTP error: {e}")
            return None
    except Exception as e:
        logger.error(f"Content humanize karne me fail: {e}")
        return None

def process_blogs():
    """Supabase ke sab blogs ko process aur update karta hai."""
    page_size = 1000
    offset = 0
    total_updated = 0

    while True:
        logger.info(f"Blogs fetch kar raha hoon {offset} se {offset + page_size - 1}")
        response = supabase.table('blogs').select('id, content').eq('humanized', False).range(offset, offset + page_size - 1).execute()
        blogs = response.data or []

        if not blogs:
            logger.info("Aur koi blogs process karne ke liye nahi hain")
            break

        for blog in blogs:
            blog_id = blog['id']
            content = blog['content']
            if not content:
                logger.info(f"Blog ID {blog_id} me content nahi hai, skip kar raha hoon")
                continue

            # Replace placeholders
            content = replace_placeholders(content)
            logger.info(f"Blog ID {blog_id} ke liye placeholders replace kiye")

            # Humanize content
            logger.info(f"Blog ID {blog_id} ko humanize kar raha hoon")
            new_content = humanize_content(content)
            if new_content:
                new_content = clean_content(new_content)
                try:
                    supabase.table('blogs').update({'content': new_content, 'humanized': True}).eq('id', blog_id).execute()
                    total_updated += 1
                    logger.info(f"Blog ID {blog_id} successfully update ho gaya")
                except Exception as update_err:
                    logger.error(f"Blog ID {blog_id} update karne me fail: {update_err}")
            else:
                logger.warning(f"Blog ID {blog_id} ke liye humanized content nahi mila")

            time.sleep(3)  # 3-second delay taaki rate limit na hit ho

        if len(blogs) < page_size:
            logger.info("Blogs ka end aa gaya")
            break

        offset += page_size

    logger.info(f"Total blogs update hue: {total_updated}")

def process_blogs_background():
    """Blog processing ko background thread me chala raha hoon."""
    global update_running
    if update_running:
        logger.info("Update pehle se chal raha hai")
        return
    update_running = True
    try:
        process_blogs()
    finally:
        update_running = False

def keep_alive():
    """Har 5 minute me ping karta hai taaki app alive rahe."""
    max_retries = 3
    while True:
        for attempt in range(max_retries):
            try:
                response = requests.get(f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost:5000')}/ping", timeout=10)
                response.raise_for_status()
                logger.info("Keep-alive ping successful")
                break
            except Exception as e:
                logger.error(f"Keep-alive attempt {attempt + 1}/{max_retries} fail hua: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)  # Retry se pehle wait
                else:
                    logger.error("Keep-alive retries ke baad bhi fail")
        time.sleep(300)  # 5 minute wait

@app.route('/start_update', methods=['POST'])
def start_update():
    """Blog update process start karne ka route."""
    if update_running:
        return jsonify({"message": "Update pehle se chal raha hai"}), 400
    threading.Thread(target=process_blogs_background).start()
    return jsonify({"message": "Update shuru ho gaya"}), 202

@app.route('/ping', methods=['GET'])
def ping():
    """Ping route taaki app alive rahe."""
    return jsonify({"status": "alive"}), 200

if __name__ == "__main__":
    # Keep-alive thread shuru karo
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
