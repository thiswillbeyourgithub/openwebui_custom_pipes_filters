# OpenWebUI Custom Pipes & Filters

A collection of pipes, filters and tools for OpenWebUI. My usual goto templates to quickly create new Filters and Tools can be found as `templates.py` inside their respective folders.

## Components

### Filters

- **add_metadata.py** - Adds user and other metadata to requests. Useful for langfuse or litellm tracking.
    * As of version 1.0.0 of add_metadata.py, while the user is correctly passed to langfuse and litellm, other metadata are not being transmitted properly.
- **langfuse filter.py** - should maybe be better than add_metadata, and don't rely on litellm
- **warn_if_long_chat.py** - Adds soft and hard limits to the number of messages in a chat.
- **combine_user_messages.py** - Combines all user messages into a single message and removes all assistant messages to improve LLM responses. Preserves files and images.
- **hide_thinking_filter.py** - Removes thinking XML tags to reduce token count and converts them to HTML details tags. Not used anymore because open-webui now automatically wraps the thoughts.
- **debug_filter.py** - Filter that prints argument as they pass through it. You can use it multiple times to debug another filter. You can then use `docker logs open-webui --tail 100 --follow | grep DebugFilter` to see the data that interests you.
- **infinite_chat.py** - keep only the last n messages. Used to not have to create a new chat so often, for example with the anki_tool.
- **tool_compressor.py** - by default tool execution metadata (like output values etc) is stored as escaped html/json inside the content and results variables of a details html tag in the body of the message. Depending on formatting this can be uselessly token intensive, hence this tool removes them and prints only the content or results as regular html, making the whole chat much less token intensive. **This might not be needed since openwebui version 0.6.1**
- **DontAccumulateThoughts.py** - remove the `<thinking></thinking>` blocks in the input. Making the chat faster and less expensive as successive turns actually could only be paying attention to the conclusion.
- ~~**WIP_automatic_claude_caching.py**  - [WIP] Automatically replaces system prompts with cached versions. Unfinished project.~~
- **anki_deck_creator_filter** - To create [Anki](https://apps.ankiweb.net/) cards. See [Anki Deck Creator](./anki_deck_creator/).

### Tools

- **anki_tool.py** - Creates [Anki](https://apps.ankiweb.net/) flashcards through [AnkiConnect](https://ankiweb.net/shared/info/2055492159) with configurable settings. Pairs nicely with **infinite_chat.py**.
    - The open-webui instance must be able to reach the [Anki](https://apps.ankiweb.net/) app. Hence this tool is really only usable if a single user is using anki. For multiple anki users, see [Anki Deck Creator](./anki_deck_creator/).

- **wdoc_tool.py** - tool to use wdoc as an url parser or summarizer. Make sure that the LLM is using default tool calling instead of native.
    - **WARNING: you might have issues with wdoc versions. You can specify in the file the installation source of wdoc: either from the latest release or from the main branch or the dev brainch, or even a specific version.**

### Actions
- **anki_deck_creator_action** - To create [Anki](https://apps.ankiweb.net/) cards. See [Anki Deck Creator](./anki_deck_creator/).

### Pipes

- **hide_thinking.py** - Pipe version of the hide_thinking filter functionality.
    - Not used anymore because open-webui now automatically wraps the thoughts.
    - Includes an untested anthropic caching.
- **costtrackingpipe.py** - Tracks user costs and removes thinking blocks (deprecated in favor of langfuse).

### Pipelines

- **langfuse_litellm_filter_pipeline.py** - **(WIP)** A pipeline that adds metadata to request inspired by [this PR](https://github.com/open-webui/pipelines/pull/438) but with added support for litellm model names instead of open-webui alias.

