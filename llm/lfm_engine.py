"""LFM2.5-Audio GGUF engine wrapper."""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Generator, Iterable, List, Optional

import socket

from dotenv import load_dotenv
from openai import OpenAI


@dataclass
class LFMAudioEngine:
    model_dir: str = "models/lfm-audio"
    runner_path: str = "runners/llama-liquid-audio-ubuntu-x64/llama-liquid-audio-server"
    port: int = 8090

    def __post_init__(self) -> None:
        self.server_process: Optional[subprocess.Popen] = None
        self._client: Optional[OpenAI] = None
        self._log_file: Optional[object] = None
        self.system_prompt: str = "Respond with interleaved text and audio."
        self.context_prompt: str = ""
        load_dotenv()
        try:
            with open("config/PROXY.md", "r", encoding="utf-8") as f:
                self.context_prompt = f.read().strip()
        except FileNotFoundError:
            self.context_prompt = ""

    @property
    def model_path(self) -> str:
        return os.path.join(self.model_dir, "LFM2.5-Audio-1.5B-Q4_0.gguf")

    @property
    def mmproj_path(self) -> str:
        return os.path.join(self.model_dir, "mmproj-LFM2.5-Audio-1.5B-Q4_0.gguf")

    @property
    def vocoder_path(self) -> str:
        return os.path.join(self.model_dir, "vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf")

    @property
    def tokenizer_path(self) -> str:
        return os.path.join(self.model_dir, "tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf")

    def _client_for_port(self) -> OpenAI:
        if not self._client:
            self._client = OpenAI(base_url=f"http://127.0.0.1:{self.port}/v1", api_key="dummy")
        return self._client

    def _port_open(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                return True
        except OSError:
            return False

    def start_server(self, timeout_s: int = 600) -> None:
        if self.server_process and self.server_process.poll() is None:
            return
        # If a server is already running externally, just connect.
        if self._port_open():
            return
        cmd = [
            self.runner_path,
            "-m",
            self.model_path,
            "-mm",
            self.mmproj_path,
            "-mv",
            self.vocoder_path,
            "--tts-speaker-file",
            self.tokenizer_path,
            "--port",
            str(self.port),
        ]
        env = os.environ.copy()
        runner_dir = os.path.dirname(self.runner_path)
        env["LD_LIBRARY_PATH"] = f"{runner_dir}:{env.get('LD_LIBRARY_PATH', '')}"
        self._log_file = open("lfm_server.log", "a", encoding="utf-8")
        self.server_process = subprocess.Popen(cmd, env=env, stdout=self._log_file, stderr=subprocess.STDOUT)
        self._wait_ready(timeout_s=timeout_s)

    def _wait_ready(self, timeout_s: int = 600) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            if self._port_open():
                return
            time.sleep(1.0)
        raise RuntimeError("LFM server did not become ready in time")

    def stop_server(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
        self._log_file = None
        self.server_process = None

    def chat(self, messages: List[dict], max_tokens: int = 512, stream: bool = False) -> str | Generator[str, None, None]:
        client = self._client_for_port()
        filtered: List[dict] = []
        for msg in messages:
            role = msg.get("role")
            if role == "system":
                continue
            content = msg.get("content", "")
            if role == "assistant":
                filtered.append({"role": "user", "content": f"Assistant: {content}"})
            else:
                filtered.append({"role": "user", "content": content})
        prepared: List[dict] = [{"role": "system", "content": self.system_prompt}]
        if self.context_prompt:
            prepared.append({"role": "user", "content": f"Context:\n{self.context_prompt}"})
        prepared.extend(filtered)

        def _iter() -> Generator[str, None, None]:
            for chunk in client.chat.completions.create(
                model="LFM2.5-Audio-1.5B",
                messages=prepared,
                max_tokens=max_tokens,
                stream=True,
            ):
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        if stream:
            return _iter()

        text = ""
        for part in _iter():
            text += part
        return text

    def chat_stream(self, messages: List[dict], max_tokens: int = 512) -> Generator[str, None, None]:
        return self.chat(messages=messages, max_tokens=max_tokens, stream=True)  # type: ignore[return-value]

    def __enter__(self) -> "LFMAudioEngine":
        self.start_server()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop_server()
