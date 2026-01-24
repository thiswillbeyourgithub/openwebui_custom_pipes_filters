# Anki Deck Creator for Open WebUI

A pair of Open WebUI extensions that enable LLMs to create downloadable Anki flashcard decks (.apkg files) directly within conversations, without requiring [AnkiConnect](https://ankiweb.net/shared/info/2055492159).

**This project was built using [aider.chat](https://github.com/Aider-AI/aider/).**

## Overview

This solution was created to enable quick flashcard creation for multiple users in a shared Open WebUI instance, where direct communication with Anki via AnkiConnect isn't feasible. Instead of sending cards directly to Anki, users can accumulate cards throughout a conversation and download them as a complete .apkg file.

## Components

The system consists of two parts that work together:

### 1. Anki Deck Creator Filter (`filters/anki_deck_creator_filter.py`)

**Purpose:** Guides the LLM to format flashcards correctly, tracks card accumulation, and optimizes context for long conversations.

**What it does:**
- **Inlet (before LLM):**
  - Adds instructions to the system prompt explaining how to format flashcards using `<anki_cards>` tags with JSON arrays
  - Filters conversation history to keep only the last N messages (configurable), reducing token usage in long conversations
  - Preserves important metadata from filtered messages using regex patterns
  - Cleans up previous info messages to save tokens
- **Outlet (after LLM):** Detects and counts flashcards in LLM responses, providing feedback to users about how many cards were created

### 2. Anki Deck Creator Action (`actions/anki_deck_creator_action.py`)

**Purpose:** Generates and downloads the .apkg file.

**What it does:**
- Scans the entire conversation for all flashcards across all assistant messages
- Combines them into a single Anki deck using the `genanki` library
- Triggers a browser download of the .apkg file
- Users can then import this file into Anki on any device

## How It Works

### Workflow

1. **User asks LLM to create flashcards**
   - Example: "Create 5 flashcards about photosynthesis"

2. **Filter adds formatting instructions (inlet)**
   - System prompt is automatically enriched with JSON formatting requirements
   - Specifies which fields to use (e.g., "body" for cloze content, "more" for context)

3. **LLM generates cards in the specified format**
   ```
   <anki_cards>
   [
     {
       "body": "Photosynthesis converts {{c1::light energy}} into {{c2::chemical energy}}",
       "more": "This process occurs in chloroplasts"
     }
   ]
   </anki_cards>
   ```

4. **Filter tracks cards (outlet)**
   - Detects the new cards
   - Shows: "✅ New cards: 5, Total: 5"
   - Instructs user to click "Generate Anki Deck" button

5. **User clicks the "Generate Anki Deck" action button**
   - Action scans all assistant messages in the conversation
   - Extracts all cards found in `<anki_cards>` tags
   - Creates a .apkg file with proper cloze model
   - Triggers browser download

6. **User imports the .apkg file into Anki**
   - Works on desktop, mobile, or web versions of Anki
   - All cards from the conversation are in a single deck

## Configuration

Both components share the same `fields_description` configuration to ensure consistency.

### Filter Valves

```python
fields_description: str = Field(
    default='{"body": "Main content with cloze deletions", "more": "Additional context"}',
    description="JSON dict defining flashcard fields"
)
N_messages_to_keep: int = Field(
    default=0,
    description="Number of previous messages to keep (0 = only system + current user, 1 = + last assistant, 2 = + last user + last assistant, etc.)"
)
regex_keeper: str = Field(
    default="",
    description="Multi-line regex patterns to preserve important lines from filtered messages (e.g., 'Source:.*\\nTeacher:.*')"
)
debug: bool = False  # Enable debug logging
```

### Action Valves

```python
deck_name: str = "LLM Generated Cards"  # Name of exported deck
model_name: str = "Cloze Model"  # Anki note type name
fields_description: str = '{"body": "...", "more": "..."}'  # Must match filter
```

**Important:** The `fields_description` must be identical in both filter and action for cards to export correctly.

## Installation

### Requirements

The action requires the `genanki` library:

```bash
pip install genanki
```

### Setup

1. Install the filter: `filters/anki_deck_creator_filter.py`
2. Install the action: `actions/anki_deck_creator_action.py`
3. **Enable both** in your Open WebUI settings
4. Configure the `fields_description` in both to match your needs

## Customizing Card Fields

You can customize what fields your flashcards have by modifying the `fields_description` JSON in both components.

**Example:** Add a "source" field to track where information came from:

```json
{
  "body": "Main content with cloze deletions like {{c1::hidden text}}",
  "more": "Additional context or explanations",
  "source": "Article or book reference"
}
```

The filter will instruct the LLM to fill these fields, and the action will include them in the .apkg file.

## Advanced Features

### Message Filtering for Long Conversations

The filter includes a message filtering system to optimize token usage in long conversations:

- **`N_messages_to_keep`**: Controls how many previous messages to keep in context
  - `0` = Only system prompt + current user message (most token-efficient)
  - `1` = System + last assistant message + current user
  - `2` = System + last user + last assistant + current user
  - And so on...
- System messages (with flashcard instructions) are always preserved
- The current user message is always included
- This allows you to have very long flashcard creation sessions without hitting token limits

### Regex Keeper for Metadata Preservation

Use `regex_keeper` to preserve important information from messages that would otherwise be filtered out:

- Each line is a separate regex pattern (no `/` delimiters needed)
- Matched lines from user messages are kept and prepended to the last kept message
- Useful for preserving source citations, teacher names, dates, etc.

**Example configuration:**
```
[sS]ource:.*
[tT]eacher:.*
[dD]ate:.*
```

This ensures that even if messages are filtered, lines like "Source: Chapter 5" or "Teacher: Dr. Smith" will be preserved.

### Token Optimization

The filter automatically cleans up its own info messages (the "✅ Flashcards formatted successfully!" notifications) from previous messages to save tokens. This happens transparently during the inlet phase.

## Why Not AnkiConnect?

This approach was chosen because:

1. **Multi-user environments:** In shared Open WebUI instances, users may not have Anki running locally
2. **Flexibility:** Users can review cards in the chat before downloading
3. **Accumulation:** Cards can be created across multiple messages in a conversation
4. **Portability:** .apkg files work anywhere Anki is installed, including mobile apps
5. **Simplicity:** No need to configure AnkiConnect or keep Anki running in the background
6. **Scalability:** Message filtering allows very long flashcard creation sessions without token limit issues

## Tips for Best Results

1. **Be specific with the LLM:** Ask for a certain number of cards or specific topics
2. **Use cloze deletions:** Format like `{{c1::text}}` for better active recall
3. **Review before downloading:** Check the cards in the conversation first
4. **Keep conversations focused:** One topic per conversation makes deck organization easier
5. **Customize fields:** Adjust `fields_description` to match your study needs
6. **Use message filtering for long sessions:** Set `N_messages_to_keep` to 1-2 for extended flashcard creation without hitting token limits
7. **Preserve important metadata:** Use `regex_keeper` to keep source citations, page numbers, or other references even when filtering messages
8. **Include metadata in prompts:** Start messages with structured metadata (e.g., "Source: Chapter 5\nPage: 42") that regex_keeper can preserve

## Troubleshooting

### No cards detected
- Ensure the filter is enabled
- Check that the LLM used `<anki_cards>` tags
- Verify the JSON is valid

### .apkg won't download
- Check browser console for JavaScript errors
- Verify `genanki` is installed
- Ensure both filter and action are enabled

### Cards missing fields
- Verify `fields_description` matches in both filter and action
- Check the JSON structure in LLM responses

### Long conversations hitting token limits
- Reduce `N_messages_to_keep` to 0-2 to keep only recent context
- Use `regex_keeper` to preserve important metadata from filtered messages
- The filter automatically cleans up its own info messages to save tokens

## License

AGPLv3

## Links

- [Open WebUI](https://github.com/open-webui/open-webui)
- [genanki](https://github.com/kerrickstaley/genanki)
- [Anki](https://apps.ankiweb.net/)
