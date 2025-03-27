"""
title: Don't Accumulate Thoughts
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2025-03-27
license: GPLv3
description: Removes thinking blocks (<thinking>...</thinking>) from assistant messages to avoid resending them in chat history, saving costs and reducing token usage.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/dont-accumulate-thoughts
"""

import re
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from loguru import logger


class Filter:
    VERSION: str = "1.0.0"
    NAME: str = "DontAccumulateThoughts"

    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (lower numbers run first)."
        )
        debug: bool = Field(
            default=False,
            description="Enable debug logging"
        )
        thinking_pattern: str = Field(
            default=r"<thinking>.*?</thinking>",
            description="Regex pattern to match thinking blocks (supports multiline with (?s) flag)"
        )

    def __init__(self):
        """Initialize the filter with default values."""
        self.valves = self.Valves()

    def __init__(self):
        """Initialize the filter with default values."""
        self.valves = self.Valves()
        self._thinking_pattern = None
        self.thinking_regex = re.compile(self.valves.thinking_pattern, re.DOTALL)
        
    async def log(self, message: str, level="info", emitter=None) -> None:
        """Log a message."""
        getattr(logger, level)(f"[{self.NAME}] {message}")
        if emitter:
            if level == "info":
                if self.valves.debug:
                    await emitter.progress_update(f"[{self.NAME}] {message}")
            elif level == "debug":
                if self.valves.debug:
                    await emitter.progress_update(f"[{self.NAME}] {message}")
            elif level == "error":
                await emitter.error_update(f"[{self.NAME}] {message}")
                
    def filter_message(self, message: dict) -> dict:
        """
        Filter thinking blocks from a message.
        
        Args:
            message: The message dictionary to filter
            
        Returns:
            The filtered message dictionary
        """
        if message.get("role") != "assistant":
            return message
            
        content = message.get("content", "")
        if not content:
            return message
            
        # Remove thinking blocks
        filtered_content = self.thinking_regex.sub("", content).strip()
        
        # Create a new message with the filtered content
        filtered_message = message.copy()
        filtered_message["content"] = filtered_content
        
        return filtered_message

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        **kwargs
    ) -> dict:
        emitter = EventEmitter(__event_emitter__)
        
        await self.log("Processing inlet request", emitter=emitter)
        
        try:
            if "messages" in body:
                # Filter all assistant messages in the message history
                filtered_messages = []
                for message in body["messages"]:
                    filtered_message = self.filter_message(message)
                    filtered_messages.append(filtered_message)
                
                body["messages"] = filtered_messages
                await self.log(f"Filtered {len(filtered_messages)} messages", emitter=emitter)
            
            await self.log("Request processed successfully", emitter=emitter)
            if self.valves.debug:
                await emitter.success_update("Thinking blocks filtered successfully")
        except Exception as e:
            await self.log(f"Error in inlet: {str(e)}", level="error", emitter=emitter)
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

    async def emit(self, description: str = "Unknown State", status: str = "in_progress", done: bool = False):
        """Emit an event with the given parameters."""
        if self.event_emitter:
            await self.event_emitter({
                "description": description,
                "status": status,
                "done": done
            })
