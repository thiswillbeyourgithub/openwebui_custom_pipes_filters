# OpenWebUI Custom Pipes & Filters

A collection of pipes, filters and tools for OpenWebUI.

## Components

### Filters

- **add_metadata.py** (v1.0.2) - Adds user and other metadata to requests. Useful for langfuse or litellm tracking.
- **hide_thinking_filter.py** (v0.6) - Removes thinking XML tags to reduce token count and converts them to HTML details tags.
- **warn_if_long_chat.py** (v1.0.0) - Adds soft and hard limits to the number of messages in a chat.
- **WIP_automatic_claude_caching.py** (v0.0) - [WIP] Automatically replaces system prompts with cached versions.

### Pipes

- **hide_thinking.py** - Pipe version of the hide_thinking filter functionality.
- **costtrackingpipe.py** (v3.1.1) - Tracks user costs and removes thinking blocks (deprecated in favor of langfuse).

### Tools

- **anki_tool.py** (v0.0.1) - Creates Anki flashcards through AnkiConnect with configurable settings.
- **wdoc_tool.py** - Documentation tool requiring wdoc v2.5.7.

## Known Issues

* As of version 1.0.0 of add_metadata.py, while the user is correctly passed to langfuse and litellm, other metadata are not being transmitted properly.

## Notes

- The costtrackingpipe has been deprecated in favor of using langfuse with the add_metadata filter for user tracking.
