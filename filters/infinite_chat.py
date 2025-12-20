"""
title: InfiniteChat
author: thiswillbeyourgithub
version: 1.4.0
date: 2025-03-22
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
license: AGPLv3
description: A filter that keeps chats manageable by retaining only the last N messages.
"""

from pydantic import BaseModel, Field
import re
from typing import Optional, Callable, Any, List, Union
from loguru import logger


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]

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

    def _preserve_regex_content(self, messages: List[dict]) -> List[dict]:
        """
        Preserves content matching the regex pattern from messages that would be removed.
        Adds matching lines to the most recent user message.

        Args:
            messages: List of non-system messages
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
                logger.debug(
                    "InfiniteChat filter: No user message found to preserve content to"
                )
                return messages

            latest_user_msg = messages[latest_user_msg_idx]
            latest_content = latest_user_msg.get("content", "")

            # Check if the pattern already exists in the latest message
            if self._content_has_pattern(latest_content, pattern):
                logger.debug(
                    f"InfiniteChat filter: Pattern '{self.valves.preserve_regex}' already exists in latest message"
                )
                return messages

            # Search older messages for the pattern

            # Start with the second most recent user message and work backwards
            match = None
            for i in range(latest_user_msg_idx - 1, -1, -1):
                if "role" not in messages[i] or messages[i]["role"] != "user":
                    continue

                content = messages[i].get("content", "")

                match = self._content_has_pattern(content, pattern, return_match=True)
                if not match:
                    continue
                logger.debug(f"InfiniteChat filter: Found matching content: {match}")
                break

            # Add the preserved lines to the top of the latest user message
            # first extract the string of the last message
            if isinstance(latest_content, str):
                latest_content_str = latest_content
            elif isinstance(latest_content, list):
                for li in latest_content:
                    if li["type"] == "text":
                        latest_content_str = li["text"]
                        break
            else:
                raise ValueError(latest_content)

            if not match:
                logger.debug(
                    f"InfiniteChat filter: No content matching pattern '{self.valves.preserve_regex}' found in older messages"
                )
                return messages

            new_content = match + "\n" + latest_content_str
            logger.info(
                f"InfiniteChat filter: Readded line '{match}' to the latest user message"
            )

            # readd to the last message
            if isinstance(latest_content, str):
                messages[latest_user_msg_idx]["content"] = new_content
            elif isinstance(latest_content, list):
                for ili, li in enumerate(latest_content):
                    if li["type"] == "text":
                        messages[latest_user_msg_idx]["content"][ili][
                            "text"
                        ] = new_content
                        break
            else:
                raise ValueError(latest_content)
            return messages

        except re.error as e:
            logger.error(f"InfiniteChat filter: Error during regex matching: {str(e)}")
            return messages

    def _content_has_pattern(
        self,
        content: Union[str, List[dict], dict],
        pattern: re.Pattern,
        return_match: bool = False,
    ) -> Union[bool, str]:
        """
        Checks if the content already contains the pattern.

        Args:
            content: The content to check
            pattern: Compiled regex pattern

        Returns:
            True if the pattern is found in the content
        """
        if isinstance(content, dict):
            if content["type"] != "text":
                return False
            else:
                return self._content_has_pattern(content["text"], pattern, return_match)
        elif isinstance(content, list):
            vals = [
                self._content_has_pattern(cont, pattern, return_match)
                for cont in content
            ]
            if not any(vals):
                return False
            elif return_match:
                return [v for v in vals if isinstance(v, str)][0]
            else:
                return True

        if not content:
            return False

        for line in content.split("\n"):
            if pattern.search(line):
                return pattern.findall(line)[0]

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

        sys_message = [
            m for m in body["messages"] if "role" in m and m["role"] == "system"
        ]

        if self.valves.debug:
            await log(
                f"InfiniteChat filter: inlet: messages count before: {len(body['messages'])}, including {len(sys_message)} system message(s)"
            )

        # Separate user/assistant messages from system messages
        non_system_messages = [
            m for m in body["messages"] if ("role" not in m) or (m["role"] != "system")
        ]

        # Check if we need to preserve any content based on regex
        if self.valves.preserve_regex and len(non_system_messages) > keep:
            non_system_messages = self._preserve_regex_content(non_system_messages)

        # Apply the message limit
        body["messages"] = sys_message + non_system_messages[-keep:]

        if self.valves.debug:
            await emitter.success_update(
                f"InfiniteChat filter: inlet: messages count after: {len(body['messages'])}"
            )

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
