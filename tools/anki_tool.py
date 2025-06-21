"""
title: Anki Flashcard Creator
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub
open_webui_url: https://openwebui.com/t/qqqqqqqqqqqqqqqqqqqq/ankiflashcardcreator/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
description: A tool to create Anki flashcards through Ankiconnect with configurable settings and event emitters for UI feedback. Supports fields overrides via user valves. Note: if you want a multi user multi anki setup (each user with its own anki) you want each user to add its own private tool with as host a local url to its host via reverse proxies like ngrok that allows a url to point to a local service on the client side. By the author of Voice2Anki and AnkiAiUtils.
version: 1.5.4
"""

# TODO make it able to create several flashcards in one call, to make it more cost effective
# TODO update the tool parameters too: https://github.com/open-webui/open-webui/blob/main/backend/open_webui/utils/tools.py
# TODO make it possible to include images in the cards, by that I mean for example: send an image + a question, and get the card created about the question (this is already working) AND store the image in the source
# TODO if the example field contains only a string, it is a path to a file that contains examples in a json or toml file.
# TODO support for specifying input and output (currently we only use output) in the examples
# TODO add a tool "add to memory" that is never triggered autonomously by the llm but the user can ask the llm to use it to add the last created anki card as an example
#   TODO then make a prompt filtering that roughly filters out by semantic cosine, just to avoid issues when having too many examples

import requests
import json
import base64
import uuid
from typing import Callable, Any, List, Optional
from pydantic import BaseModel, Field
import aiohttp
from loguru import logger


TEMPLATE_EXAMPLE = """
Here are some good flashcards examples:
<examples>
<card>
EXAMPLES
</card>
</examples>
"""
TEMPLATE_DOCSTRING = """
RULES

Here are the text fields you can specify along with what their appropriate content should be:
Each keys of the param `fields` must be among those fields and all values must be strings.
<fields_description>
FIELDS_DESCRIPTION
</fields_description>
EXAMPLES

:param fields: Dictionary mapping the flashcard's field names to their string content. Refer to the tool description for details.
:return: The note id of the new card.
"""


