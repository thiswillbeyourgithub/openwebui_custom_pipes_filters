"""
title: tool_compressor
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.1
date: 2025-02-21
license: GPLv3
description: A Filter that makes more compact the tool calls (turn the <details> escaped html (token expensive!) into regular unescaped html, or even removed.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/tool_compressor
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import re
from loguru import logger
from bs4 import BeautifulSoup



class Filter:
    VERSION: str = "1.0.1"
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=True,
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

        # Parse the entire text with BeautifulSoup
        soup = BeautifulSoup(text, 'html.parser')
        
        # Find all details tags with type="tool_calls"
        details_tags = soup.find_all('details', attrs={"type": "tool_calls"})
        
        if not details_tags:
            self.log("No tool_calls details tags found after parsing")
            return text
            
        self.log(f"Found {len(details_tags)} tool_calls details tags")
        
        # Process each details tag
        for details_tag in details_tags:
            # Process this tag and any nested details tags
            self._process_details_tag(details_tag)
            
        # Return the modified HTML
        return str(soup)
    
    def _process_details_tag(self, details_tag):
        """Process a single details tag and its nested details tags recursively."""
        # First process any nested details tags
        nested_details = details_tag.find_all('details', recursive=False)
        for nested_tag in nested_details:
            self._process_details_tag(nested_tag)
        
        # Store content and results if needed
        content_value = details_tag.get('content', '')
        results_value = details_tag.get('results', '')
        
        # Remove the attributes if configured to do so
        if self.valves.remove_content and 'content' in details_tag.attrs:
            del details_tag['content']
        if self.valves.remove_results and 'results' in details_tag.attrs:
            del details_tag['results']
            
        # Add content and results as text if needed
        if not self.valves.remove_content and content_value:
            content_p = BeautifulSoup(f"<p>Content: {content_value}</p>", 'html.parser').p
            details_tag.append(content_p)
            
        if not self.valves.remove_results and results_value:
            results_p = BeautifulSoup(f"<p>Results: {results_value}</p>", 'html.parser').p
            details_tag.append(results_p)

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


