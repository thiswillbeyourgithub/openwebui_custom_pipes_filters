"""
title: wdocTool
author: thiswillbeyourgithub
openwebui_url: https://openwebui.com/t/qqqqqqqqqqqqqqqqqqqq/wdoctool
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
version: 1.4.1
license: GPLv3
description: use wdoc (cf github repo) as rag system to parse online stuff or summarize them. WIP because it can be used to do many more things! Note: as of open-webui 0.6.5, you HAVE to install my other tool 'userToolsOutput' to make wdoc's output appear as an assistant message.
"""

# TODO:
# - test that putting a gibberish API key in the env variable makes it indeed not work
# - add a tool to summarize files (either from the file parser or from the the file path itself)
# - add a tool to query data
#   - add a user valve to specify a path to use as a source of embeddings (make sure they are in a $username subfolder)

import os
import subprocess
import json
from typing import Callable, Any, Dict
import re
from pydantic import BaseModel, Field
import importlib
import sys
from pathlib import Path
from loguru import logger
from datetime import datetime

# disable import tricks, even though should be set by default in 2.7.0
os.environ["WDOC_IMPORT_TYPE"] = "native"

def normalize_dict_values(input_dict: Dict) -> Dict:
    """
    Iterates over a dictionary and converts string values of 'none', 'true', or 'false'
    (case-insensitive) to their Python equivalents (None, True, False).

    Args:
        input_dict: The dictionary to process

    Returns:
        A new dictionary with normalized values
    """
    result = {}
    for key, value in input_dict.items():
        if isinstance(value, str):
            lower_value = value.lower()
            if lower_value == "none":
                result[key] = None
            elif lower_value == "true":
                result[key] = True
            elif lower_value == "false":
                result[key] = False
            else:
                result[key] = value
        elif isinstance(value, dict):
            # Recursively process nested dictionaries
            result[key] = normalize_dict_values(value)
        else:
            result[key] = value
    return result


