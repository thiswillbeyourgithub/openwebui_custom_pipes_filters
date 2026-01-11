"""
title: Anki DB Creator Filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2026-01-11
license: AGPLv3
description: Creates Anki flashcards from LLM responses. Accumulates cards across conversation and exports to .apkg format.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/anki_db_creator
"""

import json
import re
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from loguru import logger

try:
    import genanki
except ImportError:
    genanki = None


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]
    NAME: str = "Anki DB Creator Filter"

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
        deck_name: str = Field(
            default="LLM Generated Cards", description="Name of the Anki deck"
        )
        model_name: str = Field(
            default="Cloze Model", description="Name of the Anki note type/model"
        )
        cards_directory: str = Field(
            default="/tmp",
            description="Directory to store cards JSON and apkg files (will create subdirectories per chat)",
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

    def _get_chat_directory(self, chat_id: str) -> Path:
        """Get the directory for storing files for this chat."""
        # Use chat_id to create unique directory per conversation
        base_dir = Path(self.valves.cards_directory)
        chat_dir = base_dir / f"anki_cards_{chat_id}"
        chat_dir.mkdir(parents=True, exist_ok=True)
        return chat_dir

    def _get_cards_file_path(self, chat_id: str) -> Path:
        """Get the path to the cards JSON file for this chat."""
        return self._get_chat_directory(chat_id) / "cards.json"

    def _load_existing_cards(self, chat_id: str) -> List[dict]:
        """Load existing cards from the JSON file if it exists."""
        cards_file = self._get_cards_file_path(chat_id)
        if cards_file.exists():
            try:
                return json.loads(cards_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Error loading cards file: {e}")
                return []
        return []

    def _save_cards(self, chat_id: str, cards: List[dict]) -> Path:
        """Save cards to the JSON file."""
        cards_file = self._get_cards_file_path(chat_id)
        cards_file.write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
        return cards_file

    def _create_anki_model(self, fields: List[str]) -> "genanki.Model":
        """Create a genanki cloze model with the specified fields."""
        # Generate a stable model ID based on field names to ensure consistency
        # across multiple generations of the same deck structure
        model_id = random.randrange(1 << 30, 1 << 31)
        
        field_list = [{"name": field} for field in fields]
        
        # Create cloze template that shows all fields
        # The first field will be used for cloze deletions
        qfmt = "{{cloze:" + fields[0] + "}}"
        afmt = "{{cloze:" + fields[0] + "}}"
        
        # Add remaining fields to the answer side
        for field in fields[1:]:
            afmt += f"<br><br><b>{field}:</b><br>{{{{{field}}}}}"
        
        templates = [
            {
                "name": "Cloze",
                "qfmt": qfmt,
                "afmt": afmt,
            },
        ]
        
        return genanki.Model(
            model_id,
            self.valves.model_name,
            fields=field_list,
            templates=templates,
            model_type=genanki.Model.CLOZE,
        )

    def _create_apkg(self, chat_id: str, cards: List[dict]) -> Path:
        """Create an .apkg file from the cards using genanki."""
        if not genanki:
            raise ImportError("genanki is not installed. Install it with: pip install genanki")
        
        # Get field names from the fields_description
        try:
            fields_desc = json.loads(self.valves.fields_description)
            field_names = list(fields_desc.keys())
        except Exception as e:
            raise ValueError(f"Invalid fields_description JSON: {e}")
        
        # Create model and deck
        model = self._create_anki_model(field_names)
        deck_id = random.randrange(1 << 30, 1 << 31)
        deck = genanki.Deck(deck_id, self.valves.deck_name)
        
        # Add notes to deck
        for card in cards:
            # Extract field values in the correct order
            field_values = [card.get(field, "") for field in field_names]
            note = genanki.Note(
                model=model,
                fields=field_values,
            )
            deck.add_note(note)
        
        # Write to file
        apkg_path = self._get_chat_directory(chat_id) / "cards.apkg"
        genanki.Package(deck).write_to_file(str(apkg_path))
        
        return apkg_path

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        __chat_id__: Optional[str] = None,
        **kwargs,
    ) -> dict:
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
            # Generate the instruction text based on fields_description
            try:
                fields_desc = json.loads(self.valves.fields_description)
            except Exception as e:
                await self.log(f"Invalid fields_description JSON: {e}", level="error")
                return body

            # Build the instruction
            instruction = "\n\n---\n\n**IMPORTANT INSTRUCTION FOR FLASHCARD CREATION:**\n\n"
            instruction += "At the end of your response, you MUST include a JSON array of flashcard dictionaries enclosed in <json> tags.\n\n"
            instruction += "Each flashcard should be a dictionary with the following fields:\n"
            for field_name, field_description in fields_desc.items():
                instruction += f"- **{field_name}**: {field_description}\n"
            
            instruction += "\nFor cloze deletions, use the format {{c1::text to hide}}, {{c2::another hidden text}}, etc.\n"
            instruction += "\nExample format:\n"
            instruction += "<json>\n"
            
            # Create example based on fields
            example_card = {}
            first_field = True
            for field_name, field_description in fields_desc.items():
                if first_field:
                    example_card[field_name] = "What is this?<br>{{c1::This is an example of hidden content}}"
                    first_field = False
                else:
                    example_card[field_name] = "Additional information here"
            
            instruction += json.dumps([example_card], indent=2)
            instruction += "\n</json>\n"

            # Find or create system message and append the instruction
            messages = body.get("messages", [])
            system_message_found = False
            
            for message in messages:
                if message.get("role") == "system":
                    # Append to existing system message
                    content = message.get("content", "")
                    if isinstance(content, str):
                        message["content"] = content + instruction
                    elif isinstance(content, list):
                        # If content is a list, append as text item
                        message["content"].append({"type": "text", "text": instruction})
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
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        __chat_id__: Optional[str] = None,
        **kwargs,
    ) -> dict:
        self.emitter = EventEmitter(__event_emitter__)

        # Check user-specific settings
        user_valves = {}
        if __user__ and "valves" in __user__:
            user_valves = dict(__user__.get("valves", {}))

        if not user_valves.get("enabled", True):
            return body

        await self.log("Processing outlet request")

        try:
            if not __chat_id__:
                await self.log("No chat_id provided, cannot process cards", level="error")
                return body

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
            
            # Extract JSON from <json>...</json> tags
            json_pattern = r"<json>\s*(.*?)\s*</json>"
            json_matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)
            
            if not json_matches:
                await self.log("No <json> tags found in response")
                return body

            # Parse the JSON
            try:
                new_cards = json.loads(json_matches[0])
                if not isinstance(new_cards, list):
                    new_cards = [new_cards]
            except Exception as e:
                await self.log(f"Error parsing JSON from response: {e}", level="error")
                return body

            await self.log(f"Extracted {len(new_cards)} new card(s)")

            # Load existing cards and merge
            existing_cards = self._load_existing_cards(__chat_id__)
            all_cards = existing_cards + new_cards
            
            await self.log(f"Total cards: {len(all_cards)} (previous: {len(existing_cards)}, new: {len(new_cards)})")

            # Save cards to JSON file
            cards_json_path = self._save_cards(__chat_id__, all_cards)
            await self.log(f"Saved cards to {cards_json_path}")

            # Create .apkg file
            try:
                apkg_path = self._create_apkg(__chat_id__, all_cards)
                await self.log(f"Created .apkg file at {apkg_path}")
            except Exception as e:
                await self.log(f"Error creating .apkg file: {e}", level="error")
                apkg_path = None

            # Remove JSON section from the message content
            cleaned_content = re.sub(json_pattern, "", content, flags=re.DOTALL | re.IGNORECASE)
            cleaned_content = cleaned_content.strip()

            # Add file information to the cleaned content
            file_info = f"\n\n---\n\n✅ **Flashcards created successfully!**\n\n"
            file_info += f"📊 Total cards in deck: **{len(all_cards)}**\n"
            file_info += f"🆕 New cards added: **{len(new_cards)}**\n\n"
            file_info += f"📁 Files location: `{self._get_chat_directory(__chat_id__)}`\n"
            file_info += f"- `cards.json` - All cards in JSON format\n"
            if apkg_path:
                file_info += f"- `cards.apkg` - Anki package ready to import\n"
            
            last_assistant_msg["content"] = cleaned_content + file_info

            await self.emitter.success_update(
                f"Created {len(new_cards)} new flashcard(s). Total: {len(all_cards)}"
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
