"""
title: User Tools Output Filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.2.0
date: 2025-04-18
license: GPLv3
description: Extracts tool results from HTML details tags and displays them more prominently. This was done for the wdoc tool to make its output appear as an LLM message but could be used elsewhere too.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/userToolsOutput
"""

from typing import Any, Callable, Optional
from pydantic import BaseModel, Field
from loguru import logger
import re
import html
import codecs
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
        debug: bool = Field(default=False, description="Enable debug logging")

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
        # Only log if debug is True or if it's an error
        if (hasattr(self.valves, "debug") and self.valves.debug) or level == "error":
            getattr(logger, level)(f"[{self.NAME}] {message}")
            
        if not self.emitter:
            return

        if level == "info" or level == "debug":
            if hasattr(self.valves, "debug") and self.valves.debug:
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
                        processed_content, extracted_parts = (
                            await self._process_html_content(content)
                        )
                        # Only modify the content if we actually found and extracted parts
                        if extracted_parts:
                            message["content"] = (
                                processed_content
                                + "\n\n"
                                + "\n\n".join(extracted_parts)
                            )
                        # Otherwise leave it unchanged
                    elif isinstance(content, list):
                        # Process list of content items (multi-modal)
                        all_extracted_parts = []
                        for j, item in enumerate(content):
                            if isinstance(item, dict) and "text" in item:
                                processed_text, extracted_parts = (
                                    await self._process_html_content(item["text"])
                                )
                                # Only modify text if we found extractions
                                if extracted_parts:
                                    content[j]["text"] = processed_text
                                    all_extracted_parts.extend(extracted_parts)
                            elif isinstance(item, dict) and "content" in item:
                                processed_content, extracted_parts = (
                                    await self._process_html_content(item["content"])
                                )
                                # Only modify content if we found extractions
                                if extracted_parts:
                                    content[j]["content"] = processed_content
                                    all_extracted_parts.extend(extracted_parts)

                        # Append extracted parts at the end of the content list
                        if all_extracted_parts:
                            content.append(
                                {
                                    "text": "\n\n".join(all_extracted_parts),
                                    "type": "text",
                                }
                            )

                # Handle legacy "body" key
                elif "body" in message:
                    processed_body, extracted_parts = await self._process_html_content(
                        message["body"]
                    )
                    # Only modify the body if we actually found and extracted parts
                    if extracted_parts:
                        message["body"] = (
                            processed_body + "\n\n" + "\n\n".join(extracted_parts)
                        )

            await self.log("Tool outputs extracted and repositioned successfully")

        except Exception as e:
            await self.log(f"Error in outlet: {str(e)}", level="error")

        return body

    async def _process_html_content(self, content: str) -> tuple[str, list[str]]:
        """
        Process HTML content to extract tool outputs.
        Only processes <details> tags, leaving the rest of the markdown intact.

        Returns:
            tuple: (processed_content, list_of_extracted_contents)
        """
        if not content or "<details" not in content:
            await self.log("No details tags in content, skipping", level="debug")
            return content, []

        try:
            await self.log(
                f"Content length before processing: {len(content)}", level="debug"
            )
            await self.log(f"Content snippet: {content[:100]}...", level="debug")

            # Use regex to find all <details> tags in the content
            details_pattern = re.compile(r"<details[^>]*>.*?</details>", re.DOTALL)
            details_matches = list(details_pattern.finditer(content))

            if not details_matches:
                await self.log("No details tags found by regex", level="debug")
                return content, []

            await self.log(f"Found {len(details_matches)} details tags", level="debug")

            # Create pattern for extracting content between userToolsOutput tags
            tool_output_pattern = re.compile(
                f"{re.escape(self.valves.pattern_start)}(.*?){re.escape(self.valves.pattern_end)}",
                re.MULTILINE | re.DOTALL,
            )

            # List to collect extracted content
            extracted_contents = []
            modified_content = content

            for i, match in enumerate(details_matches):
                await self.log(f"Processing details tag {i}", level="debug")
                details_html = match.group(0)
                details_start = match.start()
                details_end = match.end()

                # Parse only this specific details tag with BeautifulSoup
                soup = BeautifulSoup(details_html, "html.parser")
                details_tag = soup.find("details")

                if not details_tag or "result" not in details_tag.attrs:
                    await self.log(
                        f"No result attribute in details tag {i}", level="debug"
                    )
                    continue

                result_content = html.unescape(details_tag.attrs.get("result", ""))
                await self.log(
                    f"Result content after unescaping (first 100 chars): {result_content[:100]}",
                    level="debug",
                )

                # Find all tool output matches in the result content
                tool_matches = list(tool_output_pattern.finditer(result_content))

                if not tool_matches:
                    await self.log(
                        f"No pattern matches found in details tag {i}", level="debug"
                    )
                    continue

                await self.log(
                    f"Found {len(tool_matches)} tool output matches in details tag {i}",
                    level="debug",
                )

                # Process the matches
                cleaned_result = result_content
                for tool_match in tool_matches:
                    full_match = tool_match.group(
                        0
                    )  # The entire match including the tags
                    inner_content = tool_match.group(
                        1
                    )  # Just the content between the tags

                    # Replace escaped newlines with actual newlines
                    inner_content = inner_content.replace("\\n", "\n")
                    
                    # Decode Unicode escape sequences like \u00e9 to proper characters
                    try:
                        inner_content = codecs.decode(inner_content, 'unicode_escape')
                    except Exception as e:
                        await self.log(f"Error decoding unicode: {str(e)}", level="debug")
                    
                    # Add to extracted contents list
                    await self.log(
                        f"Collecting inner content (first 100 chars): {inner_content[:100]}",
                        level="debug",
                    )
                    extracted_contents.append(inner_content)

                    # Remove the match from the result attribute
                    cleaned_result = cleaned_result.replace(full_match, "").strip()

                # Clean up the result content
                if cleaned_result.startswith('"'):
                    cleaned_result = cleaned_result[1:]
                if cleaned_result.endswith('"'):
                    cleaned_result = cleaned_result[:-1]
                while cleaned_result.endswith(r"\n"):
                    cleaned_result = cleaned_result[:-2]
                cleaned_result = cleaned_result.strip()
                
                # Decode Unicode escape sequences in the cleaned result
                try:
                    cleaned_result = codecs.decode(cleaned_result, 'unicode_escape')
                except Exception as e:
                    await self.log(f"Error decoding unicode in result: {str(e)}", level="debug")

                await self.log(
                    f"Cleaned result (first 100 chars): {cleaned_result[:100]}",
                    level="debug",
                )

                # Update the result attribute
                details_tag.attrs["result"] = html.escape(cleaned_result)

                # Replace the original details tag in the content
                processed_details = str(details_tag)
                modified_content = (
                    modified_content[:details_start]
                    + processed_details
                    + modified_content[details_end:]
                )

            await self.log(
                f"Final content length: {len(modified_content)}", level="debug"
            )
            return modified_content, extracted_contents

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
