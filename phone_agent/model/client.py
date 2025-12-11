"""Model client for AI inference using OpenAI-compatible API."""

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


@dataclass
class ModelConfig:
    """Configuration for the AI model."""

    base_url: str = "https://api-inference.modelscope.cn/v1"
    api_key: str = "ms-3dd3f247-aa7d-4586-b2bf-acee47e2d213"
    model_name: str = "ZhipuAI/AutoGLM-Phone-9B"
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Response from the AI model."""

    thinking: str
    action: str
    raw_content: str


class ModelClient:
    """
    Client for interacting with OpenAI-compatible vision-language models.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self.client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)

    def request(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """
        Send a request to the model.

        Args:
            messages: List of message dictionaries in OpenAI format.

        Returns:
            ModelResponse containing thinking and action.

        Raises:
            ValueError: If the response cannot be parsed.
        """
        kwargs = {
            "messages": messages,
            "model": self.config.model_name,
            # "max_tokens": self.config.max_tokens,
            "temperature": 0.01,
            "top_p": 0.1,
            "stream": True,
        }

        # if self.config.extra_body:
        #     kwargs["extra_body"] = self.config.extra_body

        response = self.client.chat.completions.create(**kwargs)

        raw_content = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                raw_content += chunk.choices[0].delta.content

        # Parse thinking and action from response
        thinking, action = self._parse_response(raw_content)

        return ModelResponse(thinking=thinking, action=action, raw_content=raw_content)

    def _parse_response(self, content: str) -> tuple[str, str]:
        """
        Parse the model response into thinking and action parts.

        Args:
            content: Raw response content.

        Returns:
            Tuple of (thinking, action).
        """
        content = content.strip()
        
        # Case 1: Standard format with <answer> tag
        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        # Case 2: No <answer> tag, but has <think> tag
        if "<think>" in content and "</think>" in content:
            parts = content.split("</think>", 1)
            thinking = parts[0].replace("<think>", "").strip()
            action = parts[1].strip()
            return thinking, action

        # Case 3: No tags, try to find action pattern
        # Look for the start of the action (e.g., {action=, do(, finish()
        action_markers = ["{action=", "do(", "finish("]
        first_marker_pos = len(content)
        
        for marker in action_markers:
            pos = content.find(marker)
            if pos != -1 and pos < first_marker_pos:
                first_marker_pos = pos
        
        if first_marker_pos < len(content):
            thinking = content[:first_marker_pos].strip()
            action = content[first_marker_pos:].strip()
            return thinking, action

        # Case 4: Fallback, treat everything as action (or thinking?)
        # If it looks like a JSON/Dict, it's an action
        if content.startswith("{") or content.startswith("do(") or content.startswith("finish("):
            return "", content
            
        # Otherwise, it might be just thinking or a malformed response
        return content, ""


class MessageBuilder:
    """Helper class for building conversation messages."""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        """Create a system message."""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Create a user message with optional image.

        Args:
            text: Text content.
            image_base64: Optional base64-encoded image.

        Returns:
            Message dictionary.
        """
        content = []

        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        content.append({"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        """Create an assistant message."""
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """
        Remove image content from a message to save context space.

        Args:
            message: Message dictionary.

        Returns:
            Message with images removed.
        """
        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"] if item.get("type") == "text"
            ]
        return message

    @staticmethod
    def build_screen_info(current_app: str, **extra_info) -> str:
        """
        Build screen info string for the model.

        Args:
            current_app: Current app name.
            **extra_info: Additional info to include.

        Returns:
            JSON string with screen info.
        """
        info = {"current_app": current_app, **extra_info}
        return json.dumps(info, ensure_ascii=False)
