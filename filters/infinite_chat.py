"""
title: InfiniteChat
author: thiswillbeyourgithub
version: 1.3.0
date: 2025-03-22
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
license: GPLv3
description: A filter that keeps chats manageable by retaining only the last N messages.
"""

from pydantic import BaseModel, Field
import re
from typing import Optional, Callable, Any, List
from loguru import logger


class Filter:
    VERSION: str = "1.3.0"
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=False, 
            description="True to add emitter prints",
        )
        keep_messages: int = Field(
            default=2,
            description="Number of most recent messages to keep in the chat. This does not count the system message.",
        )
        preserve_regex: str = Field(
            default="",
            description="Regex pattern to identify content that should be preserved from older messages that would be removed. Matching lines will be copied to the top of the latest user message.",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def on_valves_updated(self):
        pass
        
    async def _preserve_regex_content(self, messages: List[dict], log_func) -> None:
        """
        Preserves content matching the regex pattern from messages that would be removed.
        Adds matching lines to the most recent user message.
        
        Args:
            messages: List of non-system messages
            log_func: Function to use for logging
        """
        try:
            # Compile the regex pattern
            pattern = re.compile(self.valves.preserve_regex)
            
            # Find the most recent user message
            latest_user_msg_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if "role" in messages[i] and messages[i]["role"] == "user":
                    latest_user_msg_idx = i
                    break
                    
            if latest_user_msg_idx is None:
                await log_func("No user message found to preserve content to")
                return
                
            latest_user_msg = messages[latest_user_msg_idx]
            latest_content = latest_user_msg.get("content", "")
            
            # Check if the pattern already exists in the latest message
            if self._content_has_pattern(latest_content, pattern):
                await log_func(f"Pattern '{self.valves.preserve_regex}' already exists in latest message")
                return
                
            # Search older messages for the pattern
            preserved_lines = []
            
            # Start with the second most recent user message and work backwards
            for i in range(latest_user_msg_idx - 1, -1, -1):
                if "role" not in messages[i] or messages[i]["role"] != "user":
                    continue
                    
                content = messages[i].get("content", "")
                if not content:
                    continue
                    
                # Check each line for a match
                for line in content.split('\n'):
                    if pattern.search(line):
                        preserved_lines.append(line)
                        await log_func(f"Found matching content: {line[:50]}{'...' if len(line) > 50 else ''}")
                        # Stop once we find a match
                        break
                        
                # If we found matches, stop searching
                if preserved_lines:
                    break
                    
            # Add the preserved lines to the top of the latest user message
            if preserved_lines:
                messages[latest_user_msg_idx]["content"] = '\n'.join(preserved_lines + [latest_content])
                await log_func(f"Added {len(preserved_lines)} preserved line(s) to the latest user message")
            else:
                await log_func(f"No content matching pattern '{self.valves.preserve_regex}' found in older messages")
                
        except re.error as e:
            await log_func(f"Invalid regex pattern: {str(e)}")
            
    def _content_has_pattern(self, content: str, pattern: re.Pattern) -> bool:
        """
        Checks if the content already contains the pattern.
        
        Args:
            content: The content to check
            pattern: Compiled regex pattern
            
        Returns:
            True if the pattern is found in the content
        """
        if not content:
            return False
            
        for line in content.split('\n'):
            if pattern.search(line):
                return True
                
        return False

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        # printer
        emitter = EventEmitter(__event_emitter__)
        async def log(message: str):
            if self.valves.debug:
                logger.info(f"InfiniteChat filter: inlet: {message}")
            await emitter.progress_update(message)

        keep = self.valves.keep_messages
        if keep < 2:
            await log("keep_messages must be at least 2, using default of 2")
            keep = 2

        sys_message = [m for m in body["messages"] if "role" in m and m["role"] == "system"]

        if self.valves.debug:
            await log(f"InfiniteChat filter: inlet: messages count before: {len(body['messages'])}, including {len(sys_message)} system message(s)")

        # Separate user/assistant messages from system messages
        non_system_messages = [m for m in body["messages"] if ("role" not in m) or (m["role"] != "system")]
        
        # Check if we need to preserve any content based on regex
        if self.valves.preserve_regex and len(non_system_messages) > keep:
            await self._preserve_regex_content(non_system_messages, await log)
        
        # Apply the message limit
        body["messages"] = sys_message + non_system_messages[-keep:]

        if self.valves.debug:
            await emitter.success_update(f"InfiniteChat filter: inlet: messages count after: {len(body['messages'])}")

        return body


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        logger.info(description)
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )
