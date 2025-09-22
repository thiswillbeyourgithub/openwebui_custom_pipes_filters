"""
title: Combine User Messages Filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2025-09-22
license: GPLv3
description: Combines all user messages into a single message and removes all assistant messages to improve LLM responses. Preserves files and images.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/combine_user_messages
"""

from typing import Any, Callable, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field
from loguru import logger


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]
    NAME: str = "Combine User Messages Filter"

    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (lower numbers run first).",
        )
        enabled: bool = Field(
            default=True, description="Enable or disable this filter"
        )
        debug: bool = Field(
            default=False, description="Enable debug logging"
        )
        message_separator: str = Field(
            default="\n\n---\n\n",
            description="Separator to use between combined user messages"
        )

    class UserValves(BaseModel):
        """User-specific configuration options for the filter."""

        enabled: bool = Field(
            default=True, description="Enable or disable this filter for the user"
        )

    def __init__(self):
        """Initialize the filter with default values."""
        self.valves = self.Valves()

    async def log(self, message: str, level="info") -> None:
        """Log a message."""
        getattr(logger, level)(f"[{self.NAME}] {message}")
        if level == "info":
            if self.valves.debug:
                await self.emitter.progress_update(f"[{self.NAME}] {message}")
        elif level == "debug":
            if self.valves.debug:
                await self.emitter.progress_update(f"[{self.NAME}] {message}")
        elif level == "error":
            await self.emitter.error_update(f"[{self.NAME}] {message}")

    def _extract_content_text(self, content: Union[str, List[Dict]]) -> str:
        """Extract text content from message content, handling both string and list formats."""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return " ".join(text_parts)
        return ""

    def _extract_files_and_images(self, content: Union[str, List[Dict]]) -> List[Dict]:
        """Extract file and image items from message content."""
        if isinstance(content, str):
            return []
        elif isinstance(content, list):
            media_items = []
            for item in content:
                if isinstance(item, dict) and item.get("type") in ["image_url", "file"]:
                    media_items.append(item)
            return media_items
        return []

    def _combine_user_messages(self, messages: List[Dict]) -> List[Dict]:
        """Combine all user messages into one, preserving system messages."""
        combined_messages = []
        user_texts = []
        all_files_and_images = []
        
        for message in messages:
            role = message.get("role", "")
            
            if role == "system":
                # Preserve system messages as-is
                combined_messages.append(message)
            elif role == "user":
                # Extract text and media from user messages
                content = message.get("content", "")
                text = self._extract_content_text(content)
                if text.strip():
                    user_texts.append(text.strip())
                
                # Collect files and images
                media_items = self._extract_files_and_images(content)
                all_files_and_images.extend(media_items)
            # Skip assistant messages completely
        
        # Create combined user message if we have any user content
        if user_texts or all_files_and_images:
            combined_content = []
            
            # Add text content
            if user_texts:
                combined_text = self.valves.message_separator.join(user_texts)
                combined_content.append({
                    "type": "text",
                    "text": combined_text
                })
            
            # Add all files and images
            combined_content.extend(all_files_and_images)
            
            # Use string format if only text, otherwise use list format
            if len(combined_content) == 1 and combined_content[0]["type"] == "text":
                content = combined_content[0]["text"]
            else:
                content = combined_content
            
            combined_user_message = {
                "role": "user",
                "content": content
            }
            combined_messages.append(combined_user_message)
        
        return combined_messages

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        **kwargs,
    ) -> dict:
        self.emitter = EventEmitter(__event_emitter__)
        
        # Check if filter is enabled
        if not self.valves.enabled:
            return body
            
        # Check user-specific settings
        user_valves = {}
        if __user__ and "valves" in __user__:
            user_valves = __user__.get("valves", {})
        
        if not user_valves.get("enabled", True):
            await self.log("Filter disabled for this user")
            return body

        await self.log("Processing inlet request")

        try:
            messages = body.get("messages", [])
            if not messages:
                await self.log("No messages found in body")
                return body

            original_count = len(messages)
            user_count = sum(1 for msg in messages if msg.get("role") == "user")
            assistant_count = sum(1 for msg in messages if msg.get("role") == "assistant")
            system_count = sum(1 for msg in messages if msg.get("role") == "system")

            await self.log(f"Original messages: {original_count} (system: {system_count}, user: {user_count}, assistant: {assistant_count})")

            # Combine user messages and remove assistant messages
            combined_messages = self._combine_user_messages(messages)
            body["messages"] = combined_messages

            new_count = len(combined_messages)
            await self.log(f"Combined messages: {new_count}")
            
            # Notify user that filter has been applied
            await self.emitter.progress_update(f"Combined {user_count} user messages into 1, removed {assistant_count} assistant messages")

            await self.log("Request processed successfully")
        except Exception as e:
            await self.log(f"Error in inlet: {str(e)}", level="error")
            
        return body

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        **kwargs,
    ) -> dict:
        self.emitter = EventEmitter(__event_emitter__)

        # Check if filter is enabled
        if not self.valves.enabled:
            return body
            
        # Check user-specific settings
        user_valves = {}
        if __user__ and "valves" in __user__:
            user_valves = __user__.get("valves", {})
        
        if not user_valves.get("enabled", True):
            return body

        await self.log("Processing outlet request")

        try:
            messages = body.get("messages", [])
            message_count = len(messages)
            
            system_count = sum(1 for msg in messages if msg.get("role") == "system")
            user_count = sum(1 for msg in messages if msg.get("role") == "user")
            assistant_count = sum(1 for msg in messages if msg.get("role") == "assistant")
            
            # Assert that we have the expected structure:
            # - 2 messages (1 user + 1 assistant) or 3 messages (1 system + 1 user + 1 assistant)
            expected_total = 2 if system_count == 0 else 3
            
            assert message_count == expected_total, (
                f"Expected {expected_total} messages after filtering "
                f"(system: {system_count}, user: {user_count}, assistant: {assistant_count}), "
                f"but got {message_count} messages"
            )
            
            assert user_count == 1, f"Expected exactly 1 user message, got {user_count}"
            assert assistant_count == 1, f"Expected exactly 1 assistant message, got {assistant_count}"
            assert system_count <= 1, f"Expected at most 1 system message, got {system_count}"

            await self.log(f"Outlet validation passed: {message_count} messages as expected")

        except Exception as e:
            await self.log(f"Error in outlet: {str(e)}", level="error")
            
        return body


class EventEmitter:
    """Helper class for emitting events to the client."""

    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        """Initialize with an event emitter function."""
        self.event_emitter = event_emitter

    async def progress_update(self, description: str):
        """Emit a progress update event."""
        await self.emit(description=description, status="in_progress", done=False)

    async def error_update(self, description: str):
        """Emit an error event."""
        await self.emit(description=description, status="error", done=True)

    async def success_update(self, description: str):
        """Emit a success event."""
        await self.emit(description=description, status="success", done=True)

    async def emit(
        self,
        description: str = "Unknown State",
        status: str = "in_progress",
        done: bool = False,
    ):
        """Emit an event with the given parameters."""
        if self.event_emitter:
            await self.event_emitter(
                {"description": description, "status": status, "done": done}
            )
