import os
import json  # Added this import back
import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_KEY = os.getenv("CLOUDFLARE_API_TOKEN")

# Cloudflare model IDs use the @cf/author/model format
DEFAULT_MODEL = "@cf/moonshotai/kimi-k2.7-code" 
CF_ENDPOINT = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1/chat/completions"

app = Flask(__name__)
CORS(app)

@app.route('/', methods=["GET"])
def health_check():
    return "Cloudflare AI Proxy Online", 200

@app.route('/v1/chat/completions', strict_slashes=False, methods=["POST", "OPTIONS"])
@app.route('/chat/completions', strict_slashes=False, methods=["POST", "OPTIONS"])
def handle_proxy():
    if request.method == "OPTIONS":
        return Response(status=200)

    try:
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
                    # 1. Safely format the Cloudflare error so it doesn't break the frontend UI
                    if r.status_code != 200:
                        error_obj = {"error": f"Cloudflare Error {r.status_code}: {r.text}"}
                        yield f"data: {json.dumps(error_obj)}\n\n"
                        return
                    
                    for line in r.iter_lines():
                        if line:
                            yield f"{line.decode('utf-8')}\n\n"

            except Exception as e:
                # 2. Safely format proxy loop errors
                error_obj = {"error": f"Proxy Loop Error: {str(e)}"}
                yield f"data: {json.dumps(error_obj)}\n\n"
        
        return Response(stream_with_context(stream_response()), content_type='text/event-stream')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
