from abc import ABC, abstractmethod
import base64
import io
import json
import mimetypes
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Union
from PIL import Image
import requests

__all__ = [
    "UnifiedPipeline",
    "RemoteJarvisProvider",
    "OpenAIProvider",
    "AnthropicProvider",
]


def prepare_image(image_input: Union[str, bytes, Image.Image]) -> Dict[str, str]:
    if isinstance(image_input, Image.Image):
        buf = io.BytesIO()
        image_input.convert("RGB").save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {
            "base64": b64,
            "mime_type": "image/jpeg",
            "data_url": f"data:image/jpeg;base64,{b64}",
        }
    elif isinstance(image_input, bytes):
        b64 = base64.b64encode(image_input).decode("utf-8")
        return {
            "base64": b64,
            "mime_type": "image/jpeg",
            "data_url": f"data:image/jpeg;base64,{b64}",
        }
    elif isinstance(image_input, str):
        if image_input.startswith(("http://", "https://")):
            return {
                "base64": "",
                "mime_type": "image/jpeg",
                "data_url": image_input,
            }
        elif os.path.isfile(image_input):
            mime_type = (
                mimetypes.guess_type(image_input)[0] or "image/jpeg"
            )
            with open(image_input, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return {
                "base64": b64,
                "mime_type": mime_type,
                "data_url": f"data:{mime_type};base64,{b64}",
            }
        elif image_input.startswith("data:image"):
            header, b64 = image_input.split(",", 1)
            mime = header.split(";")[0].split(":")[1]
            return {"base64": b64, "mime_type": mime, "data_url": image_input}
    raise ValueError(f"Invalid image: {image_input}")


class BaseLLMProvider(ABC):

    @abstractmethod
    def generate(
        self,
        prompt: str,
        image: Optional[Union[str, bytes, Image.Image]] = None,
        model: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> List[Union[str, Dict[str, int]]]:
        pass


class RemoteJarvisProvider(BaseLLMProvider):

    def __init__(
        self, endpoint: str, machine_id: Optional[Union[int, str]] = None
    ):
        self.endpoint = endpoint.rstrip("/")
        self.machine_id = str(machine_id) if machine_id else None

    def _ensure_instance_running(self):
        try:
            res = subprocess.run(
                ["jl", "list", "--json"], capture_output=True, text=True
            )
            if res.returncode != 0 or not res.stdout.strip():
                return

            stdout_clean = res.stdout.strip()
            start_idx = min(
                [
                    i
                    for i in (stdout_clean.find("["), stdout_clean.find("{"))
                    if i != -1
                ],
                default=0,
            )
            data = json.loads(stdout_clean[start_idx:])

            inst_list = []
            if isinstance(data, list):
                inst_list = [i for i in data if isinstance(i, dict)]
            elif isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list):
                        inst_list.extend(
                            [item for item in val if isinstance(item, dict)]
                        )
                    elif isinstance(val, dict):
                        inst_list.append(val)
                if not inst_list:
                    inst_list = [data]

            target = None
            if self.machine_id:
                target = next(
                    (
                        i
                        for i in inst_list
                        if str(
                            i.get("machine_id")
                            or i.get("id")
                            or i.get("machineId")
                        )
                        == self.machine_id
                    ),
                    None,
                )
            elif inst_list:
                target = inst_list[0]

            if target:
                status = str(
                    target.get("status")
                    or target.get("state")
                    or target.get("instance_status")
                    or ""
                ).lower()
                if status in ("paused", "pausing"):
                    mid = str(
                        target.get("machine_id")
                        or target.get("id")
                        or target.get("machineId")
                    )
                    print(
                        f"[Client] Instance {mid} is currently Paused. Running 'jl resume'..."
                    )
                    subprocess.run(["jl", "resume", mid, "--yes"], check=True)
                    print(
                        "[Client] Instance is now Running! Waiting for inference server to boot..."
                    )
                    self._wait_for_server()

        except Exception as e:
            print(f"[Client notice] CLI status check: {e}")

    def _wait_for_server(self, timeout: int = 120):
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(f"{self.endpoint}/health", timeout=3)
                if resp.status_code == 200:
                    print("[Client] Inference server is online!")
                    return
            except Exception:
                pass
            time.sleep(3)

    def generate(
        self,
        prompt: str,
        image: Optional[Union[str, bytes, Image.Image]] = None,
        model: str = "openbmb/MiniCPM-V-4.6",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> List[Union[str, Dict[str, int]]]:
        self._ensure_instance_running()

        url = f"{self.endpoint}/v1/generate"
        payload = {
            "prompt": prompt,
            "image": prepare_image(image)["data_url"] if image else None,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return [data["output"], data["usage"], data["model"]]


class OpenAIProvider(BaseLLMProvider):

    def __init__(self, api_key: Optional[str] = None):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def generate(
        self,
        prompt: str,
        image: Optional[Union[str, bytes, Image.Image]] = None,
        model: str = "gpt-4o",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> List[Union[str, Dict[str, int]]]:
        content = (
            [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": prepare_image(image)["data_url"]},
                },
            ]
            if image
            else prompt
        )
        res = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        return [
            res.choices[0].message.content or "",
            {
                "prompt_tokens": res.usage.prompt_tokens if res.usage else 0,
                "completion_tokens": res.usage.completion_tokens
                if res.usage
                else 0,
                "total_tokens": res.usage.total_tokens if res.usage else 0,
            },
            model,
        ]


class AnthropicProvider(BaseLLMProvider):

    def __init__(self, api_key: Optional[str] = None):
        from anthropic import Anthropic

        self.client = Anthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )

    def generate(
        self,
        prompt: str,
        image: Optional[Union[str, bytes, Image.Image]] = None,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> List[Union[str, Dict[str, int]]]:
        if image:
            img = prepare_image(image)
            if not img["base64"] and img["data_url"].startswith("http"):
                r = requests.get(img["data_url"], timeout=15)
                img["base64"] = base64.b64encode(r.content).decode("utf-8")
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img["mime_type"],
                        "data": img["base64"],
                    },
                },
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt

        res = self.client.messages.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        return [
            "".join([b.text for b in res.content]) if res.content else "",
            {
                "prompt_tokens": res.usage.input_tokens,
                "completion_tokens": res.usage.output_tokens,
                "total_tokens": res.usage.input_tokens
                + res.usage.output_tokens,
            },
            model,
        ]


class UnifiedPipeline:

    def __init__(
        self,
        jarvis_endpoint: str,
        machine_id: Optional[Union[int, str]] = None,
    ):
        self.providers = {
            "jarvis": RemoteJarvisProvider(
                endpoint=jarvis_endpoint, machine_id=machine_id
            ),
            "openai": None,
            "anthropic": None,
        }

    def generate(
        self,
        prompt: str,
        image: Optional[Union[str, bytes, Image.Image]] = None,
        model: str = "openbmb/MiniCPM-V-4.6",
        provider: str = "jarvis",
        api_key: Optional[str] = None,
        max_tokens: int = 2048,
        **kwargs,
    ) -> List[Union[str, Dict[str, int]]]:
        provider = provider.lower()
        if provider == "jarvis":
            client = self.providers["jarvis"]
        elif provider == "openai":
            if not self.providers["openai"] or api_key:
                self.providers["openai"] = OpenAIProvider(api_key=api_key)
            client = self.providers["openai"]
        elif provider == "anthropic":
            if not self.providers["anthropic"] or api_key:
                self.providers["anthropic"] = AnthropicProvider(api_key=api_key)
            client = self.providers["anthropic"]
        else:
            raise ValueError(f"Unknown provider: {provider}")

        return client.generate(
            prompt=prompt,
            image=image,
            model=model,
            max_tokens=max_tokens,
            **kwargs,
        )