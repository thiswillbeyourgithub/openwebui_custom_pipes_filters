"""
title: Anki Deck Creator Filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2026-01-15
license: AGPLv3
description: Adds instructions for Anki flashcard creation and helps accumulate cards across conversation. REQUIRES the companion 'Anki Deck Creator Action' action to be installed to generate downloadable .apkg files. Both filter and action must be enabled to work properly.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/anki_deck_creator_filter
requirements: None
"""

import json
import re
from typing import Any, Callable, List, Optional, Dict
from pydantic import BaseModel, Field
from loguru import logger


# Template for flashcard creation instructions
# FIELDS_LIST_PLACEHOLDER will be replaced with the actual field descriptions
# EXAMPLE_PLACEHOLDER will be replaced with the example card JSON
FLASHCARD_INSTRUCTION_TEMPLATE = """

**IMPORTANT INSTRUCTION FOR FLASHCARD CREATION:**

When creating flashcards, keep your response VERY brief.
Just acknowledge briefly and provide the cards in the specified format.

You MUST include a JSON array of flashcard dictionaries enclosed in <anki_cards> tags.

Each flashcard should be a dictionary with the following fields:
FIELDS_LIST_PLACEHOLDER

For cloze deletions, use the format {{c1::text to hide}}, {{c2::another hidden text}}, etc.

Example format:
<anki_cards>
EXAMPLE_PLACEHOLDER
</anki_cards>

The user can then use the 'Generate Anki Deck' action button to create a downloadable .apkg file.
"""


