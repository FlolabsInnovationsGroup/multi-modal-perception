import os
# Import UnifiedPipeline directly from client.py
from client import UnifiedPipeline

# 1. Initialize the pipeline with the JarvisLabs port 8000 URL
JARVIS_URL = "https://f3bf514665991-6007.notebooksn.jarvislabs.net"
pipeline = UnifiedPipeline(jarvis_endpoint="http://localhost:6007")

# 2. Test JarvisLabs GPU endpoint remotely
print("--- 1. Querying JarvisLabs GPU ---")
jarvis_res = pipeline.generate(
    prompt="What animal is on the candy?",
    image="https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/p-blog/candy.JPG",
    model="openbmb/MiniCPM-V-4.6",
    provider="jarvis",
    max_tokens=2048,
)

print(f"Output     : {jarvis_res[0]}")
print(f"Token Usage: {jarvis_res[1]}")
print(f"Model      : {jarvis_res[2]}\n")

# 3. Test OpenAI (Optional)
# print("--- 2. Querying OpenAI ---")
# openai_res = pipeline.generate(
#     prompt="Describe what you see in this picture.",
#     image="https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/p-blog/candy.JPG",
#     model="gpt-4o",
#     provider="openai",
#     api_key=os.getenv("OPENAI_API_KEY")
# )
# print(f"Output     : {openai_res[0]}")
# print(f"Token Usage: {openai_res[1]}")
# print(f"Model      : {openai_res[2]}\n")

# 4. Test Anthropic (Optional)
# print("--- 3. Querying Anthropic ---")
# claude_res = pipeline.generate(
#     prompt="Describe what you see in this picture.",
#     image="https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/p-blog/candy.JPG",
#     model="claude-3-5-sonnet-20241022",
#     provider="anthropic",
#     api_key=os.getenv("ANTHROPIC_API_KEY")
# )
# print(f"Output     : {claude_res[0]}")
# print(f"Token Usage: {claude_res[1]}")
# print(f"Model      : {claude_res[2]}")