class Tools:

    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]

    class Valves(BaseModel):
        ankiconnect_host: str = Field(
            default="http://localhost",
            description="Host address for Ankiconnect",
            required=True,
        )
        ankiconnect_port: str = Field(
            default="8765",
            description="Port for Ankiconnect",
            required=True,
        )
        deck: str = Field(
            default="Default",
            description="Deck for new flashcards. If not 'Default', it must be created manually.",
            required=True,
        )
        notetype_name: str = Field(
            default="Basic",
            description="Note type for new flashcards. It must already exist.",
            required=True,
        )
        tags: List[str] = Field(
            default="open-webui",
            description="Tags for new flashcards.",
            required=True,
        )
        fields_description: str = Field(
            default='{"Front": "The concise question", "Back": "The answer"}',
            description="Description of the note type fields and their purpose. Use json format.",
            required=True,
        )
        rules: str = Field(
            default="""Calling this function creates a single Anki flashcard using the `fields` argument as contents.
You can leave some fields empty.
If not otherwised specified, write the flashcard in the language of the user's request.
You are allowed to use html formatting.
You can refer to images by using the placeholder ANKI_IMAGE_PATH in your field values - this will be replaced with the actual image(s) from the conversation.
Please pay very close attention to the examples of the user and try to imitate their formulation.
If the user didn't specify how many cards to create, assume he wants a single one.
If the user does not reply anything useful after creating the flashcard, do NOT assume you should create more cards, if unsure ask them.""",
            description="All rules given to the LLM.",
            required=True,
        )
        examples: str = Field(
            default='[{"Front": "What is the capital of France?", "Back": "Paris"},{"Front": "What is 2+2?", "Back": "4"}]',
            description="Examples of good flashcards to show the LLM.",
            required=True,
        )
        metadata_field: str = Field(
            default="",
            description="Name of a field to which we append the metadata of this chat. Useful to keep track of the source of a flashcard.",
            required=True,
        )
        openwebui_url: str = Field(
            default="http://localhost:8080",
            description="URL of the OpenWebUI instance. Only used if metadata_field is specified to add a link to the chat.",
            required=False,
        )
        pass

    # We need to use a setter property because that's the only way I could find
    # to update the docstring of the tool depending on a valve.
    # This was devised after looking at https://github.com/open-webui/open-webui/blob/2017856791b666fac5f1c2f80a3bc7916439438b/backend/open_webui/utils/tools.py
    @property
    def valves(self):
        return self._valves

    @valves.setter
    def valves(self, value):
        self._valves = value
        self.create_flashcard.__func__.__doc__ = update_docstring(
            fields_description=value.fields_description,
            rules=value.rules,
            examples=value.examples,
        )

    class UserValves(BaseModel):
        field_overrides: str = Field(
            default="{}",
            description="JSON string of field values that will override any values specified by the LLM in the fields parameter.",
        )
        enable_overloading: bool = Field(
            default=True,
            description="If set to false, the LLM's field values will not be overridden by field_overrides.",
        )
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.fields_description = self.valves.fields_description
        self.parameters_are_checked = False

    async def __tool_param_checker__(self):
        # check deck exists and model exists
        logger.debug("AnkiFlashcardCreator: Starting to check Tool parameters")
        deck_list = await _ankiconnect_request(
            self.valves.ankiconnect_host, self.valves.ankiconnect_port, "deckNames"
        )
        assert (
            self.valves.deck in deck_list
        ), f"Deck '{self.valves.deck}' was not found in the decks of anki. You must create it first."
        models = await _ankiconnect_request(
            self.valves.ankiconnect_host, self.valves.ankiconnect_port, "modelNames"
        )
        assert (
            self.valves.notetype_name in models
        ), f"Notetype '{self.valves.notetype_name}' was not found in the notetypes of anki. You must fix the valve first."
        self.parameters_are_checked = True

    async def create_flashcard(
        self,
        fields: dict,
        __messages__: List = None,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
        __model__: dict = {},
        __metadata__: dict = {},
        __files__: list = None,  # don't know how to make it work so far
    ) -> Optional[int]:
        """THIS DOCSTRING IS A PLACEHOLDER AND SHOULD NEVER BE SHOWN TO AN LLM.
        TO THE LLM: IF YOU SEE THIS MESSAGE NOTIFY THE USER OF THAT FACT AND
        WARN THEM THAT THIS IS A BUG AND ASK THEM TO CREATE A BUG REPORT AT https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters.
        """
        logger.info(
            f"AnkiFlashcardCreator: Starting create_flashcard with fields: {fields}"
        )
        logger.info(
            f"AnkiFlashcardCreator: __messages__ length: {len(__messages__) if __messages__ else 0}"
        )
        logger.info(
            f"AnkiFlashcardCreator: __user__: {__user__.get('name', 'unknown')}"
        )
        logger.info(f"AnkiFlashcardCreator: __files__: {__files__}")
        emitter = EventEmitter(__event_emitter__)

        # check tool parameter validity on first method call instead of
        if not self.parameters_are_checked:
            logger.info("AnkiFlashcardCreator: Checking tool parameters for first time")
            try:
                await self.__tool_param_checker__()
            except Exception as e:
                logger.error(
                    f"AnkiFlashcardCreator: Error when checking tool parameters: '{e}'"
                )
                await emitter.error_update(
                    f"AnkiFlashcardCreator: Error when checking tool parameters: '{e}'"
                )
                return (
                    f"AnkiFlashcardCreator: Error when checking tool parameters: '{e}'"
                )

        if isinstance(fields, str):
            try:
                fields_dict = json.loads(fields)
                assert isinstance(fields_dict, dict), "Not a dict"
            except Exception as e:
                # remove anything before the first { and after the last }
                start = -1
                end = -1
                for i, char in enumerate(fields):
                    if char == "{" and start == -1:
                        start = i
                    if char == "}":
                        end = i

                if start != -1 and end != -1:
                    f = fields[start : end + 1]
                else:
                    f = ""
                try:
                    f = json.loads(f)
                    assert isinstance(f, dict), "Not a dict"
                    fields_dict = f
                except Exception as e:
                    logger.info(
                        f"AnkiFlashcardCreator: fields param was a str but couldn't be parsed as dict: '{e}'"
                    )

        if not fields:
            await emitter.error_update("No field contents provided")
            return "No field contents provided"

        if not isinstance(fields, dict):
            await emitter.error_update(
                f"Invalid format for `fields` param, it must be a dict, received '{fields}'"
            )
            return "No field contents provided or invalid format"

        # Process user valves if present
        field_overrides = {}
        enable_overloading = True
        if __user__ and "valves" in __user__:
            # Check if overloading is enabled
            if hasattr(__user__["valves"], "enable_overloading"):
                enable_overloading = __user__["valves"].enable_overloading

            # Only process overrides if enabled
            if enable_overloading:
                override_value = __user__["valves"].field_overrides
                if isinstance(override_value, str):
                    try:
                        field_overrides = json.loads(override_value)
                        assert isinstance(
                            field_overrides, dict
                        ), "field_overrides must be a dictionary"
                        await emitter.progress_update(
                            f"Field to override: {field_overrides}"
                        )
                    except Exception as e:
                        await emitter.error_update(
                            f"Error parsing field_overrides from user valves: {str(e)}"
                        )
                        return f"Error parsing field_overrides: {str(e)}"
                elif isinstance(override_value, dict):
                    field_overrides = override_value
                    await emitter.progress_update(
                        f"Field to override: {field_overrides}"
                    )

        # Apply field overrides to override any values specified by the LLM (if enabled)
        merged_fields = fields.copy()
        if enable_overloading and field_overrides:
            merged_fields.update(field_overrides)
            await emitter.progress_update("Applied field overrides")
        fields = merged_fields

        # Process images from messages for the picture parameter
        pictures = []
        target_fields = []

        if __messages__:
            images = []
            for message in __messages__:
                if isinstance(message, dict) and message.get("role") == "user":
                    content = message.get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if (
                                isinstance(item, dict)
                                and item.get("type") == "image_url"
                            ):
                                image_url = item.get("image_url", {}).get("url", "")
                                if image_url.startswith("data:image/"):
                                    # Extract base64 data and format
                                    try:
                                        # Parse the data URL: data:image/png;base64,SGVsbG8...
                                        header, data = image_url.split(",", 1)
                                        format_part = header.split(";")[0].split("/")[
                                            1
                                        ]  # Extract 'png' from 'data:image/png'
                                        images.append((data, format_part))
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to parse image data URL: {e}"
                                        )
                                        await emitter.error_update(
                                            f"Failed to parse image data: {e}"
                                        )
                                        return f"Failed to parse image data: {e}"

            if images:
                await emitter.progress_update(
                    f"Found {len(images)} image(s), preparing for Anki..."
                )

                # Determine target fields for images
                # Check if any field has ANKI_IMAGE_PATH placeholder
                placeholder_fields = []
                placeholder_field_contents = {}
                for field_name, field_value in fields.items():
                    if "ANKI_IMAGE_PATH" in str(field_value):
                        placeholder_fields.append(field_name)
                        # Store original content but don't remove placeholder yet
                        placeholder_field_contents[field_name] = str(field_value)

                if placeholder_fields:
                    target_fields = placeholder_fields
                    await emitter.progress_update(
                        f"Images will be added to fields with ANKI_IMAGE_PATH: {placeholder_fields}"
                    )
                else:
                    # If no placeholder, add to the last field
                    if fields:
                        target_fields = [list(fields.keys())[-1]]
                        await emitter.progress_update(
                            f"No ANKI_IMAGE_PATH placeholder found, images will be added to field '{target_fields[0]}'"
                        )
                    else:
                        logger.error("No fields available to add images to")
                        await emitter.error_update(
                            "No fields available to add images to"
                        )
                        return "No fields available to add images to"

                # Prepare picture objects for addNote
                for i, (image_data, image_format) in enumerate(images):
                    filename = f"anki_image_{uuid.uuid4().hex[:8]}.{image_format}"
                    pictures.append(
                        {
                            "data": image_data,
                            "filename": filename,
                            "fields": target_fields,
                        }
                    )
                    await emitter.progress_update(
                        f"Prepared image {i+1}/{len(images)}: {filename}"
                    )

        tags = self.valves.tags
        if isinstance(tags, str):
            tags = self.valves.tags.split(",")

        # Verify all values are strings
        if not all(isinstance(value, str) for value in fields.values()):
            await emitter.error_update("All field values must be strings")
            return "All field values must be strings"

        if self.valves.fields_description not in self.create_flashcard.__func__.__doc__:
            message = f"The field description is not up to date anymore, please turn off then on again the anki tool to update the tool description. The new field description value is '{self.valves.fields_description}'"
            if self.fields_description != self.valves.fields_description:
                message += f"\nThe old field description is '{self.fields_description}'"
            await emitter.error_update(message)
            raise Exception(message)
        self.fields_description = self.valves.fields_description

        # checks that all fields of the example are found in the fields_description
        try:
            fd = json.loads(self.valves.fields_description)
            assert isinstance(fd, dict), f"Is not a dict but {type(fd)}"
            for k, v in fd.items():
                assert v.strip(), "Cannot contain empty values"
        except Exception as e:
            raise Exception(
                f"Error when parsing examples as json. It must be a json formatted list of dict. Error: '{e}'"
            )

        try:
            exs = json.loads(self.valves.examples)
            assert isinstance(exs, list), f"It's not a list but {type(exs)}"
            assert len(exs), "The list is empty"
            assert all(
                isinstance(ex, dict) for ex in exs
            ), "The list does not contain only dicts"
            assert len(exs) == len(
                set([json.dumps(ex) for ex in exs])
            ), "The list contains duplicates"
        except Exception as e:
            raise Exception(
                f"Error when parsing examples as json. It must be a json formatted list of dict. Error: '{e}'"
            )
        for ex in exs:
            for k, v in ex.items():
                assert (
                    k in fd
                ), f"An example mentions a field '{k}' that was not defined in the fields_description: {fd}."

        # check that all fields are appropriate
        for k, v in fields.items():
            assert (
                k in fd
            ), f"Field '{k}' of `fields` is not part of fields_description valve"

        try:
            await emitter.progress_update("Connecting to Anki...")

            # quick request to ankiconnect to check that the connection is working
            version = await _ankiconnect_request(
                self.valves.ankiconnect_host, self.valves.ankiconnect_port, "version"
            )
            if not isinstance(version, int):
                logger.error(
                    f"Unepected version check value from AnkiConnect: '{version}'"
                )
                await emitter.error_update(
                    f"Unepected version check value from AnkiConnect: '{version}'"
                )
                return f"Error when checking version of ankiconnect. Instead of an int received '{version}'"

            # # Verify Ankiconnect is working by checking that the deck exists
            # deck_list = await _ankiconnect_request(
            #     self.valves.ankiconnect_host, self.valves.ankiconnect_port, "deckNames"
            # )
            # assert (
            #     self.valves.deck in deck_list
            # ), f"Deck '{self.valves.deck}' was not found in the decks of anki. You must create it first."
            #
            # # also check modelname
            # models = await _ankiconnect_request(
            #     self.valves.ankiconnect_host, self.valves.ankiconnect_port, "modelNames"
            # )
            # assert (
            #     self.valves.notetype_name in models
            # ), f"Notetype '{self.valves.notetype_name}' was not found in the notetypes of anki. You must fix the valve first."

            await emitter.progress_update("Creating flashcard...")

            note = {
                "deckName": self.valves.deck,
                "modelName": self.valves.notetype_name,
                "fields": fields.copy(),
                "tags": tags,
            }

            # Add pictures to the note object if any were prepared
            if pictures:
                note["picture"] = pictures

            if self.valves.metadata_field:
                metadata = flatten_dict(__user__.copy())
                if "valves" in metadata:
                    del metadata["valves"]
                metadata["AnkiFlashcardCreatorVersion"] = self.VERSION
                metadata["__model__"] = flatten_dict(__model__)
                metadata["__metadata__"] = flatten_dict(__metadata__)

                # Add chat link if we have the URL and chat_id
                if (
                    self.valves.openwebui_url
                    and "__metadata__" in metadata
                    and "chat_id" in metadata["__metadata__"]
                ):
                    chat_url = f"{self.valves.openwebui_url}/c/{metadata['__metadata__']['chat_id']}"
                    chat_link = f'<p><a href="{chat_url}">View original chat</a></p>'
                else:
                    chat_link = ""

                metadata = json.dumps(metadata, indent=2, ensure_ascii=False)
                metadata = (
                    chat_link
                    + "<br>"
                    + '<pre><code class="language-json">'
                    + metadata
                    + "</code></pre>"
                )
                if self.valves.metadata_field in note["fields"]:
                    note["fields"][self.valves.metadata_field] += "<br>" + metadata
                else:
                    note["fields"][self.valves.metadata_field] = metadata
                # note["fields"][self.valves.metadata_field] = note["fields"][self.valves.metadata_field].replace("\r", "\n").replace("\n", "<br>")

            # Send the request with the note (pictures are now inside the note object)
            request_params = {"note": note}

            logger.info(f"Creating the following note: '{note}'")

            result = await _ankiconnect_request(
                self.valves.ankiconnect_host,
                self.valves.ankiconnect_port,
                "addNote",
                request_params,
            )

            assert isinstance(
                result, int
            ), f"Output of ankiconnect was not an note_id but: {result}"

            # Update fields to replace placeholders with actual image references
            if pictures and placeholder_fields:
                await emitter.progress_update(
                    "Updating fields with image references..."
                )

                # Create updated fields with image references
                updated_fields = {}
                for field_name in placeholder_fields:
                    original_content = placeholder_field_contents[field_name]

                    # Create image filename references for replacement
                    image_tags = []
                    for picture in pictures:
                        if field_name in picture["fields"]:
                            image_tags.append(picture["filename"])

                    # Replace placeholder with image tags
                    updated_content = original_content.replace(
                        "ANKI_IMAGE_PATH", "".join(image_tags)
                    )
                    updated_fields[field_name] = updated_content

                # Update the note fields
                update_params = {"note": {"id": result, "fields": updated_fields}}

                await _ankiconnect_request(
                    self.valves.ankiconnect_host,
                    self.valves.ankiconnect_port,
                    "updateNoteFields",
                    update_params,
                )

                await emitter.progress_update("Successfully updated fields with images")

            await emitter.progress_update("Syncing with AnkiWeb...")
            await _ankiconnect_request(
                self.valves.ankiconnect_host, self.valves.ankiconnect_port, "sync"
            )

            await emitter.success_update("Successfully created and synced flashcard")
            return f"Note ID: {result}"

        except Exception as e:
            await emitter.error_update(f"Failed to create flashcards: {str(e)}")
            return f"Failed to create flashcards: {str(e)}"


