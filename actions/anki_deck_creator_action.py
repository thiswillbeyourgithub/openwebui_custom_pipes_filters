"""
title: Anki Deck Creator Action
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2026-01-15
license: AGPLv3
description: Action button to generate and download an Anki .apkg file from all flashcards in the conversation. REQUIRES the companion 'Anki Deck Creator Filter' to be installed and enabled to properly format cards. Both filter and action must be enabled to work properly. This action was built using aider.chat.
required_open_webui_version: 0.3.0
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/anki_deck_creator_action
requirements: genanki
"""

import base64
import json
import random
import re
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

import genanki

# For some reason there are quicks when parsing the __doc__ from actions
__versions = [li for li in __doc__.splitlines() if li.strip().startswith("version: ")]
VERSION: str = "v?"
if __versions:
    VERSION = __versions[0].split("version: ")[1]


class Action:
    """
    Action to generate an Anki .apkg file from all flashcards in the conversation.
    Works in conjunction with the Anki Card Accumulator Filter.
    """

    VERSION: str = VERSION
    NAME: str = "Generate Anki Deck"

    class Valves(BaseModel):
        """Configuration options for the action."""

        deck_name: str = Field(
            default="LLM Generated Cards", description="Name of the Anki deck"
        )
        model_name: str = Field(
            default="Cloze Model", description="Name of the Anki note type/model"
        )
        fields_description: str = Field(
            default='{"body": "Main content with cloze deletions like {{c1::hidden text}}", "more": "Additional context or explanations"}',
            description="JSON dict where keys are field names and values are descriptions. Must match the filter configuration.",
        )

    def __init__(self):
        """Initialize the action with default valves."""
        self.valves = self.Valves()

    def _extract_all_cards(self, body: dict) -> List[dict]:
        """
        Extract all flashcards from all assistant messages in the conversation.
        Cards are stored in <anki_cards>...</anki_cards> tags.
        """
        all_cards = []
        messages = body.get("messages", [])

        # Pattern to find card JSON in messages - matches the filter's pattern
        json_pattern = r"<details id=anki_card>\s*(.*?)\s*</details>"

        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Find all card sections in this message
                matches = re.findall(json_pattern, content, re.DOTALL | re.IGNORECASE)

                for match in matches:
                    try:
                        cards = json.loads(match)
                        if isinstance(cards, list):
                            all_cards.extend(cards)
                        else:
                            all_cards.append(cards)
                    except Exception as e:
                        # Skip malformed JSON sections
                        continue

        return all_cards

    def _create_anki_model(self, fields: List[str]) -> "genanki.Model":
        """
        Create a genanki cloze model with the specified fields.
        The model allows cloze deletions in the first field and displays all fields.
        """
        # Generate a stable model ID to ensure consistency
        model_id = random.randrange(1 << 30, 1 << 31)

        field_list = [{"name": field} for field in fields]

        # Create cloze template
        # The first field is used for cloze deletions
        qfmt = "{{cloze:" + fields[0] + "}}"
        afmt = "{{cloze:" + fields[0] + "}}"

        # Add remaining fields to the answer side for context
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

    def _create_apkg(self, cards: List[dict]) -> bytes:
        """
        Create an .apkg file from the cards using genanki.
        Returns the binary content of the .apkg file.
        """
        if not genanki:
            raise ImportError(
                "genanki is not installed. Install it with: pip install genanki"
            )

        if not cards:
            raise ValueError("No cards to export")

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

        # Write to a temporary bytes buffer
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            genanki.Package(deck).write_to_file(tmp_path)
            with open(tmp_path, "rb") as f:
                apkg_bytes = f.read()
            return apkg_bytes
        finally:
            # Clean up temporary file
            import os

            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    async def action(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        __event_call__: Optional[Callable[[dict], Any]] = None,
        **kwargs,
    ) -> Optional[dict]:
        """
        Main action method that generates the .apkg file.
        This is called when the user clicks the action button.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.progress_update("Extracting flashcards from conversation...")

            # Extract all cards from the conversation
            all_cards = self._extract_all_cards(body)

            if not all_cards:
                await emitter.error_update(
                    "No flashcards found in this conversation. "
                    "Make sure the LLM has generated cards in <details id=anki_card> tags."
                )
                return {
                    "content": "❌ No flashcards found in this conversation. "
                    "Please ask the LLM to create flashcards first."
                }

            await emitter.progress_update(
                f"Found {len(all_cards)} cards. Generating .apkg file..."
            )

            # Generate the .apkg file
            try:
                apkg_bytes = self._create_apkg(all_cards)
            except ImportError as e:
                await emitter.error_update(str(e))
                return {
                    "content": f"❌ Error: {str(e)}\n\n"
                    "Please contact your administrator to install genanki."
                }
            except Exception as e:
                await emitter.error_update(f"Error creating .apkg file: {str(e)}")
                return {"content": f"❌ Error creating .apkg file: {str(e)}"}

            # Encode as base64 for download
            apkg_b64 = base64.b64encode(apkg_bytes).decode("utf-8")

            # Create filename
            filename = f"{self.valves.deck_name.replace(' ', '_')}.apkg"

            # Generate JavaScript to trigger download (similar to Word export action)
            js_download_code = f"""
                (function() {{
                    const b64Data = "{apkg_b64}";
                    const filename = "{filename}";
                    const mimeType = "application/x-apkg";
                    
                    // Convert base64 to blob
                    const byteCharacters = atob(b64Data);
                    const byteNumbers = new Array(byteCharacters.length);
                    for (let i = 0; i < byteCharacters.length; i++) {{
                        byteNumbers[i] = byteCharacters.charCodeAt(i);
                    }}
                    const byteArray = new Uint8Array(byteNumbers);
                    const blob = new Blob([byteArray], {{ type: mimeType }});
                    
                    // Create download link
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    
                    // Cleanup
                    setTimeout(() => {{
                        window.URL.revokeObjectURL(url);
                        document.body.removeChild(a);
                    }}, 100);
                }})();
            """

            # Execute the download JavaScript
            if __event_call__:
                await __event_call__(
                    {
                        "type": "execute",
                        "data": {"code": js_download_code},
                    }
                )

            await emitter.success_update(
                f"Successfully generated Anki deck with {len(all_cards)} cards!"
            )

            # Return success message
            return None

        except Exception as e:
            await emitter.error_update(f"Unexpected error: {str(e)}")
            return None


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
                {"type": "status", "data": {"description": description, "done": done}}
            )
