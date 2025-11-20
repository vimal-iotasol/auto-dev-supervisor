import os
import re
from typing import Optional, List
from openai import OpenAI
from auto_dev_supervisor.domain.model import Task, TaskTestResult
from auto_dev_supervisor.infra.opendevin import OpenDevinClient

class GenAIOpenDevinClient(OpenDevinClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4-turbo"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("[Warning] No OpenAI API Key found. GenAI client will fail if called.")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model = model

    def execute_task(self, task: Task, context: str) -> str:
        if not self.client:
            return "Error: No API Key provided for GenAI client."

        prompt = self._construct_prompt(task, context)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. You write production-ready code. When you write code, output it in markdown code blocks with the filename in the first line of the block or immediately preceding it, e.g. `filename.py`\n```python\ncode\n```. You must write the full content of the file."},
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content
            self._parse_and_write_files(content)
            return content
        except Exception as e:
            return f"Error calling LLM: {e}"

    def fix_issues(self, task: Task, errors: str) -> str:
        if not self.client:
            return "Error: No API Key provided for GenAI client."

        prompt = f"""
        The previous attempt to complete task '{task.title}' failed with the following errors:
        
        {errors}
        
        Please fix the code to resolve these errors. Output the full corrected file content.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are OpenDevin. Fix the bugs based on the error logs provided. Output full file contents."},
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content
            self._parse_and_write_files(content)
            return content
        except Exception as e:
            return f"Error calling LLM: {e}"

    def _construct_prompt(self, task: Task, context: str) -> str:
        return f"""
        Task: {task.title}
        Description: {task.description}
        
        Context:
        {context}
        
        Please implement the necessary code for this task.
        """

    def _parse_and_write_files(self, content: str):
        """
        Parses markdown code blocks and writes them to files.
        Regex looks for:
        (filename)
        ```lang
        code
        ```
        """
        # This is a simplified regex. In a real prod system, we'd need more robust parsing.
        # Pattern: Look for a filename (alphanumeric + . + ext) followed by a newline and a code block
        # Or code block with filename comment? 
        # Let's try to find patterns like: `path/to/file.py`\n```python...```
        
        # Regex to capture:
        # Group 1: Filename (optional, might be in text before)
        # Group 2: Code content
        
        # Strategy: Split by code blocks, look at preceding lines for filenames.
        
        code_blocks = re.split(r"```\w*\n", content)
        # The first chunk is text before first block.
        # Then we have: code + "```" + text + "```" ...
        
        # Actually, let's iterate over the matches.
        pattern = r"([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)\s*\n```\w*\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        for filename, code in matches:
            self._write_file(filename.strip(), code.strip())

    def _write_file(self, filename: str, content: str):
        try:
            # Ensure dir exists
            directory = os.path.dirname(filename)
            if directory:
                os.makedirs(directory, exist_ok=True)
            
            with open(filename, "w") as f:
                f.write(content)
            print(f"[GenAI] Wrote file: {filename}")
        except Exception as e:
            print(f"[GenAI] Failed to write {filename}: {e}")
