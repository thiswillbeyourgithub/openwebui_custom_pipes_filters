"""
title: User Tools Output Filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2023-07-12
license: GPLv3
description: Extracts tool results from HTML details tags and displays them more prominently
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/userToolsOutput
"""

from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from loguru import logger
import re
import html
from bs4 import BeautifulSoup


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]
    NAME: str = "userToolsOutput"

    class Valves(BaseModel):
        priority: int = Field(
            default=-10,
            description="Priority level for the filter operations (lower numbers run last).",
        )
        pattern_start: str = Field(
            default="<userToolsOutput>",
            description="Start pattern to match for extracting tool output",
        )
        pattern_end: str = Field(
            default="</userToolsOutput>",
            description="End pattern to match for extracting tool output",
        )
        debug: bool = Field(
            default=False,
            description="Enable debug logging"
        )

    class UserValves(BaseModel):
        """User-specific configuration options for the filter."""

        enabled: bool = Field(
            default=True, description="Enable or disable this filter for the user"
        )

    def __init__(self):
        """Initialize the filter with default values."""
        self.valves = self.Valves()
        self.emitter = None

    async def log(self, message: str, level="info") -> None:
        """Log a message."""
        getattr(logger, level)(f"[{self.NAME}] {message}")
        if not self.emitter:
            return

        if level == "info":
            if hasattr(self.valves, 'debug') and self.valves.debug:
                await self.emitter.progress_update(f"[{self.NAME}] {message}")
        elif level == "debug":
            if hasattr(self.valves, 'debug') and self.valves.debug:
                await self.emitter.progress_update(f"[{self.NAME}] {message}")
        elif level == "error":
            await self.emitter.error_update(f"[{self.NAME}] {message}")


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

        if __user__ and __user__.get("valves"):
            user_valves = dict(__user__.get("valves", {}))
        else:
            user_valves = {}

        await self.log("Processing outlet request")

        try:
            # Ensure messages exist in the body
            if "messages" not in body:
                await self.log("No messages found in body", level="debug")
                return body

            # Process each message
            for i, message in enumerate(body["messages"]):
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue

                await self.log(f"Processing assistant message {i}", level="debug")

                # Handle content as string or list of dict
                if "content" in message:
                    content = message["content"]

                    if isinstance(content, str):
                        # Process string content
                        message["content"] = await self._process_html_content(content)
                    elif isinstance(content, list):
                        # Process list of content items (multi-modal)
                        for j, item in enumerate(content):
                            if isinstance(item, dict) and "text" in item:
                                content[j]["text"] = await self._process_html_content(item["text"])
                            elif isinstance(item, dict) and "content" in item:
                                content[j]["content"] = await self._process_html_content(item["content"])

                # Handle legacy "body" key
                elif "body" in message:
                    message["body"] = await self._process_html_content(message["body"])

            await self.log("Tool outputs extracted and repositioned successfully")

        except Exception as e:
            await self.log(f"Error in outlet: {str(e)}", level="error")

        return body

    async def _process_html_content(self, content: str) -> str:
        """Process HTML content to extract and reposition tool outputs."""
        if not content or "<details" not in content:
            return content

        try:
            soup = BeautifulSoup(content, 'html.parser')
            details_tags = soup.find_all("details")

            if not details_tags:
                return content

            await self.log(f"Found {len(details_tags)} details tags", level="debug")

            pattern = re.compile(
                f"{re.escape(self.valves.pattern_start)}.*?{re.escape(self.valves.pattern_end)}",
                re.MULTILINE | re.DOTALL
            )

            for details in details_tags:
                if "result" not in details.attrs:
                    continue

                result_content = html.unescape(details.attrs.get("result", ""))

                # Find all matches of the pattern
                matches = pattern.findall(result_content)

                if not matches:
                    continue

                await self.log(f"Found {len(matches)} matches in details", level="debug")

                # Remove the matches from the result attribute
                cleaned_result = result_content
                for match in matches:
                    cleaned_result = cleaned_result.replace(match, "").strip()

                # Update the result attribute with cleaned content
                details.attrs["result"] = html.escape(cleaned_result)

                # Add the extracted content after the details tag
                for match in matches:
                    extracted_div = soup.new_tag("div")
                    extracted_div.attrs["class"] = "extracted-tool-result"
                    extracted_div.append(BeautifulSoup(match, 'html.parser'))
                    details.insert_after(extracted_div)

            return str(soup)

        except Exception as e:
            await self.log(f"Error processing HTML content: {str(e)}", level="error")
            return content


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
