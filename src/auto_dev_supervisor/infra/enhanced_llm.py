import os
import time
import json
import hashlib
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from auto_dev_supervisor.domain.model import Task, TaskTestResult
from auto_dev_supervisor.infra.llm import GenAIOpenDevinClient
from auto_dev_supervisor.core.config import ConfigManager
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler, ErrorCategory, ErrorSeverity

class EnhancedGenAIOpenDevinClient(GenAIOpenDevinClient):
    """
    Enhanced LLM client with speed optimizations and iterative error resolution.
    Features:
    - Response caching to avoid redundant API calls
    - Streaming responses for faster perceived performance
    - Parallel processing for multiple tasks
    - Advanced error recovery with context learning
    - Request batching for better throughput
    """
    
    def __init__(self, provider: str = "openai", model: str = "gpt-4-turbo", 
                 config_manager: Optional[ConfigManager] = None, 
                 project_root: Optional[str] = None,
                 enable_cache: bool = True,
                 enable_streaming: bool = True,
                 max_parallel_requests: int = 3,
                 retry_delay: float = 1.0):
        super().__init__(provider, model, config_manager, project_root)
        self.enable_cache = enable_cache
        self.enable_streaming = enable_streaming
        self.max_parallel_requests = max_parallel_requests
        self.retry_delay = retry_delay
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".auto-dev", "cache")
        self.response_cache = {}
        self.error_context_history = []
        
        # Ensure cache directory exists
        if self.enable_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
            self._load_cache()
    
    def _get_cache_key(self, prompt: str, task_id: str) -> str:
        """Generate cache key from prompt and task ID"""
        content = f"{task_id}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _load_cache(self):
        """Load response cache from disk"""
        cache_file = os.path.join(self.cache_dir, f"{self.provider}_{self.model}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    self.response_cache = json.load(f)
            except Exception as e:
                print(f"[Cache] Failed to load cache: {e}")
                self.response_cache = {}
    
    def _save_cache(self):
        """Save response cache to disk"""
        if not self.enable_cache:
            return
            
        cache_file = os.path.join(self.cache_dir, f"{self.provider}_{self.model}.json")
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.response_cache, f)
        except Exception as e:
            print(f"[Cache] Failed to save cache: {e}")
    
    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response if available"""
        if not self.enable_cache:
            return None
        
        cached = self.response_cache.get(cache_key)
        if cached:
            print(f"[Cache] Cache hit for key: {cache_key[:8]}...")
            return cached
        return None
    
    def _cache_response(self, cache_key: str, response: str):
        """Cache response for future use"""
        if not self.enable_cache:
            return
        
        self.response_cache[cache_key] = response
        # Limit cache size to prevent memory issues
        if len(self.response_cache) > 1000:
            # Remove oldest entries
            keys_to_remove = list(self.response_cache.keys())[:500]
            for key in keys_to_remove:
                del self.response_cache[key]
    
    def execute_task(self, task: Task, context: str) -> str:
        """Enhanced task execution with caching and streaming"""
        print(f"[EnhancedGenAI] Starting task execution: {task.title} (ID: {task.id})")
        print(f"[EnhancedGenAI] Provider: {self.provider}, Model: {self.model}")
        print(f"[EnhancedGenAI] Service: {task.service_name}")
        print(f"[EnhancedGenAI] Streaming: {self.enable_streaming}, Cache: {self.enable_cache}")
        
        if not self.client and self.provider != "gemini":
            error_message = f"No API Key provided for {self.provider} client"
            print(f"[EnhancedGenAI] Error: {error_message}")
            return f"Error: {error_message}"
        
        prompt = self._construct_prompt(task, context)
        cache_key = self._get_cache_key(prompt, task.id)
        
        # Check cache first
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            print(f"[EnhancedGenAI] Using cached response")
            return cached_response
        
        # Execute with enhanced error handling and streaming
        try:
            content = self._execute_with_streaming(task, prompt, cache_key)
            
            # Apply self-review for quality improvement
            try:
                review_feedback = self._enhanced_self_review(content, task, context)
                if review_feedback and "```" in review_feedback:
                    print("[EnhancedGenAI] Applying enhanced self-review fixes")
                    content = review_feedback
            except Exception as e:
                print(f"[EnhancedGenAI] Self-review failed (non-critical): {e}")
            
            # Cache the final response
            self._cache_response(cache_key, content)
            self._save_cache()
            
            return content
            
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"provider": self.provider, "model": self.model, "task_id": task.id, 
                   "service_name": task.service_name, "phase": "execute_task"}
            )
            print(f"[EnhancedGenAI] Error calling LLM: {error.message}")
            
            # Try alternate providers with parallel processing
            return self._try_parallel_providers(task, context, error.message)
    
    def _execute_with_streaming(self, task: Task, prompt: str, cache_key: str) -> str:
        """Execute with streaming for faster perceived performance"""
        print(f"[EnhancedGenAI] Constructed prompt length: {len(prompt)} characters")
        
        if self.provider == "gemini":
            return self._execute_gemini_streaming(task, prompt)
        else:
            return self._execute_openai_streaming(task, prompt)
    
    def _execute_gemini_streaming(self, task: Task, prompt: str) -> str:
        """Execute with Gemini streaming"""
        if not self.client:
            raise Exception("Gemini client not initialized")
        
        print(f"[EnhancedGenAI] Calling Gemini API with streaming...")
        
        # Use streaming for Gemini
        response = self.client.generate_content(prompt, stream=self.enable_streaming)
        
        content = ""
        if self.enable_streaming:
            print("[EnhancedGenAI] Streaming response...")
            for chunk in response:
                if chunk.text:
                    content += chunk.text
                    # Update progress (for GUI feedback)
                    print(f"[Streaming] Received {len(content)} chars...\r", end="")
            print()  # New line after streaming
        else:
            content = response.text
        
        print(f"[EnhancedGenAI] Received response length: {len(content)} characters")
        self._parse_and_write_files(content)
        return content
    
    def _execute_openai_streaming(self, task: Task, prompt: str) -> str:
        """Execute with OpenAI-compatible streaming"""
        print(f"[EnhancedGenAI] Calling {self.provider} API with model {self.model}...")
        
        messages = [
            {"role": "system", "content": "You are OpenDevin, an autonomous AI software engineer. You write production-ready code. When you write code, output it in markdown code blocks. IMPORTANT: The first line of every code block MUST be a comment containing the filename, e.g. `## filename: src/main.py` or `# filename: Dockerfile`. You must write the full content of the file."},
            {"role": "user", "content": prompt}
        ]
        
        if self.enable_streaming:
            print("[EnhancedGenAI] Using streaming for faster response...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True
            )
            
            content = ""
            print("[EnhancedGenAI] Streaming response...")
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
                    # Update progress (for GUI feedback)
                    print(f"[Streaming] Received {len(content)} chars...\r", end="")
            print()  # New line after streaming
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            content = response.choices[0].message.content
        
        print(f"[EnhancedGenAI] Received response length: {len(content)} characters")
        self._parse_and_write_files(content)
        return content
    
    def _enhanced_self_review(self, content: str, task: Task, original_context: str) -> str:
        """Enhanced self-review with context awareness"""
        review_prompt = f"""
        You are reviewing code generated by OpenDevin for task: {task.title}
        
        Original context: {original_context}
        
        Generated code:
        {content}
        
        Please review this code for:
        1. Code quality and best practices
        2. Potential bugs or issues
        3. Performance optimizations
        4. Security vulnerabilities
        5. Completeness of implementation
        
        If you find issues, provide the corrected code. If no issues found, respond with "CODE_OK".
        If corrections are needed, output the full corrected code in markdown code blocks.
        """
        
        try:
            if self.provider == "gemini":
                response = self.client.generate_content(review_prompt)
                review_result = response.text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a code reviewer. Provide concise feedback and corrections."},
                        {"role": "user", "content": review_prompt}
                    ]
                )
                review_result = response.choices[0].message.content
            
            if "CODE_OK" in review_result:
                return content
            elif "```" in review_result:
                return review_result
            else:
                return content
                
        except Exception as e:
            print(f"[EnhancedGenAI] Self-review failed: {e}")
            return content
    
    def _try_parallel_providers(self, task: Task, context: str, original_error: str) -> str:
        """Try multiple providers in parallel for faster fallback"""
        print(f"[EnhancedGenAI] Attempting parallel provider fallback...")
        
        # Define fallback providers
        fallback_providers = [
            ("openai", "gpt-3.5-turbo"),
            ("ollama", "llama3.1"),
            ("gemini", "gemini-1.5-flash")
        ]
        
        # Filter out current provider and unavailable ones
        available_providers = []
        for provider, model in fallback_providers:
            if provider != self.provider:  # Don't retry same provider
                key = self.config_manager.get_api_key(provider)
                if key or provider == "ollama":  # Ollama doesn't need API key
                    available_providers.append((provider, model))
        
        if not available_providers:
            return f"Error calling LLM: {original_error} (No fallback providers available)"
        
        print(f"[EnhancedGenAI] Trying {len(available_providers)} fallback providers in parallel...")
        
        with ThreadPoolExecutor(max_workers=min(len(available_providers), self.max_parallel_requests)) as executor:
            futures = {}
            for provider, model in available_providers:
                future = executor.submit(self._try_single_provider, provider, model, task, context)
                futures[future] = (provider, model)
            
            # Return first successful result
            for future in as_completed(futures, timeout=30):
                try:
                    result = future.result()
                    if result and not result.startswith("Error"):
                        provider, model = futures[future]
                        print(f"[EnhancedGenAI] Fallback provider {provider}/{model} succeeded")
                        return result
                except Exception as e:
                    provider, model = futures[future]
                    print(f"[EnhancedGenAI] Fallback provider {provider}/{model} failed: {e}")
        
        return f"Error calling LLM: {original_error} (All fallback providers failed)"
    
    def _try_single_provider(self, provider: str, model: str, task: Task, context: str) -> str:
        """Try a single provider for fallback"""
        try:
            # Create temporary client for this provider
            temp_client = GenAIOpenDevinClient(provider, model, self.config_manager)
            return temp_client.execute_task(task, context)
        except Exception as e:
            return f"Error: {e}"
    
    def fix_issues(self, task: Task, errors: str) -> str:
        """Enhanced issue fixing with iterative improvement"""
        print(f"[EnhancedGenAI] Fixing issues for task: {task.title}")
        print(f"[EnhancedGenAI] Errors: {errors[:100]}...")
        
        # Store error context for learning
        self.error_context_history.append({
            "task_id": task.id,
            "task_title": task.title,
            "service_name": task.service_name,
            "errors": errors,
            "timestamp": time.time()
        })
        
        # Keep only recent error history (last 50)
        if len(self.error_context_history) > 50:
            self.error_context_history = self.error_context_history[-50:]
        
        # Find similar past errors for context
        similar_errors = self._find_similar_errors(errors, task.service_name)
        
        enhanced_prompt = f"""
        The previous attempt to complete task '{task.title}' failed with the following errors:
        
        {errors}
        
        {similar_errors}
        
        Please fix the code to resolve these errors. Consider:
        1. The specific error messages and their root causes
        2. Best practices for the service type: {task.service_name}
        3. Similar fixes that worked in the past (if any)
        4. Output the full corrected file content
        
        Output the corrected code in markdown code blocks with filename comments.
        """
        
        try:
            if self.provider == "gemini":
                if not self.client:
                    raise Exception("Gemini client not initialized")
                response = self.client.generate_content(enhanced_prompt)
                content = response.text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are OpenDevin. Fix the bugs based on the error logs provided. Output full file contents. IMPORTANT: The first line of every code block MUST be a comment containing the filename, e.g. `## filename: src/main.py`."},
                        {"role": "user", "content": enhanced_prompt}
                    ]
                )
                content = response.choices[0].message.content
            
            self._parse_and_write_files(content)
            return content
            
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"provider": self.provider, "task_id": task.id, "service_name": task.service_name, "phase": "fix_issues"}
            )
            return f"Error fixing issues: {error.message}"
    
    def _find_similar_errors(self, current_error: str, service_name: str) -> str:
        """Find similar past errors for context"""
        if not self.error_context_history:
            return ""
        
        # Simple similarity check based on error message content
        similar_contexts = []
        for error_ctx in self.error_context_history:
            if (error_ctx["service_name"] == service_name and 
                error_ctx["task_id"] != "current" and
                len(set(current_error.lower().split()) & set(error_ctx["errors"].lower().split())) > 3):
                similar_contexts.append(error_ctx)
        
        if similar_contexts:
            recent = similar_contexts[-1]  # Get most recent similar error
            return f"""
        Similar past error context:
        - Task: {recent['task_title']}
        - Service: {recent['service_name']}
        - Previous errors: {recent['errors'][:200]}...
        - This might help identify patterns in the errors.
        """
        
        return ""
