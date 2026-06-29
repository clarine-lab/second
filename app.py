import os
import json 
import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Fireworks only requires a single API Key
API_KEY = os.getenv("FIREWORKS_API_KEY")

# Fireworks models require the 'accounts/fireworks/models/' prefix
DEFAULT_MODEL = "accounts/fireworks/models/llama-v3p1-8b-instruct" 
FIREWORKS_ENDPOINT = "https://api.fireworks.ai/inference/v1/chat/completions"

app = Flask(__name__)
CORS(app)

@app.route('/', methods=["GET"])
def health_check():
    return "Fireworks AI Proxy Online", 200

@app.route('/v1/chat/completions', strict_slashes=False, methods=["POST", "OPTIONS"])
@app.route('/chat/completions', strict_slashes=False, methods=["POST", "OPTIONS"])
def handle_proxy():
    # 1. The Preflight Catch
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
            "Content-Type": "application/json",
            "Accept": "text/event-stream" 
        }

        def stream_response():
            try:
                with requests.post(FIREWORKS_ENDPOINT, headers=headers, json=payload, stream=True, timeout=(15, 600)) as r:
                    if r.status_code != 200:
                        error_obj = {"error": f"Fireworks Error {r.status_code}: {r.text}"}
                        yield f"data: {json.dumps(error_obj)}\n\n"
                        return
                    
                    # Pass the SSE lines straight through
                    for line in r.iter_lines():
                        if line:
                            yield f"{line.decode('utf-8')}\n\n"

            except Exception as e:
                error_obj = {"error": f"Proxy Loop Error: {str(e)}"}
                yield f"data: {json.dumps(error_obj)}\n\n"
        
        return Response(stream_with_context(stream_response()), content_type='text/event-stream')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
