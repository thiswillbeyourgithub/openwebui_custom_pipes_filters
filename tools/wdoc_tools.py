"""
title: wdocParser
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
description: Use wdoc to parse urls and files
funding_url: https://github.com/open-webui
version: 1.0.0
license: GPLv3
# requirements: wdoc>=2.6.7  # commented to instead install it in the tool itself and avoid uninstalling open-webui dependencies
description: use wdoc (cf github repo) as rag system to parse online stuff or summarize them. WIP because it can be used to do many more things!
"""

# TODO:
# - leverage open-webui's citations for the sources of queries: https://docs.openwebui.com/features/plugin/tools/
# - add a tool to query data
# - add a user valve to specify a path to use as a source of embeddings (make sure they are in a $username subfolder)

import os
import subprocess
import requests
import json
from typing import Callable, Any, Literal, Optional
import re
from pydantic import BaseModel, Field, validator
import importlib
import sys
from pathlib import Path
from loguru import logger
from datetime import datetime

# disable import tricks
os.environ["WDOC_IMPORT_TYPE"] = "native"

# install wdoc if not present already
try:
    import wdoc
except ImportError as e:
    logger.info("wdoc needs to be installed")
if Path('/app/backend/requirements.txt').exists():
    subprocess.check_call([
        sys.executable,
        "-m",
        "uv",
        "pip",
        "install",
        #"-U",
        "--reinstall",
        "--overrides",
        "/app/backend/requirements.txt",  # to make sure we don't remove any dependency from open-webui
        "wdoc>=2.6.10",
        "--system"
    ])


try:
    import wdoc
    del sys.modules['wdoc']
except Exception as e:
    raise Exception(f"Couldn't import wdoc: '{e}'")


class Tools:

    VERSION: str = "1.0.0"
    MINIMUM_WDOC_VERSION: str = "2.6.10"

    class Valves(BaseModel):
        allow_user_valves_override: bool = Field(
            default=True,
            description="If True then we allow user valves to override the Valves dicts. If False UserValves raise an exeception."
        )
        always_unimport_wdoc: bool = Field(
            default=False,
            description="If False, wdoc will be unimported after each use. If True, wdoc will remain imported."
        )
        use_citations: bool = Field(
            default=False,
            description="If True, use the citation system for summaries instead of outputting the text directly."
        )
        use_citations_for_parse: bool = Field(
            default=False,
            description="If True, use the citation system for parsed content instead of outputting the text directly."
        )
        summary_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when summarizing"
        )
        parse_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when parsing"
        )
        env_variables_as_dict: str = Field(
            default='{"WDOC_LITELLM_USER": "$USER", "WDOC_LITELLM_TAGS": "open-webui", "WDOC_STRICT_DOCDICT": "False"}',
            description="JSON string of environment variables to set when using wdoc. Keys will be uppercased. If '$USER' is used in a value it will be replaced by the name of the open-webui user."
        )
        pass


    class UserValves(BaseModel):
        override_summary_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when summarizing. This will be applied after the Valves."
        )
        override_parse_kwargs: str = Field(
            default="{}",
            description="JSON string of kwargs to pass to wdoc when parsing. This will be applied after the Valves."
        )
        override_env_variables_as_dict: str = Field(
            default="{}",
            description="JSON string of environment variables to set when using wdoc. Keys will be uppercased. This will be applied after the Valves."
        )
        pass



    def __init__(self):
        self.valves = self.Valves()
        self.citation = False  # to make my own citations
        self.on_valves_updated()

    def on_valves_updated(self) -> None:
        # Validate that the kwargs are valid JSON dictionaries
        self.summary_kwargs = json.loads(self.valves.summary_kwargs)
        assert isinstance(self.summary_kwargs, dict), f"summary_kwargs must be a dictionary, got {type(self.summary_kwargs)}"
        
        self.parse_kwargs = json.loads(self.valves.parse_kwargs)
        assert isinstance(self.parse_kwargs, dict), f"parse_kwargs must be a dictionary, got {type(self.parse_kwargs)}"
        
        self.env_variables = json.loads(self.valves.env_variables_as_dict)
        assert isinstance(self.env_variables, dict), f"env_variables_as_dict must be a dictionary, got {type(self.env_variables)}"
        
        # Check types of boolean valves
        assert isinstance(self.valves.allow_user_valves_override, bool), f"allow_user_valves_override must be a boolean, got {type(self.valves.allow_user_valves_override)}"
        self.allow_user_valves_override = self.valves.allow_user_valves_override
        
        assert isinstance(self.valves.always_unimport_wdoc, bool), f"always_unimport_wdoc must be a boolean, got {type(self.valves.always_unimport_wdoc)}"
        self.always_unimport_wdoc = self.valves.always_unimport_wdoc
        
        assert isinstance(self.valves.use_citations, bool), f"use_citations must be a boolean, got {type(self.valves.use_citations)}"
        assert isinstance(self.valves.use_citations_for_parse, bool), f"use_citations_for_parse must be a boolean, got {type(self.valves.use_citations_for_parse)}"

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
        emitter = EventEmitter(__event_emitter__)
        self.on_valves_updated()

        await emitter.progress_update(f"Parsing '{url}'")

        uvalves = dict(__user__.get("valves", {}))
        if uvalves and any(d != "{}" for d in uvalves.values()) and not self.allow_user_valves_override:
            await emitter.error_update(f"You are trying to use a UserValve but the Valves of WdocTool don't allow it.\n{uvalves}")
            assert self.allow_user_valves_override, f"You are trying to use a UserValve but the Valves of WdocTool don't allow it.\n{uvalves}"

        parse_kwargs = self.parse_kwargs.copy()
        override_parse_kwargs = uvalves.get("override_parse_kwargs", "{}")
        if isinstance(override_parse_kwargs, str):
            override_parse_kwargs = json.loads(override_parse_kwargs)
        assert isinstance(override_parse_kwargs, dict), "override_parse_kwargs must be a JSON dictionary"
        parse_kwargs.update(override_parse_kwargs)
        env_variables = self.env_variables.copy()
        override_env_variables_as_dict = uvalves.get("override_env_variables_as_dict", "{}")
        if isinstance(override_env_variables_as_dict, str):
            override_env_variables_as_dict = json.loads(override_env_variables_as_dict)
        assert isinstance(override_env_variables_as_dict, dict), "override_env_variables_as_dict must be a JSON dictionary"
        for k, v in override_env_variables_as_dict.items():
            if "WDOC_PRIVATE_MODE" == k:
                raise Exception(f"Cannot set WDOC_PRIVATE_MODE from a user valve. Just to be safe.")
        env_variables.update(override_env_variables_as_dict)
        for k, v in env_variables.items():
            if isinstance(v, str) and "$USER" in v:
                env_variables[k] = v.replace("$USER", __user__.get("name", "Unknown"))

        with EnvVarContext(env_variables):
            wdoc = import_wdoc()
            try:
                parsed = wdoc.wdoc.parse_file(
                    path=url,
                    filetype="auto",
                    format="langchain_dict",
                    **parse_kwargs,
                )
            except Exception as e:
                error_message=f"Error when parsing:\nArguments were: '{parse_kwargs}'\n{e}"
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

        await emitter.success_update(
            f"Successfully parsed '{title if title else url}'"
        )
        
        if self.valves.use_citations_for_parse:
            await emitter.cite(
                doc_content=content,
                title=title if title else "Parsed Content",
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
        If this tool fail, do not try the parsing tool right away and ask the user what to do.

        :param url: The URL of the online data to summarize.
        :return: The summary as text, or an error message.
        """
        emitter = EventEmitter(__event_emitter__)
        self.on_valves_updated()

        await emitter.progress_update(f"Summarizing '{url}'")

        uvalves = dict(__user__.get("valves", {}))
        if uvalves and any(d != "{}" for d in uvalves.values()) and not self.allow_user_valves_override:
            await emitter.error_update(f"You are trying to use a UserValve but the Valves of WdocTool don't allow it.\n{uvalves}")
            assert self.allow_user_valves_override, f"You are trying to use a UserValve but the Valves of WdocTool don't allow it.\n{uvalves}"

        summary_kwargs = self.summary_kwargs.copy()
        override_summary_kwargs = uvalves.get("override_summary_kwargs", "{}")
        if isinstance(override_summary_kwargs, str):
            override_summary_kwargs = json.loads(override_summary_kwargs)
        assert isinstance(override_summary_kwargs, dict), "override_summary_kwargs must be a JSON dictionary"
        summary_kwargs.update(override_summary_kwargs)
        env_variables = self.env_variables.copy()
        override_env_variables_as_dict = uvalves.get("override_env_variables_as_dict", "{}")
        if isinstance(override_env_variables_as_dict, str):
            override_env_variables_as_dict = json.loads(override_env_variables_as_dict)
        assert isinstance(override_env_variables_as_dict, dict), "override_env_variables_as_dict must be a JSON dictionary"
        for k, v in override_env_variables_as_dict.items():
            if "WDOC_PRIVATE_MODE" == k:
                raise Exception(f"Cannot set WDOC_PRIVATE_MODE from a user valve. Just to be safe.")
        env_variables.update(override_env_variables_as_dict)
        for k, v in env_variables.items():
            if isinstance(v, str) and "$USER" in v:
                env_variables[k] = v.replace("$USER", __user__.get("name", "Unknown"))

        with EnvVarContext(env_variables):
            wdoc = import_wdoc()
            try:
                instance = wdoc.wdoc(
                    path=url,
                    task="summarize",
                    filetype="auto",
                    **summary_kwargs
                )
            except Exception as e:
                error_message=f"Error when summarizing:\nArguments were: '{summary_kwargs}'\n{e}"
                await emitter.error_update(error_message)
                raise
            finally:
                if not self.always_unimport_wdoc:
                    un_import_wdoc()

        results: dict = instance.summary_results
        summary = results['summary']
        output = f"""

# Summary
{url}

- Total cost of those summaries: '{results['doc_total_tokens']}' (${results['doc_total_cost']:.5f})
- Total time saved by those summaries: {results['doc_reading_length']:.1f} minutes

--- 

{summary}

"""

        await emitter.success_update(
            f"Successfully summarized {url}"
        )
        if self.valves.use_citations:
            await emitter.cite(
                doc_content=output,
                title="Summary",
                url=url,
            )
            return "Summary completed successfully. Please check the citations panel to view the results."
        else:
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
        logger.info(f"wdoctool: {description}")
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

    async def cite(self, doc_content: str, title: str, url: str):
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
                    "source": {"name": "Summary", "url": url},
                },
            }
        )

def import_wdoc():
    importlib.invalidate_caches()
    return importlib.import_module('wdoc')  # Reimport

def un_import_wdoc():
    del sys.modules['wdoc']
    importlib.invalidate_caches()