def generate_flashcard_instruction(fields_desc: Dict[str, str]) -> str:
    """
    Generate the flashcard creation instruction from the template.

    This creates the instruction text that guides the LLM on how to format flashcards,
    using the field descriptions to customize the output format.

    Parameters
    ----------
    fields_desc : Dict[str, str]
        Dictionary where keys are field names and values are field descriptions

    Returns
    -------
    str
        The complete instruction text with placeholders replaced
    """
    # Build the fields list section
    fields_list = ""
    for field_name, field_description in fields_desc.items():
        fields_list += f"- **{field_name}**: {field_description}\n"

    # Create example card based on fields
    example_card = {}
    first_field = True
    for field_name in fields_desc.keys():
        if first_field:
            # First field gets cloze deletion example
            example_card[field_name] = (
                "What is this?<br>{{c1::This is an example of hidden content}}"
            )
            first_field = False
        else:
            # Other fields get generic content
            example_card[field_name] = "Additional information here"

    # Format the example as JSON
    example_json = json.dumps([example_card], indent=2)

    # Replace placeholders in template
    instruction = FLASHCARD_INSTRUCTION_TEMPLATE.replace(
        "FIELDS_LIST_PLACEHOLDER", fields_list.rstrip()
    ).replace("EXAMPLE_PLACEHOLDER", example_json)

    return instruction


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]
    NAME: str = "Anki Deck Creator Filter"

    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (lower numbers run first).",
        )
        debug: bool = Field(default=False, description="Enable debug logging")
        fields_description: str = Field(
            default='{"body": "Main content with cloze deletions like {{c1::hidden text}}", "more": "Additional context or explanations"}',
            description="JSON dict where keys are field names and values are descriptions of what should go in each field",
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
        """Log a message to both logger and emitter. Info and error messages
        are always shown to the user, debug messages only when debug valve is enabled."""
        getattr(logger, level)(f"[{self.NAME}] {message}")
        if level == "info":
            await self.emitter.progress_update(f"[{self.NAME}] {message}")
        elif level == "debug":
            if self.valves.debug:
                await self.emitter.progress_update(f"[{self.NAME}] {message}")
        elif level == "error":
            await self.emitter.error_update(f"[{self.NAME}] {message}")

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        **kwargs,
    ) -> dict:
        """Add flashcard creation instructions to the system prompt."""
        self.emitter = EventEmitter(__event_emitter__)

        # Check user-specific settings
        user_valves = {}
        if __user__ and "valves" in __user__:
            user_valves = dict(__user__.get("valves", {}))

        if not user_valves.get("enabled", True):
            await self.log("Filter disabled for this user")
            return body

        await self.log("Processing inlet request")

        try:
            # Clean up previous info messages to save tokens in long conversations
            # Remove content between HTML comment markers added by outlet
            messages = body.get("messages", [])
            info_pattern = r"<!-- ANKI_INFO_START -->.*?<!-- ANKI_INFO_END -->"

            for message in messages:
                content = message.get("content", "")
                if isinstance(content, str):
                    # Remove all occurrences of info messages
                    cleaned_content = re.sub(info_pattern, "", content, flags=re.DOTALL)
                    if cleaned_content != content:
                        message["content"] = cleaned_content
                elif isinstance(content, list):
                    # Handle list-type content (with text items)
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            cleaned_text = re.sub(
                                info_pattern, "", text, flags=re.DOTALL
                            )
                            if cleaned_text != text:
                                item["text"] = cleaned_text

            body["messages"] = messages

            # Parse the field descriptions from valves
            try:
                fields_desc = json.loads(self.valves.fields_description)
            except Exception as e:
                await self.log(f"Invalid fields_description JSON: {e}", level="error")
                return body

            # Generate the instruction text using the template
            instruction = generate_flashcard_instruction(fields_desc)

            # Find or create system message and append the instruction
            messages = body.get("messages", [])
            system_message_found = False

            for message in messages:
                if message.get("role") == "system":
                    # Append to existing system message with separator
                    content = message.get("content", "")
                    if isinstance(content, str):
                        message["content"] = content + "\n\n---" + instruction
                    elif isinstance(content, list):
                        # If content is a list, append as text item with separator
                        message["content"].append(
                            {"type": "text", "text": "\n\n---" + instruction}
                        )
                    system_message_found = True
                    break

            if not system_message_found:
                # Create a new system message at the beginning
                messages.insert(0, {"role": "system", "content": instruction})

            body["messages"] = messages

            await self.log("Added flashcard creation instruction to system prompt")

        except Exception as e:
            await self.log(f"Error in inlet: {str(e)}", level="error")

        return body

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        **kwargs,
    ) -> dict:
        """Extract and count flashcards from LLM responses."""
        self.emitter = EventEmitter(__event_emitter__)

        # Check user-specific settings
        user_valves = {}
        if __user__ and "valves" in __user__:
            user_valves = dict(__user__.get("valves", {}))

        if not user_valves.get("enabled", True):
            return body

        await self.log("Processing outlet request")

        try:
            messages = body.get("messages", [])
            if not messages:
                await self.log("No messages in body")
                return body

            # Get the last assistant message
            last_assistant_msg = None
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg
                    break

            if not last_assistant_msg:
                await self.log("No assistant message found")
                return body

            content = last_assistant_msg.get("content", "")

            # Extract JSON from <anki_cards>...</anki_cards> tags
            json_pattern = r"<anki_cards>\s*(.*?)\s*</anki_cards>"
            json_matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)

            if not json_matches:
                # No cards in this message, that's fine
                return body

            # Parse the JSON to count cards
            try:
                new_cards = json.loads(json_matches[0])
                if not isinstance(new_cards, list):
                    new_cards = [new_cards]
            except Exception as e:
                await self.log(f"Error parsing JSON from response: {e}", level="error")
                return body

            await self.log(f"Found {len(new_cards)} new card(s) in this response")

            # Count total cards in conversation
            messages = body.get("messages", [])
            total_cards = 0
            for msg in messages:
                if msg.get("role") == "assistant":
                    msg_content = msg.get("content", "")
                    msg_matches = re.findall(
                        json_pattern, msg_content, re.DOTALL | re.IGNORECASE
                    )
                    for match in msg_matches:
                        try:
                            cards = json.loads(match)
                            if isinstance(cards, list):
                                total_cards += len(cards)
                            else:
                                total_cards += 1
                        except Exception:
                            pass

            # Add informative message after the cards
            # Wrapped in HTML comments so it can be removed in subsequent requests to save tokens
            info_msg = f"\n\n<!-- ANKI_INFO_START -->\n\n---\n\n✅ **Flashcards formatted successfully!**\n\n"
            info_msg += f"🆕 New cards in this response: **{len(new_cards)}**\n"
            info_msg += f"📊 Total cards in conversation: **{total_cards}**\n\n"
            info_msg += "💡 Click the **'Generate Anki Deck'** action button below to download all cards as a .apkg file.\n"
            info_msg += "\n<!-- ANKI_INFO_END -->"

            last_assistant_msg["content"] = content + info_msg

            await self.emitter.success_update(
                f"Found {len(new_cards)} new cards. Total: {total_cards}"
            )

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
