"""
title: tool_compressor
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 2.0.0
date: 2025-02-21
license: GPLv3
description: A Filter that makes more compact the tool calls (removes the 'content' and/or 'results' element of the <details> escaped html tag in tool calls output. Otherwise the escaping gets really costly and is unreadable. If you remove both, the LLM still has access to the tool output.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/tool_compressor
requirements: bs4
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import re
from loguru import logger
from bs4 import BeautifulSoup



class Filter:
    VERSION: str = "2.0.0"
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=False,
            description="Use debug prints",
        )
        remove_results: bool = Field(
            default=True,
            description="Delete the results field",
        )
        remove_content: bool = Field(
            default=True,
            description="Delete the content field",
        )

    def __init__(self):
        self.valves = self.Valves()

    def log(self, message: str):
        if self.valves.debug:
            logger.info(f"ToolCompressor: {message}")

    def compress_tool_calls(self, text: str) -> str:
        # Check if there are any tool_calls details tags
        if "<details type=\"tool_calls\"" not in text:
            self.log("No tool_calls in message")
            return text

        # Use regex to find and modify details tags
        pattern = r'<details\s+([^>]*?)type="tool_calls"([^>]*?)>'
        
        def replace_attributes(match):
            attrs = match.group(1) + match.group(2)
            modified_attrs = attrs
            
            if self.valves.remove_content:
                modified_attrs = re.sub(r'content="[^"]*"', '', modified_attrs)
                
            if self.valves.remove_results:
                modified_attrs = re.sub(r'results="[^"]*"', '', modified_attrs)
                
            # Clean up any double spaces from removed attributes
            modified_attrs = re.sub(r'\s+', ' ', modified_attrs).strip()
            
            return f'<details {modified_attrs}>'
        
        modified_text = re.sub(pattern, replace_attributes, text)
        self.log("Processed tool_calls details tags")
        
        return modified_text
    
    # This method is no longer needed with the new approach

    async def inlet(
        self,
        body: dict,
        ) -> dict:
        self.log("Inlet")
        for im, m in enumerate(body["messages"]):
            body["messages"][im]["content"] = self.compress_tool_calls(m["content"])
        return body

    def outlet(
        self,
        body: dict,
        ) -> dict:
        self.log("Outlet")
        for im, m in enumerate(body["messages"]):
            body["messages"][im]["content"] = self.compress_tool_calls(m["content"])
        return body


if __name__ == "__main__":
    import sys
    import os
    
    if len(sys.argv) != 2:
        print("Usage: python tool_compressor.py <filename>")
        sys.exit(1)
    
    filename = sys.argv[1]
    
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        
        filter_instance = Filter()
        compressed_content = filter_instance.compress_tool_calls(content)
        
        print("\n--- COMPRESSED CONTENT ---\n")
        print(compressed_content)
        print("\n--- END OF COMPRESSED CONTENT ---\n")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)


