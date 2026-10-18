"""Runs ONLY on Hugging Face ZeroGPU. Never import this from the StudyRoute backend."""
from __future__ import annotations

import hmac
import json
import os

import gradio as gr
import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
# Set this as a Space Secret, never in source. Match HF_SPACE_APP_SECRET in StudyRoute.
APP_SECRET = os.environ.get("SPACE_APP_SECRET", "")
if len(APP_SECRET) < 32:
    raise RuntimeError("Set a random SPACE_APP_SECRET of at least 32 characters in Space Settings.")

tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, trust_remote_code=False)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, revision=REVISION, torch_dtype=torch.bfloat16, device_map="cpu",
    low_cpu_mem_usage=True, trust_remote_code=False, use_safetensors=True,
).eval()


@spaces.GPU(duration=45)
def generate(system: str, user: str) -> str:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")
    if inputs.input_ids.shape[-1] > 7000:
        raise gr.Error("Request context is too large. Start a shorter conversation.")
    try:
        model.to("cuda")
        inputs = inputs.to("cuda")
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=768, do_sample=False)
        return tokenizer.decode(output[0][inputs.input_ids.shape[-1]:], skip_special_tokens=True)
    finally:
        model.to("cpu")
        torch.cuda.empty_cache()


def respond(payload: str, app_secret: str) -> str:
    # Reject before allocating GPU. Do not echo submitted credentials or prompts.
    if not hmac.compare_digest(app_secret, APP_SECRET):
        raise gr.Error("Space access rejected.")
    if len(payload) > 50000:
        raise gr.Error("Request too large.")
    try:
        data = json.loads(payload)
        system, user = data["system"], data["user"]
        if not isinstance(system, str) or not isinstance(user, str):
            raise ValueError("Invalid request")
    except (ValueError, KeyError, TypeError):
        raise gr.Error("Invalid request format.") from None
    return generate(system, user)


with gr.Blocks() as demo:
    gr.Markdown("# StudyRoute remote model\nSynthetic data only. API protected by a Space secret.")
    payload = gr.Textbox(label="Request JSON", lines=3)
    secret = gr.Textbox(label="Space app secret", type="password")
    output = gr.Textbox(label="Response JSON")
    gr.Button("Run").click(respond, inputs=[payload, secret], outputs=output,
                           api_name="respond", concurrency_limit=1)

# Queue availability is not a guaranteed ETA. No prompts are logged by this application.
demo.queue(max_size=8).launch(show_error=True)