def flatten_dict(input: dict) -> dict:
    if not isinstance(input, dict):
        return input

    result = input.copy()
    while any(isinstance(v, dict) for v in result.values()):
        dict_found = False
        for k, v in list(
            result.items()
        ):  # Create a list to avoid modification during iteration
            if isinstance(v, dict):
                dict_found = True
                # Remove the current key-value pair
                del result[k]
                # Flatten and add the nested dictionary items
                for k2, v2 in v.items():
                    new_key = f"{k}_{k2}"
                    while new_key in result:
                        new_key = new_key + "_"
                    result[new_key] = v2
                break
            else:
                # Handle non-dictionary values
                try:
                    json.dumps(v)  # Just test if serializable
                except Exception:
                    result[k] = str(v)

    return result


async def _ankiconnect_request(
    host: str, port: str, action: str, params: dict = None
) -> Any:
    """Make a request to Ankiconnect API (async)"""
    address = f"{host}:{port}"
    request = {"action": action, "params": params or {}, "version": 6}

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.post(address, json=request) as response:
                response.raise_for_status()
                response_data = await response.json()
                if response_data.get("error"):
                    raise Exception(response_data["error"])
                return response_data["result"]
    except aiohttp.ClientError as e:
        raise Exception(f"Network error connecting to Ankiconnect: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON response from Ankiconnect: {str(e)}")
    except Exception as e:
        raise Exception(f"Ankiconnect error: {str(e)}")


