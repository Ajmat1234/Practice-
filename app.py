import os
import logging
import time
import threading
from flask import Flask, jsonify
import re
from together import Together

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")

# Validation
if not SUPABASE_URL or not SUPABASE_KEY or not TOGETHER_API_KEY:
    raise ValueError("Missing environment variables: SUPABASE_URL, SUPABASE_KEY, or TOGETHER_API_KEY")

# Initialize Supabase client
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Together client
client = Together(api_key=TOGETHER_API_KEY)

# Flask app setup
app = Flask(__name__)
update_running = False

def replace_placeholders(content):
    """Replace placeholders in the content with specific values."""
    replacements = {
        "[insert specific area of the bill]": "border security",
        "[insert potential negative impact]": "reduced access to healthcare for low-income families"
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content

def clean_content(content):
    """Remove markdown symbols from the content to ensure plain text output."""
    if not content:
        return content
    content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)  # Remove bold
    content = re.sub(r'\*([^*]+)\*', r'\1', content)      # Remove italic
    content = re.sub(r'#+\s*', '', content)               # Remove headings
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)  # Remove links
    content = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', content)  # Remove images
    content = re.sub(r'```[\s\S]*?```', '', content)      # Remove code blocks
    content = re.sub(r'`([^`]+)`', r'\1', content)        # Remove inline code
    content = re.sub(r'^\s*[-*+]\s+', '', content, flags=re.MULTILINE)  # Remove list bullets
    content = re.sub(r'\n\s*\n+', '\n\n', content)        # Normalize newlines
    return content.strip()

def humanize_content(content):
    """Humanize content using Together API with Llama model."""
    prompt = f"""Take the following Q&A content and rewrite it into a single, detailed, and comprehensive answer. The new content should be at least 1000 words long, written in a natural, conversational, and human-like tone. Ensure the content is engaging, informative, and avoids sounding robotic or AI-generated. Use simple, SEO-friendly language. The output must be plain text with no markdown symbols (e.g., no **, *, #, or links).

Original Content:
{content}"""
    messages = [
        {"role": "user", "content": prompt}
    ]
    try:
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            messages=messages,
            stream=True
        )
        humanized_content = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                humanized_content += chunk.choices[0].delta.content
        return humanized_content.strip()
    except Exception as e:
        logger.error(f"Failed to humanize content: {e}")
        return None

def process_blogs():
    """Process and update all blogs in Supabase with humanized content."""
    page_size = 1000
    offset = 0
    total_updated = 0

    while True:
        logger.info(f"Fetching blogs {offset} to {offset + page_size - 1}")
        response = supabase.table('blogs').select('id, content').range(offset, offset + page_size - 1).execute()
        blogs = response.data or []

        if not blogs:
            logger.info("No more blogs to process")
            break

        for blog in blogs:
            blog_id = blog['id']
            content = blog['content']
            if not content:
                logger.info(f"Blog ID {blog_id} has no content, skipping")
                continue

            # Replace placeholders
            content = replace_placeholders(content)
            logger.info(f"Placeholders replaced for blog ID: {blog_id}")

            # Humanize content
            logger.info(f"Humanizing blog ID: {blog_id}")
            new_content = humanize_content(content)
            if new_content:
                new_content = clean_content(new_content)
                try:
                    supabase.table('blogs').update({'content': new_content}).eq('id', blog_id).execute()
                    total_updated += 1
                    logger.info(f"Successfully updated blog ID: {blog_id}")
                except Exception as update_err:
                    logger.error(f"Failed to update blog ID {blog_id}: {update_err}")
            else:
                logger.warning(f"No humanized content for blog ID {blog_id}")

            time.sleep(3)  # 3-second delay between requests to avoid rate limits

        if len(blogs) < page_size:
            logger.info("Reached end of blogs")
            break

        offset += page_size

    logger.info(f"Total blogs updated: {total_updated}")

def process_blogs_background():
    """Run the blog processing in a background thread."""
    global update_running
    if update_running:
        logger.info("Update already running")
        return
    update_running = True
    try:
        process_blogs()
    finally:
        update_running = False

@app.route('/start_update', methods=['POST'])
def start_update():
    """Route to start the blog update process."""
    if update_running:
        return jsonify({"message": "Update already running"}), 400
    threading.Thread(target=process_blogs_background).start()
    return jsonify({"message": "Update started"}), 202

@app.route('/ping', methods=['GET'])
def ping():
    """Route to keep the app alive."""
    return jsonify({"message": "I'm alive!"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
