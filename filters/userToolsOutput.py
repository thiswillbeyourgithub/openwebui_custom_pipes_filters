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
                        # Process string content and get extracted parts
                        processed_content, extracted_parts = await self._process_html_content(content)
                        # Combine the processed content with the extracted parts at the end
                        if extracted_parts:
                            message["content"] = processed_content + "\n\n" + "\n\n".join(extracted_parts)
                        else:
                            message["content"] = processed_content
                    elif isinstance(content, list):
                        # Process list of content items (multi-modal)
                        all_extracted_parts = []
                        for j, item in enumerate(content):
                            if isinstance(item, dict) and "text" in item:
                                processed_text, extracted_parts = await self._process_html_content(item["text"])
                                content[j]["text"] = processed_text
                                all_extracted_parts.extend(extracted_parts)
                            elif isinstance(item, dict) and "content" in item:
                                processed_content, extracted_parts = await self._process_html_content(item["content"])
                                content[j]["content"] = processed_content
                                all_extracted_parts.extend(extracted_parts)
                        
                        # Append extracted parts at the end of the content list
                        if all_extracted_parts:
                            content.append({"text": "\n\n" + "\n\n".join(all_extracted_parts), "type": "text"})

                # Handle legacy "body" key
                elif "body" in message:
                    processed_body, extracted_parts = await self._process_html_content(message["body"])
                    if extracted_parts:
                        message["body"] = processed_body + "\n\n" + "\n\n".join(extracted_parts)
                    else:
                        message["body"] = processed_body

            await self.log("Tool outputs extracted and repositioned successfully")

        except Exception as e:
            await self.log(f"Error in outlet: {str(e)}", level="error")

        return body

    async def _process_html_content(self, content: str) -> tuple[str, list[str]]:
        """
        Process HTML content to extract tool outputs.
        
        Returns:
            tuple: (processed_content, list_of_extracted_contents)
        """
        if not content or "<details" not in content:
            await self.log("No details tags in content, skipping", level="debug")
            return content, []

        try:
            await self.log(f"Content length before processing: {len(content)}", level="debug")
            await self.log(f"Content snippet: {content[:100]}...", level="debug")

            soup = BeautifulSoup(content, 'html.parser')
            details_tags = soup.find_all("details")

            if not details_tags:
                await self.log("No details tags found by BeautifulSoup", level="debug")
                return content, []

            await self.log(f"Found {len(details_tags)} details tags", level="debug")

            # Log details tags attributes
            for i, tag in enumerate(details_tags):
                await self.log(f"Details tag {i} attrs: {tag.attrs}", level="debug")

            # Create pattern with a capture group to extract only content between tags
            pattern_str = f"{re.escape(self.valves.pattern_start)}(.*?){re.escape(self.valves.pattern_end)}"
            await self.log(f"Pattern string: {pattern_str}", level="debug")

            pattern = re.compile(
                pattern_str,
                re.MULTILINE | re.DOTALL
            )

            # List to collect extracted content
            extracted_contents = []

            for i, details in enumerate(details_tags):
                await self.log(f"Processing details tag {i}", level="debug")

                if "result" not in details.attrs:
                    await self.log(f"No result attribute in details tag {i}", level="debug")
                    continue

                result_content = html.unescape(details.attrs.get("result", ""))
                await self.log(f"Result content before unescaping (first 100 chars): {details.attrs.get('result', '')[:100]}", level="debug")
                await self.log(f"Result content after unescaping (first 100 chars): {result_content[:100]}", level="debug")

                # Find all matches using finditer to get both the full match and captured groups
                matches = list(re.finditer(pattern, result_content))

                if not matches:
                    await self.log(f"No pattern matches found in details tag {i}", level="debug")
                    continue

                await self.log(f"Found {len(matches)} matches in details tag {i}", level="debug")

                # Log each match for debugging
                for j, match in enumerate(matches):
                    await self.log(f"Match {j} full text: {match.group(0)[:50]}...", level="debug")
                    await self.log(f"Match {j} captured content: {match.group(1)[:50]}...", level="debug")

                # Remove the full matches (including start/end patterns) from the result attribute
                cleaned_result = result_content
                for match in matches:
                    full_match = match.group(0)  # The entire match including the tags
                    cleaned_result = cleaned_result.replace(full_match, "").strip()

                await self.log(f"Cleaned result (first 100 chars): {cleaned_result[:100]}", level="debug")

                # Update the result attribute with cleaned content
                escaped_result = html.escape(cleaned_result)
                await self.log(f"Escaped result (first 100 chars): {escaped_result[:100]}", level="debug")
                details.attrs["result"] = escaped_result

                # Collect the extracted content instead of inserting it after the details tag
                for match in matches:
                    inner_content = match.group(1)  # Just the content between the tags
                    await self.log(f"Collecting inner content (first 100 chars): {inner_content[:100]}", level="debug")
                    extracted_contents.append(inner_content)

            await self.log(f"Processed HTML content length: {len(str(soup))}", level="debug")
            return str(soup), extracted_contents

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await self.log(f"Error processing HTML content: {str(e)}", level="error")
            await self.log(f"Traceback: {tb}", level="error")
            return content, []


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
