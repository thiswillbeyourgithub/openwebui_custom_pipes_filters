# OpenWebUI Custom Pipes & Filters

A collection of pipes, filters and tools for OpenWebUI.

## Components

### Filters

- **add_metadata.py** - Adds user and other metadata to requests. Useful for langfuse or litellm tracking.
    * As of version 1.0.0 of add_metadata.py, while the user is correctly passed to langfuse and litellm, other metadata are not being transmitted properly.
- **langfuse filter.py** - should maybe be better than add_metadata, and don't rely on litellm
- **warn_if_long_chat.py** - Adds soft and hard limits to the number of messages in a chat.
- **hide_thinking_filter.py** - Removes thinking XML tags to reduce token count and converts them to HTML details tags. Not used anymore because open-webui now automatically wraps the thoughts.
- **debug_filter.py** - prints all the arguments passing through it.
- **infinite_chat.py** - keep only the last n messages. Used to not have to create a new chat so often, for example with the anki_tool.
- **tool_compressor.py** - by default tool execution metadata (like output values etc) is stored as escaped html/json inside the content and results variables of a details html tag in the body of the message. Depending on formatting this can be uselessly token intensive, hence this tool removes them and prints only the content or results as regular html, making the whole chat much less token intensive.
- **WIP_automatic_claude_caching.py**  - [WIP] Automatically replaces system prompts with cached versions. Unfinished project.

### Tools

- **anki_tool.py** - Creates Anki flashcards through AnkiConnect with configurable settings. Pairs nicely with **infinite_chat.py**.
- **wdoc_tool.py** - tool to use wdoc as an url parser or summarizer

### Pipes

- **hide_thinking.py** - Pipe version of the hide_thinking filter functionality.
    - Not used anymore because open-webui now automatically wraps the thoughts.
    - Includes an untested anthropic caching.
- **costtrackingpipe.py** - Tracks user costs and removes thinking blocks (deprecated in favor of langfuse).

