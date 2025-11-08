from flask import Flask, request, jsonify, render_template_string
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit for screenshots

# Save folder (Render.com persistent storage – use /tmp or env var for production)
SAVE_DIR = '/tmp/screenshots'  # Render.com पर /tmp work करता, or env var set कर
os.makedirs(SAVE_DIR, exist_ok=True)

# HTML template for dashboard
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Screenshot Receiver</title></head>
<body>
    <h1>Received Screenshots (Latest 10)</h1>
    <p>Total: {{ total }}</p>
    {% for file in files %}
        <div>
            <h3>{{ file }}</h3>
            <img src="/image/{{ file }}" alt="{{ file }}" width="300" height="600">
            <p>Time: {{ file.replace('.jpg', '') }}</p>
        </div>
        <hr>
    {% endfor %}
    <p><a href="/">Refresh</a></p>
</body>
</html>
"""

@app.route('/upload', methods=['POST'])
def upload_screenshot():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        if file and file.filename.endswith('.jpg'):
            # Secure filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.jpg"
            filepath = os.path.join(SAVE_DIR, filename)
            file.save(filepath)
            
            size = os.path.getsize(filepath)
            print(f"✅ Screenshot received! File: {filename}, Size: {size} bytes")  # Log for Render console
            
            return jsonify({
                "success": True,
                "filename": filename,
                "size": size,
                "message": "Screenshot saved successfully!"
            }), 200
        else:
            return jsonify({"error": "Invalid file type - must be JPG"}), 400
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/image/<filename>')
def serve_image(filename):
    return send_from_directory(SAVE_DIR, filename)

@app.route('/', methods=['GET'])
def dashboard():
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.jpg')]
    files.sort(reverse=True)  # Latest first
    files = files[:10]  # Last 10
    return render_template_string(DASHBOARD_TEMPLATE, files=files, total=len(files))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
