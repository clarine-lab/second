import os
import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_KEY = os.getenv("CLOUDFLARE_API_TOKEN")

# Cloudflare model IDs use the @cf/author/model format
DEFAULT_MODEL = "@cf/zhipu/glm-4-9b-chat" 
CF_ENDPOINT = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1/chat/completions"

app = Flask(__name__)
# This allows all external domains to talk to your Render app
CORS(app)

@app.route('/', methods=["GET"])
def health_check():
    return "Cloudflare AI Proxy Online", 200

@app.route('/v1/chat/completions', strict_slashes=False, methods=["POST", "OPTIONS"])
@app.route('/chat/completions', strict_slashes=False, methods=["POST", "OPTIONS"])
def handle_proxy():
    # 1. The Preflight Catch: Stop the browser's security check from crashing the app
    if request.method == "OPTIONS":
        return Response(status=200)

    try:
        # 2. silent=True prevents a crash if the JSON is missing or malformed
        data = request.get_json(silent=True) or {}
        
        payload = {
            "model": data.get("model", DEFAULT_MODEL),
            "messages": data.get('messages', []),
            "stream": data.get("stream", True), 
            "temperature": data.get("temperature", 0.7),
            "max_tokens": data.get("max_tokens", 4096)
        }

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        def stream_response():
            try:
                with requests.post(CF_ENDPOINT, headers=headers, json=payload, stream=True, timeout=(15, 600)) as r:
                    if r.status_code != 200:
                        yield f"data: {{\"error\": \"Cloudflare Error {r.status_code}: {r.text}\"}}\n\n"
                        return
                    
                    for line in r.iter_lines():
                        if line:
                            yield f"{line.decode('utf-8')}\n\n"

            except Exception as e:
                yield f"data: {{\"error\": \"Proxy Loop Error: {str(e)}\"}}\n\n"
        
        return Response(stream_with_context(stream_response()), content_type='text/event-stream')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
