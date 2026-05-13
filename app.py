import os
import time
import json
import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

API_KEY = os.getenv("API_KEY")
# Case sensitivity: Some NIM versions prefer lowercase 'pro'
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-pro"
NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"

app = Flask(__name__)
CORS(app)

@app.route('/', methods=["GET"])
def health_check():
    return "NVIDIA Pro-Ready Proxy Online", 200

@app.route('/v1/chat/completions', methods=["POST"])
@app.route('/chat/completions', methods=["POST"])
def handle_proxy():
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        current_model = data.get("model", DEFAULT_MODEL)

        payload = {
            "model": current_model,
            "messages": messages,
            "stream": True, # Force streaming for Pro
            "temperature": data.get("temperature", 0.9),
            "max_tokens": data.get("max_tokens", 4096),
            "chat_template_kwargs": {
                "enable_thinking": True,
                "thinking": True
            }
        }

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        def stream_response():
            # Initial heartbeat
            yield ": connection established\n\n"
            
            try:
                with requests.post(NIM_ENDPOINT, headers=headers, json=payload, stream=True, timeout=(15, 600)) as r:
                    if r.status_code != 200:
                        err_snippet = r.raw.read(500).decode('utf-8', 'ignore')
                        yield f"data: {json.dumps({'error': 'NVIDIA Error', 'details': err_snippet})}\n\n"
                        return

                    for line in r.iter_lines():
                        if not line:
                            continue
                            
                        decoded_line = line.decode('utf-8').strip()

                        # 1. Catch the DONE signal and terminate cleanly
                        if "[DONE]" in decoded_line:
                            yield "data: [DONE]\n\n"
                            break

                        # 2. Skip usage chunks completely
                        if '"choices":[]' in decoded_line or '"usage":' in decoded_line:
                            continue

                        # 3. Filter out "Reasoning" chunks for JanitorAI compatibility
                        if '"reasoning"' in decoded_line or '"reasoning_content"' in decoded_line:
                            # We just ignore these lines completely so the front-end never sees them.
                            continue
                            
                        # 4. Ensure proper SSE formatting for actual content
                        if decoded_line.startswith("data: "):
                            yield f"{decoded_line}\n\n"
                        else:
                            yield f"data: {decoded_line}\n\n"

            except requests.exceptions.Timeout:
                yield f"data: {json.dumps({'error': 'NVIDIA Timeout', 'details': 'The model took too long.'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': 'Proxy Loop Error', 'details': str(e)})}\n\n"

        return Response(stream_with_context(stream_response()), content_type='text/event-stream')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
