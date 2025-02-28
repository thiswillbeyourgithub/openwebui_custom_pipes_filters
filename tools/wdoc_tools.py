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
# - add valves to set the parameters for wdoc
# - add a user valve to specify a path to use as a source of embeddings (make sure they are in a $username subfolder)
# - add a way to query data
# - leverage open-webui's citations for the sources

import os
import requests
from typing import Callable, Any
import re
from pydantic import BaseModel, Field
from pydantic import BaseModel, Field
from typing import Literal, Optional
import importlib


# install wdoc
import sys
import subprocess
subprocess.check_call([
    sys.executable, "-m", "uv", "pip",
    "install",
    "-U",
    "--overrides", "/app/backend/requirements.txt",  # to make sure we don't remove any dependency from open-webui
    "wdoc>=2.6.5",
    "--system"
])



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


    def __init__(self):
        self.on_valves_updated()

    def on_valves_updated(self) -> None:
        self.valves = self.Valves()
        for attr in dir(self.valves):
            if attr.startswith("WDOC_"):
                os.environ[attr] = getattr(self.valves, attr)
        if "wdoc" in sys.modules:
            importlib.reload(wdoc)
        else:
            import wdoc

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

        :param url: The URL of the online data to summarize.
        :return: The summary as text, or an error message.
        """
        emitter = EventEmitter(__event_emitter__)

        await emitter.progress_update(f"Summarizing '{url}'")

        try:
            instance = wdoc.wdoc(
                path=url,
                task="summarize",
                filetype="auto",
            )
        except Exception as e:
            url2 = re.sub(r"\((http[^)]+)\)", "", url)
            try:
                instance = wdoc.wdoc(
                    path=url2,
                    task="summarize",
                    filetype="auto",
                )
                url = url2
            except Exception as e2:
                error_message=f"Error when summarizing:\nFirst error: {e}\nSecond error: {e2}"
                await emitter.error_update(error_message)

        results: dict = instance.summary_results
        summary = results['summary']
        output = f"""

# Summary
{url}

{summary}

- Total cost of those summaries: '{results['doc_total_tokens']}' (${results['doc_total_cost']:.5f})
- Total time saved by those summaries: {results['doc_reading_length']:.1f} minutes
"""

        await emitter.success_update(
            f"Successfully summarized {url}"
        )
        return output


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)
        raise Exception(description)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        print(f"wdocParser: {description}")
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

