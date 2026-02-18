"""LFM2.5-1.2B-Thinking engine wrapper."""
from __future__ import annotations

import ast
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Dict, Generator, Iterable, List, Optional

import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer


_TOOL_BLOCK_RE = re.compile(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", re.DOTALL)
_CALL_RE = re.compile(r"\[(.+?)\]", re.DOTALL)


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, object]


class LFMEngine:
    """Wrapper for LiquidAI LFM2.5-1.2B-Thinking."""

    def __init__(self, model_id: str = "LiquidAI/LFM2.5-1.2B-Thinking", device: str = "cpu", dtype: str = "bfloat16") -> None:
        load_dotenv()
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
        torch_dtype = getattr(torch, dtype) if hasattr(torch, dtype) else torch.float32
        if device == "cpu" and torch_dtype == torch.bfloat16 and not torch.xpu.is_available():
            # CPU bfloat16 may be unsupported on some builds
            torch_dtype = torch.float32

        self.tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            token=token,
            torch_dtype=torch_dtype,
            device_map="auto" if device != "cpu" else None,
        )
        if device == "cpu":
            self.model.to("cpu")
        self.model.eval()

    def _apply_tools(self, messages: List[Dict], tools: Optional[List[Dict]]) -> List[Dict]:
        if not tools:
            return messages
        tools_json = json.dumps(tools, ensure_ascii=False)
        messages = [m.copy() for m in messages]
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = f"{messages[0].get('content', '')}\n\nList of tools: {tools_json}"
        else:
            messages.insert(0, {"role": "system", "content": f"List of tools: {tools_json}"})
        return messages

    def _format_prompt(self, messages: List[Dict], tools: Optional[List[Dict]]) -> str:
        formatted = self._apply_tools(messages, tools)
        return self.tokenizer.apply_chat_template(formatted, tokenize=False, add_generation_prompt=True)

    def generate(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 512,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        prompt = self._format_prompt(messages, tools)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        gen_kwargs = dict(
            max_new_tokens=max_tokens,
            temperature=0.05,
            top_k=50,
            repetition_penalty=1.05,
            do_sample=True,
        )
        if not stream:
            output = self.model.generate(**inputs, **gen_kwargs)
            text = self.tokenizer.decode(output[0], skip_special_tokens=True)
            return text[len(self.tokenizer.decode(inputs["input_ids"][0], skip_special_tokens=True)) :].strip()

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        thread = threading.Thread(target=self.model.generate, kwargs={**inputs, **gen_kwargs, "streamer": streamer})
        thread.start()

        def _iter() -> Generator[str, None, None]:
            for token in streamer:
                yield token
            thread.join()

        return _iter()

    def parse_tool_calls(self, response: str) -> List[Dict]:
        calls: List[Dict] = []
        for block in _TOOL_BLOCK_RE.findall(response):
            for call_txt in _CALL_RE.findall(block):
                parsed = self._parse_call(call_txt)
                if parsed:
                    calls.append(parsed)
        return calls

    def _parse_call(self, call_txt: str) -> Optional[Dict]:
        try:
            expr = ast.parse(call_txt, mode="eval").body
        except SyntaxError:
            return None
        if not isinstance(expr, ast.Call):
            return None
        name = expr.func.id if isinstance(expr.func, ast.Name) else None
        if not name:
            return None
        kwargs: Dict[str, object] = {}
        for kw in expr.keywords:
            kwargs[kw.arg] = ast.literal_eval(kw.value)
        return {"name": name, "arguments": kwargs}

    def format_tool_result(self, tool_name: str, result: object) -> Dict:
        return {"role": "tool", "name": tool_name, "content": json.dumps(result, ensure_ascii=False)}
