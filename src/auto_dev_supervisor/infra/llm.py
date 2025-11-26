import os
from typing import Optional, List
from openai import OpenAI
# import google.generativeai as genai # Moved to lazy import due to protobuf issues on some python versions
from auto_dev_supervisor.domain.model import Task, TaskTestResult
from auto_dev_supervisor.infra.opendevin import OpenDevinClient
from auto_dev_supervisor.core.config import ConfigManager
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler, ErrorCategory, ErrorSeverity

class GenAIOpenDevinClient(OpenDevinClient):
    def __init__(self, provider: str = "openai", model: str = "gpt-4-turbo", config_manager: Optional[ConfigManager] = None, project_root: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.config_manager = config_manager or ConfigManager()
        self.project_root = os.path.abspath(project_root) if project_root else os.getcwd()
        self.error_handler = EnhancedErrorHandler()
        
        self.api_key = self.config_manager.get_api_key(provider)
        
        # For Ollama, we don't strictly need an API key, but we can use a dummy one if missing
        if provider == "ollama" and not self.api_key:
            self.api_key = "ollama"

        if not self.api_key:
            error = self.error_handler.handle_error(
                Exception(f"No API key configured for {provider}"),
                {"provider": provider, "phase": "llm_init"}
            )
            print(f"[Warning] {error.message}. GenAI client will fail if called.")
            
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
                try:
                    import urllib.request, json
                    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
                        data = resp.read().decode("utf-8")
                        tags = json.loads(data)
                        names = []
                        if isinstance(tags, dict) and "models" in tags:
                            for m in tags["models"]:
                                n = m.get("name") or m.get("tag") or ""
                                if n:
                                    names.append(n)
                        elif isinstance(tags, list):
                            for m in tags:
                                n = m.get("name") or m.get("tag") or ""
                                if n:
                                    names.append(n)
                        if self.model is None or self.model.strip() == "":
                            if "llama2" in names:
                                self.model = "llama2"
                            elif names:
                                self.model = names[0]
                        elif self.model not in names and f"{self.model}:latest" in names:
                            self.model = f"{self.model}:latest"
                except Exception:
                    pass
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
                    # Use gemini-1.5-flash as default if model is gpt-4-turbo (default from init) or gemini-pro (deprecated)
                    target_model = model
                    if model in ["gpt-4-turbo", "gemini-pro"]:
                        target_model = "gemini-1.5-flash"
                    
                    self.client = genai.GenerativeModel(model_name=target_model)
                    print(f"[GenAI] Successfully initialized Gemini client with model: {target_model}")
                except ImportError as e:
                    print(f"[Error] Failed to import google.generativeai: {e}")
                    print("[Error] Please install: pip install google-generativeai")
                    self.client = None
                except Exception as e:
                    print(f"[Error] Failed to initialize Gemini client: {e}")
                    self.client = None

    def execute_task(self, task: Task, context: str) -> str:
        print(f"[GenAI] Starting task execution: {task.title} (ID: {task.id})")
        print(f"[GenAI] Provider: {self.provider}, Model: {self.model}")
        print(f"[GenAI] Service: {task.service_name}")
        
        if not self.client and self.provider != "gemini": # Gemini client is the model object
            error = self.error_handler.handle_error(
                Exception(f"No API Key provided for {self.provider} client"),
                {"provider": self.provider, "task_id": task.id, "service_name": task.service_name, "phase": "execute_task"}
            )
            return f"Error: {error.message}"
        
        if self.provider == "gemini" and not self.client:
            error = self.error_handler.handle_error(
                Exception("Gemini client failed to initialize"),
                {"provider": self.provider, "task_id": task.id, "service_name": task.service_name, "phase": "execute_task"}
            )
            return f"Error: {error.message}"

        prompt = self._construct_prompt(task, context)
        print(f"[GenAI] Constructed prompt length: {len(prompt)} characters")
        
        try:
            content = ""
            if self.provider == "gemini":
                print(f"[GenAI] Calling Gemini API...")
                response = self.client.generate_content(prompt)
                content = response.text
            else:
                # OpenAI compatible (OpenAI, Ollama, Grok)
                print(f"[GenAI] Calling {self.provider} API with model {self.model}...")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. You write production-ready code. When you write code, output it in markdown code blocks. IMPORTANT: The first line of every code block MUST be a comment containing the filename, e.g. `## filename: src/main.py` or `# filename: Dockerfile`. You must write the full content of the file."},
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content
                
            print(f"[GenAI] Received response length: {len(content)} characters")
            self._parse_and_write_files(content)
            # Optional self-review pass
            try:
                review_feedback = self._self_review(content, task)
                if review_feedback and "```" in review_feedback:
                    print("[GenAI] Applying self-review fixes")
                    self._parse_and_write_files(review_feedback)
            except Exception:
                pass
            return content
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"provider": self.provider, "model": self.model, "task_id": task.id, "service_name": task.service_name, "phase": "execute_task"}
            )
            print(f"[GenAI] Error calling LLM: {error.message}")
            # Try alternate providers for consensus/fallback
            alt_content = self._try_alternate_providers(self._construct_prompt(task, context))
            if alt_content:
                print("[GenAI] Fallback provider succeeded; applying content")
                self._parse_and_write_files(alt_content)
                return alt_content
            return f"Error calling LLM: {error.message}"

    def fix_issues(self, task: Task, errors: str) -> str:
        if not self.client and self.provider != "gemini":
            error = self.error_handler.handle_error(
                Exception(f"No API Key provided for {self.provider} client"),
                {"provider": self.provider, "task_id": task.id, "service_name": task.service_name, "phase": "fix_issues"}
            )
            return f"Error: {error.message}"

        prompt = f"""
        The previous attempt to complete task '{task.title}' failed with the following errors:
        
        {errors}
        
        Please fix the code to resolve these errors. Output the full corrected file content.
        """
        
        try:
            content = ""
            if self.provider == "gemini":
                 if not self.client:
                     error = self.error_handler.handle_error(
                         Exception("Gemini client not initialized"),
                         {"provider": self.provider, "task_id": task.id, "service_name": task.service_name, "phase": "fix_issues"}
                     )
                     return f"Error: {error.message}"
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
            error = self.error_handler.handle_error(
                e, {"provider": self.provider, "model": self.model, "task_id": task.id, "service_name": task.service_name, "phase": "fix_issues"}
            )
            return f"Error calling LLM: {error.message}"

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
            CRITICAL REQUIREMENTS:
            1. You MUST generate a Dockerfile named `Dockerfile.{task.service_name}` - this is essential for building the service
            2. The Dockerfile should be appropriate for the service type ({task.service_name})
            3. Also generate a basic `requirements.txt` or `pyproject.toml` if needed
            4. Generate the main application file for the service
            5. Include any necessary configuration files
            
            REMEMBER: Start each code block with `## filename: <filename>`
            
            EXAMPLE DOCKERFILE FOR PYTHON SERVICE:
            ```dockerfile
            ## filename: Dockerfile.{task.service_name}
            FROM python:3.11-slim
            WORKDIR /app
            COPY requirements.txt .
            RUN pip install -r requirements.txt
            COPY . .
            CMD ["python", "main.py"]
            ```
            
            FAILURE TO GENERATE THE DOCKERFILE WILL CAUSE BUILD FAILURES!
            """
            
        base_prompt += "\nPlease implement the necessary code for this task."
        return base_prompt

    def _self_review(self, content: str, task: Task) -> Optional[str]:
        """Ask the model to self-review generated code and propose corrections."""
        try:
            review_prompt = (
                "You are OpenDevin. Review the generated code for the task '"
                + task.title +
                "'. Identify issues that would cause build/test failures (especially missing Dockerfiles or incorrect dependencies). "
                "Provide corrected files in full, using markdown code blocks with filenames."
            )
            if self.provider == "gemini":
                response = self.client.generate_content(review_prompt)
                return getattr(response, "text", "")
            else:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are OpenDevin performing a self-review."},
                        {"role": "user", "content": review_prompt}
                    ]
                )
                return resp.choices[0].message.content
        except Exception:
            return None

    def _try_alternate_providers(self, prompt: str) -> Optional[str]:
        """Attempt to use alternate providers to get a valid response."""
        try:
            alternates = [p for p in ["openai", "ollama", "grok"] if p != self.provider]
            for prov in alternates:
                api_key = self.config_manager.get_api_key(prov)
                client = None
                model = {
                    "openai": "gpt-4-turbo",
                    "ollama": "llama3.1",
                    "grok": "grok-beta"
                }.get(prov, "gpt-4-turbo")
                try:
                    if prov == "openai" and api_key:
                        client = OpenAI(api_key=api_key)
                        resp = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. Output full files in code blocks with filenames."},
                                {"role": "user", "content": prompt}
                            ]
                        )
                        return resp.choices[0].message.content
                    elif prov == "ollama":
                        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
                        resp = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. Output full files in code blocks with filenames."},
                                {"role": "user", "content": prompt}
                            ]
                        )
                        return resp.choices[0].message.content
                    elif prov == "grok" and api_key:
                        client = OpenAI(base_url="https://api.x.ai/v1", api_key=api_key)
                        resp = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. Output full files in code blocks with filenames."},
                                {"role": "user", "content": prompt}
                            ]
                        )
                        return resp.choices[0].message.content
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def _parse_and_write_files(self, content: str):
        """
        Parses markdown code blocks and writes them to files.
        """
        import re
        print(f"[GenAI] Parsing content for code blocks...")
        print(f"[GenAI] Content preview: {content[:200]}...")
        
        # Regex to find code blocks: ```lang ... ```
        # We capture the language (group 1) and the code (group 2)
        block_pattern = r"```(\w*)\n(.*?)```"
        
        # We will iterate through matches and look at the text preceding the match
        last_end = 0
        blocks_found = 0
        files_written = 0
        
        for match in re.finditer(block_pattern, content, re.DOTALL):
            start, end = match.span()
            code = match.group(2)
            blocks_found += 1
            
            filename = None
            
            # Strategy 1: Check first line of code for "filename: <name>" pattern
            lines = code.strip().split('\n')
            if lines:
                first_line = lines[0].strip()
                print(f"[GenAI] First line of code block {blocks_found}: {first_line}")
                # Regex for comment with filename
                # Supports #, //, --, or just text
                # Looks for "filename: <name>"
                name_match = re.search(r"filename:\s*([a-zA-Z0-9_./-]+)", first_line, re.IGNORECASE)
                if name_match:
                    filename = name_match.group(1)
                    print(f"[GenAI] Found filename in first line: {filename}")
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
                        print(f"[GenAI] Found filename in preceding text: {filename}")
            
            if filename:
                self._write_file(filename.strip(), code.strip())
                files_written += 1
            else:
                print(f"[GenAI] Warning: Could not determine filename for code block {blocks_found}")
                
            last_end = end
        
        print(f"[GenAI] Found {blocks_found} code blocks, wrote {files_written} files")

    def _write_file(self, filename: str, content: str):
        try:
            # Ensure dir exists
            target_path = filename
            if not os.path.isabs(target_path):
                target_path = os.path.join(self.project_root, target_path)
            directory = os.path.dirname(target_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
                print(f"[GenAI] Created directory: {directory}")
            
            with open(target_path, "w", encoding='utf-8') as f:
                f.write(content)
            print(f"[GenAI] Successfully wrote file: {target_path} ({len(content)} characters)")
        except Exception as e:
            print(f"[GenAI] Failed to write {filename}: {e}")
            import traceback
            traceback.print_exc()
