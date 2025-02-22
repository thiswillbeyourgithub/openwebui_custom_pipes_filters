# OpenWebUI Custom Pipes & Filters

A collection of pipes, filters and tools for OpenWebUI.

## Components

### Filters

- **add_metadata.py** - Adds user and other metadata to requests. Useful for langfuse or litellm tracking.
    * As of version 1.0.0 of add_metadata.py, while the user is correctly passed to langfuse and litellm, other metadata are not being transmitted properly.
- **warn_if_long_chat.py** - Adds soft and hard limits to the number of messages in a chat.
- **hide_thinking_filter.py** - Removes thinking XML tags to reduce token count and converts them to HTML details tags. Not used anymore because ooen-webui now automatically wraps the thoughts.
- **WIP_automatic_claude_caching.py**  - [WIP] Automatically replaces system prompts with cached versions. Unfinished project.
- **langfuse filter.py**
- **debug_filter.py** - prints all the arguments passing through it.

### Pipes

- **hide_thinking.py** - Pipe version of the hide_thinking filter functionality.
    - Not used anymore because ooen-webui now automatically wraps the thoughts.
    - Includes an untested anthropic caching.
- **costtrackingpipe.py** - Tracks user costs and removes thinking blocks (deprecated in favor of langfuse).

### Tools

- **anki_tool.py** - Creates Anki flashcards through AnkiConnect with configurable settings.
- **wdoc_tool.py** - Documentation tool requiring wdoc v2.5.7. (WIP)
- **wdoc_parser.py** - tool to use wdoc as an url parser
