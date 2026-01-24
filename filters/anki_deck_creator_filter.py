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
<details id=anki_card>
<summary>Flashcards</summary>
EXAMPLE_PLACEHOLDER
</details>

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
        regex_keeper: str = Field(
            default="",
            description="Multi-line text where each line is a regex pattern. Matched lines from user messages will be preserved and prepended to the last kept message. Example:\n[sS]ource:.*\n[tT]eacher:.*",
        )
        N_messages_to_keep: int = Field(
            default=0,
            description="Number of previous messages to keep in context (not counting system or current user message). 0 = only system + current user. 1 = system + last assistant + current user. 2 = system + last user + last assistant + current user. Must be >= 0.",
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

    def _extract_regex_patterns(self, regex_keeper: str) -> List[re.Pattern]:
        """
        Extract and compile regex patterns from RegexKeeper valve.

        Each line in regex_keeper is treated as a separate pattern.
        Invalid patterns are skipped with a log message.

        Parameters
        ----------
        regex_keeper : str
            Multi-line string where each line is a regex pattern

        Returns
        -------
        List[re.Pattern]
            List of compiled regex patterns
        """
        patterns = []
        for line in regex_keeper.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    patterns.append(re.compile(line))
                except re.error as e:
                    logger.warning(
                        f"[{self.NAME}] Invalid regex pattern '{line}': {str(e)}"
                    )
        return patterns

    def _extract_matched_values(
        self, messages: List[dict], patterns: List[re.Pattern]
    ) -> Dict[str, str]:
        """
        Extract the last matched value for each regex pattern from user messages.

        This iterates through all user messages, splits each by lines, and checks
        if any line matches any of the provided patterns. The last match for each
        pattern is kept (later matches override earlier ones).

        Parameters
        ----------
        messages : List[dict]
            List of message dictionaries to search through
        patterns : List[re.Pattern]
            List of compiled regex patterns to match against

        Returns
        -------
        Dict[str, str]
            Dictionary mapping pattern string to the last matched line
        """
        matched_values = {}

        for message in messages:
            if message.get("role") != "user":
                continue

            content = message.get("content", "")
            if isinstance(content, list):
                # Extract text from list-type content (used for multimodal messages)
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = "\n".join(text_parts)

            # Split by lines and check each pattern
            for line in content.splitlines():
                for pattern in patterns:
                    match = pattern.match(line.strip())
                    if match:
                        # Store the full matched line, keyed by pattern
                        matched_values[pattern.pattern] = line.strip()

        return matched_values

    def _keep_last_n_messages(
        self, messages: List[dict], n: int, prepend_text: str = ""
    ) -> List[dict]:
        """
        Keep system messages and the last N conversation messages.

        The current user message is assumed to have been removed before calling
        this function and will be re-added by the caller.

        Parameters
        ----------
        messages : List[dict]
            List of messages (excluding the current user message)
        n : int
            Number of previous messages to keep (must be >= 0)
        prepend_text : str, optional
            Text to prepend to the last kept message (used for regex matches)

        Returns
        -------
        List[dict]
            System messages + last N conversation messages

        Raises
        ------
        ValueError
            If n < 0
        """
        if n < 0:
            raise ValueError(f"N_messages_to_keep must be >= 0, got {n}")

        # Separate system messages from conversation messages
        # System messages are always kept to preserve instructions
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        conversation_messages = [msg for msg in messages if msg.get("role") != "system"]

        # Keep last N conversation messages
        if n == 0:
            kept_messages = []
        else:
            kept_messages = conversation_messages[-n:]

        # Prepend text to the last kept message if provided
        # This is used to add the regex-matched content
        if prepend_text and kept_messages:
            last_msg = kept_messages[-1]
            content = last_msg.get("content", "")
            if isinstance(content, str):
                last_msg["content"] = prepend_text + "\n\n" + content
            elif isinstance(content, list):
                # Insert at the beginning of the content list
                last_msg["content"].insert(
                    0, {"type": "text", "text": prepend_text + "\n\n"}
                )

        # Return system messages + kept conversation messages
        return system_messages + kept_messages

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
            # Remove content between text markers added by outlet
            messages = body.get("messages", [])
            info_pattern = r"\n+---\n+✅ \*\*Flashcards formatted successfully!\*\*.*?💡 Click the \*\*'Generate Anki Deck'\*\* action button below to download all cards as a \.apkg file\.\n*"

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

            # Apply message filtering to keep only last N messages
            # This allows long conversations while maintaining LLM focus
            # Extract current user message (assumed to be the last message)
            current_user_msg = None
            if body["messages"] and body["messages"][-1].get("role") == "user":
                current_user_msg = body["messages"][-1]
                messages_without_current = body["messages"][:-1]
            else:
                messages_without_current = body["messages"]

            # First, extract regex-matched values from all user messages
            # before we filter them out
            patterns = self._extract_regex_patterns(self.valves.regex_keeper)
            prepend_text = ""

            if patterns:
                matched_values = self._extract_matched_values(
                    messages_without_current, patterns
                )
                if matched_values:
                    # Build prepend text from all matched values
                    prepend_lines = list(matched_values.values())
                    prepend_text = "\n".join(prepend_lines)
                    await self.log(
                        f"Preserved {len(prepend_lines)} regex-matched line(s)",
                        level="debug",
                    )

            # Filter messages to keep only last N messages (excluding system and current user)
            original_count = len(
                [m for m in messages_without_current if m.get("role") != "system"]
            )

            # Only prepend to kept messages if we're keeping any (n > 0)
            # If n=0, we'll prepend to current user message instead
            filtered_messages = self._keep_last_n_messages(
                messages_without_current,
                self.valves.N_messages_to_keep,
                prepend_text if self.valves.N_messages_to_keep > 0 else "",
            )

            # If n=0 and there's regex-matched content, prepend it to the current user message
            # This ensures the context is preserved even when no conversation history is kept
            if (
                prepend_text
                and self.valves.N_messages_to_keep == 0
                and current_user_msg
            ):
                content = current_user_msg.get("content", "")
                if isinstance(content, str):
                    current_user_msg["content"] = prepend_text + "\n\n" + content
                elif isinstance(content, list):
                    current_user_msg["content"].insert(
                        0, {"type": "text", "text": prepend_text + "\n\n"}
                    )

            # Add current user message back
            if current_user_msg:
                filtered_messages.append(current_user_msg)

            body["messages"] = filtered_messages

            new_count = len([m for m in body["messages"] if m.get("role") != "system"])
            # Subtract 1 to not count the current user message
            kept_count = new_count - (1 if current_user_msg else 0)
            await self.log(
                f"Filtered messages: kept last {kept_count} message(s) from history "
                f"({kept_count}/{original_count} messages) + current user message",
                level="debug",
            )

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

            # Extract JSON from <details id=anki_card>...</details> tags
            # Skips the <summary> tag to extract only the JSON content
            json_pattern = (
                r"<details id=anki_card>\s*<summary>.*?</summary>\s*(.*?)\s*</details>"
            )
            json_matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)

            if not json_matches:
                # No cards in this message, that's fine
                return body

            # Inject fields configuration into the card details for the action to use
            # This creates a nested collapsed details tag so it's not intrusive
            fields_config_tag = f"\n<details id=anki_fields_config>\n<summary>Fields Configuration</summary>\n{self.valves.fields_description}\n</details>\n"

            # Insert the config right after the summary tag in the card details
            content = re.sub(
                r"(<details id=anki_card>\s*<summary>.*?</summary>)",
                r"\1" + fields_config_tag,
                content,
                flags=re.DOTALL | re.IGNORECASE,
            )
            last_assistant_msg["content"] = content

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
                    # Skips the <summary> tag and optional fields config to extract only the JSON content
                    msg_pattern = r"<details id=anki_card>\s*<summary>.*?</summary>\s*(?:<details id=anki_fields_config>.*?</details>\s*)?(.*?)\s*</details>"
                    msg_matches = re.findall(
                        msg_pattern, msg_content, re.DOTALL | re.IGNORECASE
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
            # This text will be matched and removed in subsequent requests to save tokens
            info_msg = f"\n\n---\n\n✅ **Flashcards formatted successfully!**\n\n"
            info_msg += f"🆕 New cards in this response: **{len(new_cards)}**\n"
            info_msg += f"📊 Total cards in conversation: **{total_cards}**\n\n"
            info_msg += "💡 Click the **'Generate Anki Deck'** action button below to download all cards as a .apkg file.\n"

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
