import os
from typing import Optional, List
from openai import OpenAI
# import google.generativeai as genai # Moved to lazy import due to protobuf issues on some python versions
from auto_dev_supervisor.domain.model import Task, TaskTestResult
from auto_dev_supervisor.infra.opendevin import OpenDevinClient
from auto_dev_supervisor.core.config import ConfigManager

class GenAIOpenDevinClient(OpenDevinClient):
    def __init__(self, provider: str = "openai", model: str = "gpt-4-turbo", config_manager: Optional[ConfigManager] = None):
        self.provider = provider
        self.model = model
        self.config_manager = config_manager or ConfigManager()
        
        self.api_key = self.config_manager.get_api_key(provider)
        
        # For Ollama, we don't strictly need an API key, but we can use a dummy one if missing
        if provider == "ollama" and not self.api_key:
            self.api_key = "ollama"

        if not self.api_key:
            print(f"[Warning] No API Key found for {provider}. GenAI client will fail if called.")
            
        self.client = None
        if self.api_key:
            if provider == "openai":
                self.client = OpenAI(api_key=self.api_key)
            elif provider == "ollama":
                # Ollama local API usually runs on port 11434
                self.client = OpenAI(
                    base_url="http://localhost:11434/v1",
                    api_key="ollama" # required but ignored
                )
            elif provider == "grok":
                # xAI Grok API
                self.client = OpenAI(
                    base_url="https://api.x.ai/v1",
                    api_key=self.api_key
                )
            elif provider == "grok":
                # xAI Grok API
                self.client = OpenAI(
                    base_url="https://api.x.ai/v1",
                    api_key=self.api_key
                )
            elif provider == "gemini":
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key)
                    self.client = genai.GenerativeModel(model_name=model if model != "gpt-4-turbo" else "gemini-pro")
                except ImportError as e:
                    print(f"[Error] Failed to import google.generativeai: {e}")
                    self.client = None
                except Exception as e:
                    print(f"[Error] Failed to initialize Gemini client: {e}")
                    self.client = None

    def execute_task(self, task: Task, context: str) -> str:
        if not self.client and self.provider != "gemini": # Gemini client is the model object
             return f"Error: No API Key provided for {self.provider} client."
        
        if self.provider == "gemini" and not self.client:
             return "Error: Gemini client failed to initialize (likely due to missing dependencies or Python version incompatibility)."

        prompt = self._construct_prompt(task, context)
        
        try:
            content = ""
            if self.provider == "gemini":
                response = self.client.generate_content(prompt)
                content = response.text
            else:
                # OpenAI compatible (OpenAI, Ollama, Grok)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. You write production-ready code. When you write code, output it in markdown code blocks. IMPORTANT: The first line of every code block MUST be a comment containing the filename, e.g. `## filename: src/main.py` or `# filename: Dockerfile`. You must write the full content of the file."},
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content
                
            self._parse_and_write_files(content)
            return content
        except Exception as e:
            return f"Error calling LLM: {e}"

    def fix_issues(self, task: Task, errors: str) -> str:
        if not self.client and self.provider != "gemini":
            return f"Error: No API Key provided for {self.provider} client."

        prompt = f"""
        The previous attempt to complete task '{task.title}' failed with the following errors:
        
        {errors}
        
        Please fix the code to resolve these errors. Output the full corrected file content.
        """
        
        try:
            content = ""
            if self.provider == "gemini":
                 if not self.client:
                     return "Error: Gemini client not initialized."
                 # Gemini doesn't have system prompts in the same way in generate_content, 
                 # so we prepend instructions
                 full_prompt = "You are OpenDevin. Fix the bugs based on the error logs provided. Output full file contents.\n" + prompt
                 response = self.client.generate_content(full_prompt)
                 content = response.text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are OpenDevin. Fix the bugs based on the error logs provided. Output full file contents. IMPORTANT: The first line of every code block MUST be a comment containing the filename, e.g. `## filename: src/main.py`."},
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content
                
            self._parse_and_write_files(content)
            return content
        except Exception as e:
            return f"Error calling LLM: {e}"

    def _construct_prompt(self, task: Task, context: str) -> str:
        base_prompt = f"""
        Task: {task.title}
        Description: {task.description}
        Service: {task.service_name}
        
        Context:
        {context}
        """

        if "Scaffold" in task.title:
            base_prompt += f"""
            IMPORTANT: You must generate a Dockerfile named `Dockerfile.{task.service_name}`.
            The Dockerfile should be appropriate for the service type and description.
            Also generate a basic `requirements.txt` or `pyproject.toml` if needed.
            
            REMEMBER: Start each code block with `## filename: <filename>`
            """
            
        base_prompt += "\nPlease implement the necessary code for this task."
        return base_prompt

    def _parse_and_write_files(self, content: str):
        """
        Parses markdown code blocks and writes them to files.
        """
        import logging
        logging.debug(f"LLM Response Content:\n{content}")
        
        # Regex to find code blocks: ```lang ... ```
        # We capture the language (group 1) and the code (group 2)
        block_pattern = r"```(\w*)\n(.*?)```"
        
        # We will iterate through matches and look at the text preceding the match
        last_end = 0
        for match in re.finditer(block_pattern, content, re.DOTALL):
            start, end = match.span()
            code = match.group(2)
            
            filename = None
            
            # Strategy 1: Check first line of code for "filename: <name>" pattern
            lines = code.strip().split('\n')
            if lines:
                first_line = lines[0].strip()
                # Regex for comment with filename
                # Supports #, //, --, or just text
                # Looks for "filename: <name>"
                name_match = re.search(r"filename:\s*([a-zA-Z0-9_./-]+)", first_line, re.IGNORECASE)
                if name_match:
                    filename = name_match.group(1)
                    # Remove the comment line from the code to keep it clean (optional, but good for Dockerfiles)
                    # code = "\n".join(lines[1:]) 
            
            # Strategy 2: Look at the text before this block (Fallback)
            if not filename:
                preceding_text = content[last_end:start]
                lines = preceding_text.strip().split('\n')
                if lines:
                    last_line = lines[-1].strip()
                    file_match = re.search(r"([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+|Dockerfile(?:\.[a-zA-Z0-9_-]+)?)", last_line)
                    if file_match:
                        filename = file_match.group(1)
            
            if filename:
                self._write_file(filename.strip(), code.strip())
            else:
                logging.warning("Could not determine filename for code block. Preceding text: " + preceding_text[-50:])
            
            last_end = end

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