class Tools:

    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]
    APPROPRIATE_WDOC_VERSION: str = "3.0.0"

    class Valves(BaseModel):
        useracknowledgement: bool = Field(
            default=False,
            description="I have understood that I need to install the filter 'userToolsOutput' to make the summary appear directly in the LLM output.",
        )
        allowed_users_for_override: str = Field(
            default="",
            description="Comma-separated list of usernames that are allowed to override valves. If empty, no users can override.",
        )
        always_unimport_wdoc: bool = Field(
            default=False,
            description="If False, wdoc will be unimported after each use. If True, wdoc will remain imported.",
        )
        use_citations_for_summary: bool = Field(
            default=False,
            description="If True, use the citation system for summaries instead of outputting the text directly. Keep in mind that if using userToolsOutput with wdoc, your token might mention the whole summary twice so be careful if using multiturn chats!",
        )
        use_citations_for_parse: bool = Field(
            default=False,
            description="If True, use the citation system for parsed content instead of outputting the text directly.",
        )
        parse_before_summary: bool = Field(
            default=True,
            description="If True, parse the URL before summarizing to provide the full document as a citation.",
        )
        summary_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when summarizing",
        )
        parse_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when parsing",
        )
        env_variables_as_dict: str = Field(
            default='{"WDOC_LITELLM_USER": "$USER", "WDOC_LITELLM_TAGS": "open-webui", "WDOC_STRICT_DOCDICT": "False"}',
            description="JSON string of environment variables to set when using wdoc. Keys will be uppercased. If '$USER' is used in a value it will be replaced by the name of the open-webui user.",
        )
        pass

    class UserValves(BaseModel):
        override_summary_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when summarizing. This will be applied after the Valves.",
        )
        override_parse_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when parsing. This will be applied after the Valves.",
        )
        override_env_variables_as_dict: str = Field(
            default="{}",
            description="JSON string of environment variables to set when using wdoc. Keys will be uppercased. This will be applied after the Valves.",
        )
        pass

    def __init__(self):
        self.valves = self.Valves()
        self.citation = False  # to make my own citations
        self.on_valves_updated()

    def on_valves_updated(self) -> None:
        # Validate that the kwargs are valid JSON dictionaries
        self.summary_kwargs = json.loads(self.valves.summary_kwargs)
        assert isinstance(
            self.summary_kwargs, dict
        ), f"summary_kwargs must be a dictionary, got {type(self.summary_kwargs)}"
        self.summary_kwargs = normalize_dict_values(self.summary_kwargs)

        self.parse_kwargs = json.loads(self.valves.parse_kwargs)
        assert isinstance(
            self.parse_kwargs, dict
        ), f"parse_kwargs must be a dictionary, got {type(self.parse_kwargs)}"
        self.parse_kwargs = normalize_dict_values(self.parse_kwargs)

        self.env_variables = json.loads(self.valves.env_variables_as_dict)
        assert isinstance(
            self.env_variables, dict
        ), f"env_variables_as_dict must be a dictionary, got {type(self.env_variables)}"
        self.env_variables = normalize_dict_values(self.env_variables)

        # Check allowed users format
        assert isinstance(
            self.valves.allowed_users_for_override, str
        ), f"allowed_users_for_override must be a string, got {type(self.valves.allowed_users_for_override)}"
        self.allowed_users_for_override = [
            username.strip() for username in self.valves.allowed_users_for_override.split(',') if username.strip()
        ]

        assert isinstance(
            self.valves.always_unimport_wdoc, bool
        ), f"always_unimport_wdoc must be a boolean, got {type(self.valves.always_unimport_wdoc)}"
        self.always_unimport_wdoc = self.valves.always_unimport_wdoc

        assert isinstance(
            self.valves.use_citations_for_summary, bool
        ), f"use_citations_for_summary must be a boolean, got {type(self.valves.use_citations_for_summary)}"
        assert isinstance(
            self.valves.use_citations_for_parse, bool
        ), f"use_citations_for_parse must be a boolean, got {type(self.valves.use_citations_for_parse)}"
        assert isinstance(
            self.valves.parse_before_summary, bool
        ), f"parse_before_summary must be a boolean, got {type(self.valves.parse_before_summary)}"

    async def _parse_url_internal(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Internal method to parse a URL. Used by both parse_url and summarize_url.

        :param url: The URL of the online data to parse.
        :return: The parsed data as text.
        """
        emitter = EventEmitter(__event_emitter__)

        uvalves = dict(__user__.get("valves", {}))
        if uvalves and any(d != "{}" for d in uvalves.values()):
            # Check if user is in the allowed list
            user_allowed = __user__.get("name", "") in self.allowed_users_for_override
            if not user_allowed:
                error_msg = f"User '{__user__.get('name', '')}' is not allowed to override valves. Only these users can: {', '.join(self.allowed_users_for_override) or 'None'}"
                await emitter.error_update(error_msg)
                assert user_allowed, error_msg

        parse_kwargs = self.parse_kwargs.copy()
        override_parse_kwargs = uvalves.get("override_parse_kwargs", "{}")
        if isinstance(override_parse_kwargs, str):
            override_parse_kwargs = json.loads(override_parse_kwargs)
        assert isinstance(
            override_parse_kwargs, dict
        ), "override_parse_kwargs must be a JSON dictionary"
        override_parse_kwargs = normalize_dict_values(override_parse_kwargs)

        parse_kwargs.update(override_parse_kwargs)
        env_variables = self.env_variables.copy()
        override_env_variables_as_dict = uvalves.get(
            "override_env_variables_as_dict", "{}"
        )
        if isinstance(override_env_variables_as_dict, str):
            override_env_variables_as_dict = json.loads(override_env_variables_as_dict)
        assert isinstance(
            override_env_variables_as_dict, dict
        ), "override_env_variables_as_dict must be a JSON dictionary"
        override_env_variables_as_dict = normalize_dict_values(
            override_env_variables_as_dict
        )
        for k, v in override_env_variables_as_dict.items():
            if "WDOC_PRIVATE_MODE" == k:
                raise Exception(
                    f"Cannot set WDOC_PRIVATE_MODE from a user valve. Just to be safe."
                )
        env_variables.update(override_env_variables_as_dict)
        for k, v in env_variables.items():
            if isinstance(v, str) and "$USER" in v:
                env_variables[k] = v.replace("$USER", __user__.get("name", "Unknown"))

        with EnvVarContext(env_variables):
            wdoc = import_wdoc()
            # Check wdoc version
            check_wdoc_version(wdoc, self.APPROPRIATE_WDOC_VERSION)
            try:
                parsed = wdoc.wdoc.parse_file(
                    path=url,
                    filetype="auto",
                    format="langchain_dict",
                    **parse_kwargs,
                )
            except Exception as e:
                error_message = (
                    f"Error when parsing:\nArguments were: '{parse_kwargs}'\n{e}"
                )
                await emitter.error_update(error_message)
                raise
            finally:
                if not self.always_unimport_wdoc:
                    un_import_wdoc()

        if len(parsed) == 1:
            content = parsed[0]["page_content"]
        else:
            content = "\n\n".join([p["page_content"] for p in parsed])

        title = None
        try:
            title = parsed[0]["metadata"]["title"]
            content = f"Success.\n\n## Parsing of {title}\n\n{content}\n\n---\n\n"
        except Exception as e:
            await emitter.progress_update(f"Error when getting title: '{e}'")
            content = f"Success.\n\n## Parsing of {url}\n\n{content}\n\n---\n\n"

        assert content.strip(), "Empty output of _parse_url_internal"

        return content

    async def parse_url(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Parse a url using the wdoc rag library. After being parsed,
        the content will be shown to the user so DO NOT repeat this tool's
        output yourself and instead just tell the user that it went successfuly.

        :param url: The URL of the online data to parse.
        :return: The parsed data as text, or an error message.
        """
        if not self.valves.useracknowledgement:
            raise Exception("ERROR: You need to ask the admin to manually check the first valve.")
        emitter = EventEmitter(__event_emitter__)
        self.on_valves_updated()

        await emitter.progress_update(f"Parsing '{url}'")

        try:
            content = await self._parse_url_internal(url, __event_emitter__, __user__)
        except Exception as e:
            # Error already reported in _parse_url_internal
            raise

        await emitter.success_update(f"Successfully parsed '{url}'")

        if self.valves.use_citations_for_parse:
            # Try to extract title from the content
            title_match = re.search(r"## Parsing of (.+?)\n", content)
            title = title_match.group(1) if title_match else "Parsed Content"

            await emitter.cite_parser(
                doc_content=content,
                title=title,
                url=url,
            )
            return "Parsing completed successfully. Please check the citations panel to view the results."
        else:
            return content

    async def summarize_url(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Get back a summary of the data at a given url using the wdoc rag library.
        The summary will be directly shown to the user so DO NOT repeat this tool's
        output yourself and instead just tell the user that the summary went successfuly.
        After this tool returned a summary, compress the summary into a
        SINGLE sentence unless explicitely asked to do otherwise.
        If this tool fail, do not try the parsing tool right away and ask the user what to do.

        :param url: The URL of the online data to summarize.
        :return: The summary as text, or an error message.
        """
        if not self.valves.useracknowledgement:
            raise Exception("ERROR: You need to ask the admin to manually check the first valve.")
        emitter = EventEmitter(__event_emitter__)
        self.on_valves_updated()

        await emitter.progress_update(f"Summarizing '{url}'")

        # If parse_before_summary is enabled, parse the URL first
        if self.valves.parse_before_summary:
            await emitter.progress_update(
                f"First parsing '{url}' to provide full document access"
            )
            try:
                parsed_content = await self._parse_url_internal(
                    url, __event_emitter__, __user__
                )
                if self.valves.use_citations_for_parse:
                    await emitter.cite_parser(
                        doc_content=parsed_content,
                        title="Full Document",
                        url=url,
                    )
            except Exception as e:
                await emitter.progress_update(
                    f"Warning: Failed to parse document before summarizing: {e}"
                )

        uvalves = dict(__user__.get("valves", {}))
        if uvalves and any(d != "{}" for d in uvalves.values()):
            # Check if user is in the allowed list
            user_allowed = __user__.get("name", "") in self.allowed_users_for_override
            if not user_allowed:
                error_msg = f"User '{__user__.get('name', '')}' is not allowed to override valves. Only these users can: {', '.join(self.allowed_users_for_override) or 'None'}"
                await emitter.error_update(error_msg)
                assert user_allowed, error_msg

        summary_kwargs = self.summary_kwargs.copy()
        override_summary_kwargs = uvalves.get("override_summary_kwargs", "{}")
        if isinstance(override_summary_kwargs, str):
            override_summary_kwargs = json.loads(override_summary_kwargs)
        assert isinstance(
            override_summary_kwargs, dict
        ), "override_summary_kwargs must be a JSON dictionary"
        override_summary_kwargs = normalize_dict_values(override_summary_kwargs)

        summary_kwargs.update(override_summary_kwargs)
        env_variables = self.env_variables.copy()
        override_env_variables_as_dict = uvalves.get(
            "override_env_variables_as_dict", "{}"
        )
        if isinstance(override_env_variables_as_dict, str):
            override_env_variables_as_dict = json.loads(override_env_variables_as_dict)
        assert isinstance(
            override_env_variables_as_dict, dict
        ), "override_env_variables_as_dict must be a JSON dictionary"
        override_env_variables_as_dict = normalize_dict_values(
            override_env_variables_as_dict
        )
        for k, v in override_env_variables_as_dict.items():
            if "WDOC_PRIVATE_MODE" == k:
                raise Exception(
                    "Cannot set WDOC_PRIVATE_MODE from a user valve. Just to be safe."
                )
        env_variables.update(override_env_variables_as_dict)
        for k, v in env_variables.items():
            if isinstance(v, str) and "$USER" in v:
                env_variables[k] = v.replace("$USER", __user__.get("name", "Unknown"))

        with EnvVarContext(env_variables):
            wdoc = import_wdoc()
            # Check wdoc version
            check_wdoc_version(wdoc, self.APPROPRIATE_WDOC_VERSION)
            try:
                instance = wdoc.wdoc(
                    path=url, task="summarize", filetype="auto", **summary_kwargs
                )
                if not hasattr(instance, "summary_results"):
                    logger.info("Starting the task 'summary' of wdoc")
                    results = instance.summary_task()
                else:
                    results: dict = instance.summary_results
            except Exception as e:
                error_message = (
                    f"Error when summarizing:\nArguments were: '{summary_kwargs}'\n{e}"
                )
                await emitter.error_update(error_message)
                raise
            finally:
                if not self.always_unimport_wdoc:
                    un_import_wdoc()

        await emitter.success_update(f"Successfully summarized {url}")
        summary = results["summary"]
        if results["doc_total_tokens"] == 0:
            cache_mess = ", probably because cached"
        else:
            cache_mess = ""
        metadata = f"(Saved you {round(results['doc_reading_length'])} minutes for ${results['doc_total_cost']:.5f} ({results['doc_total_tokens']} tokens{cache_mess})"
        if self.valves.use_citations_for_summary:
            output = f"""

--- 

# Summary
{url}

{metadata}

{summary}

--- 

"""
            # add the metadata at the end too
            if len(summary.splitlines()) > 50:
                output += f"\n{metadata}"

            await emitter.cite_summary(
                doc_content=output,
                title="Summary",
                url=url,
                dollar_cost=results["doc_total_cost"],
                tokens=results["doc_total_tokens"],
                time_saved=round(results["doc_reading_length"]),
            )
            return "Summary completed successfully. Please check the citations panel to view the results."
        else:
            output = f"""Summary succesful. Read it below.

<userToolsOutput>

<details open="">

<summary>Summary of {url}</summary>

{metadata}

{summary}

</details>

</userToolsOutput>
"""
            return output


class EnvVarContext:
    """Context manager for temporarily setting environment variables."""

    def __init__(self, env_vars: dict):
        """
        Initialize with a dictionary of environment variables to set.

        Args:
            env_vars: Dictionary where keys are environment variable names
                     and values are their values. Keys will be uppercased.
        """
        self.env_vars = {k.upper(): str(v) for k, v in env_vars.items()}
        self.original_values = {}

    def __enter__(self):
        # Store original values and set new values
        for key, value in self.env_vars.items():
            if key in os.environ:
                self.original_values[key] = os.environ[key]
            else:
                self.original_values[key] = None
            os.environ[key] = value
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original environment
        for key in self.env_vars:
            if self.original_values[key] is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = self.original_values[key]


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        logger.info(description)
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

    async def cite_summary(
        self,
        doc_content: str,
        title: str,
        url: str,
        time_saved: int,
        dollar_cost: float,
        tokens: int,
    ):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "citation",
                    "data": {
                        "document": [doc_content],
                        "metadata": [
                            {
                                "date_accessed": datetime.now().isoformat(),
                                "source": title,
                                "time saved": time_saved,
                                "cost in dollars": dollar_cost,
                                "cost in tokens": tokens,
                            }
                        ],
                        "source": {"name": "Summary", "url": url},
                    },
                }
            )

    async def cite_parser(
        self,
        doc_content: str,
        title: str,
        url: str,
    ):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "citation",
                    "data": {
                        "document": [doc_content],
                        "metadata": [
                            {
                                "date_accessed": datetime.now().isoformat(),
                                "source": title,
                            }
                        ],
                        "source": {"name": "Parsed Content", "url": url},
                    },
                }
            )


def import_wdoc():
    importlib.invalidate_caches()
    return importlib.import_module("wdoc")  # Reimport


def check_wdoc_version(wdoc_module, minimum_version: str) -> None:
    """
    Check if the imported wdoc version meets the minimum requirement.

    Args:
        wdoc_module: The imported wdoc module
        minimum_version: The minimum required version as a string (e.g., "2.6.10")
    """
    try:
        current_version = wdoc_module.wdoc.VERSION

        # Convert version strings to comparable integers
        def version_to_int(version_str: str) -> int:
            parts = version_str.split(".")
            # Multiply each part by the appropriate power of 10
            # e.g., "2.6.10" -> 2*100 + 6*10 + 10*1 = 270
            result = 0
            for i, part in enumerate(reversed(parts)):
                result += int(part) * (10**i)
            return result

        current_int = version_to_int(current_version)
        minimum_int = version_to_int(minimum_version)

        if current_int < minimum_int:
            logger.warning(
                f"Installed wdoc version {current_version} is older than the minimum required version {minimum_version}. Some features may not work correctly."
            )
    except Exception as e:
        logger.warning(f"Failed to check wdoc version: {e}")


def un_import_wdoc():
    del sys.modules["wdoc"]
    importlib.invalidate_caches()


# force unimporting wdoc to test import it
if "wdoc" in sys.modules:
    try:
        un_import_wdoc()
    except Exception as e:
        logger.error(f"Error when un importing wdoc before installing/updating it: '{e}'")

# install wdoc if not present already
try:
    import wdoc
except ImportError as e:
    logger.warning(f"ImportError for wdoc before trying to install/update it: '{e}'")

if Path("/app/backend/requirements.txt").exists():
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "install",
            # "-U",
            "--reinstall",
            "--overrides",
            "/app/backend/requirements.txt",  # to make sure we don't remove any dependency from open-webui
            "wdoc>=" + Tools.APPROPRIATE_WDOC_VERSION,
            "langchain-core>=0.3.37",  #  apparently needed for smooth installation as of open-webui 0.6.5
            "--system",
        ]
    )
else:
    logger.error(f"No /app/backend/requirements.txt file found")


try:
    import wdoc
    un_import_wdoc()
except Exception as e:
    raise Exception(f"Couldn't import wdoc after installation: '{e}'")