def _ankiconnect_request_sync(
    host: str, port: str, action: str, params: dict = None
) -> Any:
    """Make a request to Ankiconnect API (sync)"""
    address = f"{host}:{port}"
    request = {"action": action, "params": params or {}, "version": 6}

    try:
        response = requests.post(address, json=request, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        if response_data.get("error"):
            raise Exception(response_data["error"])
        return response_data["result"]
    except requests.RequestException as e:
        raise Exception(f"Network error connecting to Ankiconnect: {str(e)}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON response from Ankiconnect: {str(e)}")
    except Exception as e:
        raise Exception(f"Ankiconnect error: {str(e)}")


def update_docstring(fields_description: str, rules: str, examples: str) -> str:
    assert rules.strip(), f"The rules valve cannot be empty"

    examples = examples.strip()
    assert examples, f"You must supply examples"

    try:
        exs = json.loads(examples)
        assert isinstance(exs, list), f"It's not a list but {type(exs)}"
        assert len(exs), "The list is empty"
        assert all(
            isinstance(ex, dict) for ex in exs
        ), "The list does not contain only dicts"
        assert len(exs) == len(
            set([json.dumps(ex) for ex in exs])
        ), "The list contains duplicates"
    except Exception as e:
        raise Exception(
            f"Error when parsing examples as json. It must be a json formatted list of dict. Error: '{e}'"
        )

    exs = "\n</card>\n<card>\n".join([json.dumps(ex, ensure_ascii=False) for ex in exs])
    examples = TEMPLATE_EXAMPLE.replace("EXAMPLES", exs)

    temp = TEMPLATE_DOCSTRING
    assert temp.count("RULES") == 1, "Found multiple RULES in the template"
    temp = temp.replace("RULES", rules)
    assert (
        temp.count("FIELDS_DESCRIPTION") == 1
    ), "Found multiple FIELDS_DESCRIPTION in the template"
    temp = temp.replace("FIELDS_DESCRIPTION", fields_description)
    assert temp.count("EXAMPLES") == 1, "Found multiple EXAMPLES in the template"
    temp = temp.replace("EXAMPLES", examples)
    docstring = temp.strip()

    logger.info(
        f"AnkiFlashcardCreator: Updated the docstring with this value:\n---\n{docstring}\n---"
    )
    return docstring


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        logger.info(f"AnkiFlashcardCreator: {description}")
        await self.emit(description)

    async def error_update(self, description):
        logger.info(f"AnkiFlashcardCreator: ERROR - {description}")
        await self.emit(description, "error", True)
        raise Exception(description)

    async def success_update(self, description):
        logger.info(f"AnkiFlashcardCreator: {description}")
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )
