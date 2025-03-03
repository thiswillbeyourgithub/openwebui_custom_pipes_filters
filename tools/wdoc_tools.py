"""
title: wdocParser
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
description: Use wdoc to parse urls and files
funding_url: https://github.com/open-webui
version: 2.6.5
license: GPLv3
# requirements: wdoc>=2.6.5  # commented to instead install it in the tool itself and avoid uninstalling open-webui dependencies
description: use wdoc (cf github repo) as rag system to parse online stuff or summarize them. WIP because it can be used to do many more things!
"""

# TODO:
# - append the user name to wdoc's user identifier for langfuse
# - add a decorator to overload the env variable only temporarily, otherwise we can't have different values for different users
# - add a user valve to specify a path to use as a source of embeddings (make sure they are in a $username subfolder)
# - add a tool to query data
# - leverage open-webui's citations for the sources of queries

import os
import requests
from typing import Callable, Any, Literal, Optional
import re
from pydantic import BaseModel, Field
import importlib
import sys
from pathlib import Path


# install wdoc
if Path('/app/backend/requirements.txt').exists():  # for debug
    import subprocess
    subprocess.check_call([
        sys.executable, "-m", "uv", "pip",
        "install",
        "-U",
        "--overrides", "/app/backend/requirements.txt",  # to make sure we don't remove any dependency from open-webui
        "wdoc>=2.6.5",
        "--system"
    ])

import wdoc


class Tools:

    VERSION: str = "2.6.5"

    class Valves(BaseModel):
        WDOC_TYPECHECKING: Literal["disabled", "warn", "crash"] = Field(
            default="warn",
            description="Type checking behavior for the Whisper Doc service."
        )
        WDOC_NO_MODELNAME_MATCHING: bool = Field(
            default=True,
            description="Whether to disable model name matching."
        )
        WDOC_ALLOW_NO_PRICE: bool = Field(
            default=False,
            description="Whether to allow documents without a price."
        )
        WDOC_OPEN_ANKI: bool = Field(
            default=False,
            description="Whether to open Anki for document processing."
        )
        WDOC_STRICT_DOCDICT: bool = Field(
            default=False,
            description="Whether to enforce strict dictionary checking for documents."
        )
        WDOC_MAX_LOADER_TIMEOUT: int = Field(
            default=-1,
            description="Maximum timeout for the document loader in milliseconds."
        )
        WDOC_MAX_PDF_LOADER_TIMEOUT: int = Field(
            default=-1,
            description="Maximum timeout for the PDF loader in milliseconds. Disabled by default."
        )
        WDOC_PRIVATE_MODE: bool = Field(
            default=False,
            description="Whether to enable private mode for document processing."
        )
        WDOC_DEBUGGER: bool = Field(
            default=False,
            description="Whether to enable debugging mode."
        )
        WDOC_EXPIRE_CACHE_DAYS: int = Field(
            default=0,
            description="Number of days before cache expires."
        )
        WDOC_EMPTY_LOADER: bool = Field(
            default=False,
            description="Whether to allow empty content in the loader."
        )
        WDOC_BEHAVIOR_EXCL_INCL_USELESS: Literal["warn", "crash"] = Field(
            default="warn",
            description="Behavior for including or excluding useless data."
        )
        WDOC_IMPORT_TYPE: Literal["native", "lazy", "thread", "both"] = Field(
            default="thread",
            description="Type of import to use for document processing."
        )
        WDOC_MOD_FAISS_SCORE_FN: bool = Field(
            default=False,
            description="Whether to modify the FAISS score function."
        )
        WDOC_LLM_MAX_CONCURRENCY: int = Field(
            default=15,
            description="Maximum number of concurrent LLM requests."
        )
        WDOC_SEMANTIC_BATCH_MAX_TOKEN_SIZE: int = Field(
            default=1000,
            description="Maximum token size for semantic batch processing."
        )
        WDOC_MAX_CHUNK_SIZE: int = Field(
            default=16_000,
            description="Maximum chunk size for document processing."
        )
        WDOC_DEFAULT_MODEL: str = Field(
            default="anthropic/claude-3-7-sonnet-20250219",
            description="Default model to use for document processing."
        )
        WDOC_DEFAULT_EMBED_MODEL: str = Field(
            default="openai/text-embedding-3-small",
            description="Default embedding model to use."
        )
        WDOC_DEFAULT_EMBED_DIMENSION: Optional[int] = Field(
            default=None,
            description="Default dimension for embeddings."
        )
        WDOC_EMBED_TESTING: bool = Field(
            default=True,
            description="Whether to enable embedding testing."
        )
        WDOC_DEFAULT_QUERY_EVAL_MODEL: str = Field(
            default="anthropic/claude-3-5-haiku-20241022",
            description="Default model for query evaluation."
        )
        WDOC_LANGFUSE_PUBLIC_KEY: Optional[str] = Field(
            default=None,
            description="Public key for Langfuse integration."
        )
        WDOC_LANGFUSE_SECRET_KEY: Optional[str] = Field(
            default=None,
            description="Secret key for Langfuse integration."
        )
        WDOC_LANGFUSE_HOST: Optional[str] = Field(
            default=None,
            description="Host address for Langfuse integration."
        )
        ANTHROPIC_API_KEY: str = Field(default=None, description="Anthropic API key.")

    def __init__(self):
        self.citation = True
        self.on_valves_updated()

    def on_valves_updated(self) -> None:
        self.valves = self.Valves()
        for attr in dir(self.valves):
            if not attr.startswith("WDOC_") and not attr.endswith("_API_KEY"):
                continue
            val = getattr(self.valves, attr)
            if val and  val != self.valves.model_fields[attr].default:
                print(f"Overloading {attr} to '{val}'")
                os.environ[attr] = str(val)
        nuclear_reload("wdoc")

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

        try:
            parsed = wdoc.wdoc.parse_file(
                path=url,
                filetype="auto",
                format="langchain_dict",
            )
        except Exception as e:
            url2 = re.sub(r"\((http[^)]+)\)", "", url)
            try:
                parsed = wdoc.wdoc.parse_file(
                    path=url2,
                    filetype="auto",
                    format="langchain_dict",
                )
                url = url2
            except Exception as e2:
                error_message=f"Error when parsing:\nFirst error: {e}\nSecond error: {e2}"
                await emitter.error_update(error_message)

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
        os.environ["ANTHROPIC_API_KEY"] = str(self.Valves().model_fields["ANTHROPIC_API_KEY"])
        instance = None
        error_message = ""

        try:
            instance = wdoc.wdoc(
                path=url,
                task="summarize",
                filetype="auto",
            )

        except Exception as e:
            error_message = f"Error when summarizing: {e}"
            await emitter.progress_update(error_message)

        output = ""
        if instance:
            results: dict = instance.summary_results
            summary = results["summary"]
            output = f"""
# Summary
{url}

{summary}

- Total cost of those summaries: '{results['doc_total_tokens']}' (${results['doc_total_cost']:.5f})
- Total time saved by those summaries: {results['doc_reading_length']:.1f} minutes

Just echo the full Summary above verbatim, do not abridge, process or analyze in any form.
"""
            await emitter.success_update(f"Successfully summarized {url}")
        else:
            output = error_message
            await emitter.error_update(f"Error summarizing {url}")

        return output

class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)
        # raise Exception(description)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        print(f"wdoctool: {description}")
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


def nuclear_reload(package_name):
    """The most aggressive reload possible."""
    # Unload the package and all its dependencies
    to_remove = [m for m in sys.modules if m == package_name or m.startswith(package_name + '.')]
    for module in to_remove:
        if str(module) in sys.modules:
            del sys.modules[module]

    importlib.import_module("wdoc")
