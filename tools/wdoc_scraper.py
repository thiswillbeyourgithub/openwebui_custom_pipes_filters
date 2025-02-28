"""
title: wdocParser
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
description: Use wdoc to parse urls and files
funding_url: https://github.com/open-webui
version: 0.0.1
license: GPLv3
# requirements: wdoc>=2.6.5  # commented to instead install it in the tool itself and avoid uninstalling open-webui dependencies
"""

# install wdoc here
import sys
import subprocess
subprocess.check_call([
    sys.executable, "-m", "uv", "pip",
    "install",
    "--overrides", "/app/backend/requirements.txt",
    "wdoc>=2.6.5",
    "--system"
])

import requests
from typing import Callable, Any
import re
from pydantic import BaseModel, Field

from wdoc import wdoc


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


class Tools:
    class Valves(BaseModel):
        CITATION: bool = Field(
            default="True", description="True or false for citation"
        )

    def __init__(self):
        self.valves = self.Valves()
        self.citation = self.valves.CITATION

    async def parse_url(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Scrape and process a web page using wdoc

        :param url: The URL of the web page to scrape.
        :return: The scraped and processed webpage content, or an error message.
        """
        emitter = EventEmitter(__event_emitter__)

        await emitter.progress_update(f"Scraping '{url}'")

        try:
            parsed = wdoc.parse_file(
                path=url,
                filetype="auto",
                format="langchain_dict",
            )
        except Exception as e:
            url2 = re.sub(r"\((http[^)]+)\)", "", url)
            try:
                parsed = wdoc.parse_file(
                    path=url2,
                    filetype="auto",
                    format="langchain_dict",
                )
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
        except Exception as e:
            await emitter.progress_update(f"Error when getting title: '{e}'")

        await emitter.success_update(
            f"Successfully Scraped {title if title else url}"
        )
        return content
