import os
import time
import json
import requests
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Your API_KEY environment variable will now need to be a Hugging Face Token (hf_...)
API_KEY = os.getenv("API_KEY")
# Hugging Face models require the full repository ID
DEFAULT_MODEL = "zai-org/GLM-4.7" 
HF_ENDPOINT = "https://router.huggingface.co/v1/chat/completions"

app = Flask(__name__)
CORS(app)

@app.route('/', methods=["GET"])
def health_check():
    return "Hugging Face Proxy Online", 200

@app.route('/v1/chat/completions', methods=["POST"])
@app.route('/chat/completions', methods=["POST"])
def handle_proxy():
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        current_model = data.get("model", DEFAULT_MODEL)

        # Removed NVIDIA-specific arguments (chat_template_kwargs, enable_thinking)
        # Hugging Face handles formatting natively via the v1/chat/completions endpoint
        payload = {
            "model": current_model,
            "messages": messages,
            "stream": True, 
            "temperature": data.get("temperature", 0.7),
            "max_tokens": data.get("max_tokens", 4096)
        }

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        def stream_response():
            # Initial heartbeat
            yield ": connection established\n\n"
            
            try:
                with requests.post(HF_ENDPOINT, headers=headers, json=payload, stream=True, timeout=(15, 600)) as r:
                    if r.status_code != 200:
                        err_snippet = r.raw.read(500).decode('utf-8', 'ignore')
                        # Format exactly how OpenAI sends errors
                        error_json = {
                            "error": {
                                "message": f"Hugging Face Error {r.status_code}: {err_snippet}",
                                "type": "api_error"
                            }
                        }
                        yield f"data: {json.dumps(error_json)}\n\n"
                        return

                    for line in r.iter_lines():
                        if not line:
                            continue
                            
                        decoded_line = line.decode('utf-8').strip()

                        # 1. Catch the DONE signal and terminate cleanly
                        if "[DONE]" in decoded_line:
                            yield "data: [DONE]\n\n"
                            break

                        # 2. Process only properly formatted SSE data lines
                        if decoded_line.startswith("data: "):
                            json_str = decoded_line[6:] # Strip "data: "
                            
                            try:
                                data_obj = json.loads(json_str)
                                choices = data_obj.get("choices", [])
                                
                                # Filter out empty choices
                                if not choices:
                                    continue
                                    
                                delta = choices[0].get("delta", {})
                                finish_reason = choices[0].get("finish_reason")
                                
                                content = delta.get("content")
                                
                                # Send heartbeat while model is processing
                                if content is None and finish_reason is None:
                                    yield ": heartbeat\n\n"
                                    continue
                                
                                # Rebuild clean delta
                                clean_delta = {}
                                if content is not None:
                                    clean_delta["content"] = content
                                    
                                clean_chunk = {
                                    "id": data_obj.get("id", "chatcmpl-hf-proxy"),
                                    "object": "chat.completion.chunk",
                                    "created": data_obj.get("created", int(time.time())),
                                    "model": data_obj.get("model", current_model),
                                    "choices": [{
                                        "index": choices[0].get("index", 0),
                                        "delta": clean_delta,
                                        "finish_reason": finish_reason
                                    }]
                                }
                                
                                yield f"data: {json.dumps(clean_chunk)}\n\n"
                                
                            except json.JSONDecodeError:
                                yield f"{decoded_line}\n\n"

            except requests.exceptions.Timeout:
                timeout_json = {"error": {"message": "Hugging Face Timeout: The model took too long to respond.", "type": "timeout"}}
                yield f"data: {json.dumps(timeout_json)}\n\n"
            except Exception as e:
                loop_err_json = {"error": {"message": f"Proxy Loop Error: {str(e)}", "type": "proxy_error"}}
                yield f"data: {json.dumps(loop_err_json)}\n\n"
            
        return Response(stream_with_context(stream_response()), content_type='text/event-stream')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
