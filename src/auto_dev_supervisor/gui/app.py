import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import sys
import io
import time
import json
import urllib.request
from typing import Optional
from datetime import datetime

from auto_dev_supervisor.core.config import ConfigManager
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.core.supervisor import Supervisor
from auto_dev_supervisor.infra.opendevin import MockOpenDevinClient
from auto_dev_supervisor.infra.llm import GenAIOpenDevinClient
from auto_dev_supervisor.infra.enhanced_llm import EnhancedGenAIOpenDevinClient
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.qa import QAManager

class RedirectText(io.StringIO):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        # Force update to show logs in real-time
        self.text_widget.update_idletasks()

    def flush(self):
        pass

class AutoDevApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto-Dev Supervisor - AI Development Automation")
        self.geometry("1000x700")
        self.minsize(800, 600)
        
        # Configure modern theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure colors
        self.configure(bg='#f0f0f0')
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0', font=('Segoe UI', 10))
        self.style.configure('TButton', font=('Segoe UI', 10, 'bold'))
        self.style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'))
        
        self.config_manager = ConfigManager()
        self.current_task = None
        self.is_running = False
        
        self._create_widgets()
        self._load_config()
        self._center_window()

    def _center_window(self):
        """Center the window on screen"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _create_widgets(self):
        # Create header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        title_label = ttk.Label(header_frame, text="🤖 Auto-Dev Supervisor", 
                               style='Header.TLabel', font=('Segoe UI', 16, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        subtitle_label = ttk.Label(header_frame, text="AI-Powered Development Automation", 
                                  font=('Segoe UI', 10))
        subtitle_label.pack(side=tk.LEFT, padx=20)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Main content
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Run (scrollable)
        self.run_container = ttk.Frame(self.notebook)
        self.notebook.add(self.run_container, text="🚀 Run")
        self.run_frame = self._create_scrollable_area(self.run_container)
        self._create_run_tab()
        
        # Tab 2: Configuration (scrollable)
        self.config_container = ttk.Frame(self.notebook)
        self.notebook.add(self.config_container, text="⚙️ Configuration")
        self.config_frame = self._create_scrollable_area(self.config_container)
        self._create_config_tab()
        
        # Tab 3: Help (already includes its own scrolling for text)
        self.help_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.help_frame, text="❓ Help")
        self._create_help_tab()

    def _create_scrollable_area(self, parent):
        """Create a vertically scrollable area inside a tab"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        vscroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())

        inner.bind("<Configure>", _on_configure)

        # Mousewheel support
        def _on_mousewheel(event):
            delta = -1 * (event.delta // 120) if event.delta else 0
            canvas.yview_scroll(delta, "units")

        inner.bind_all("<MouseWheel>", _on_mousewheel)

        return inner

    def _create_config_tab(self):
        # API Keys Section
        api_frame = ttk.LabelFrame(self.config_frame, text="🔑 API Keys", padding=15)
        api_frame.pack(fill=tk.X, padx=20, pady=15)
        
        # Provider information
        info_label = ttk.Label(api_frame, text="Configure your LLM provider API keys. Keys are stored securely and masked.", 
                              font=('Segoe UI', 9, 'italic'))
        info_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        # OpenAI
        ttk.Label(api_frame, text="OpenAI API Key:").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.openai_key_var = tk.StringVar()
        openai_entry = ttk.Entry(api_frame, textvariable=self.openai_key_var, width=60, show="*")
        openai_entry.grid(row=1, column=1, padx=10, sticky=tk.EW)
        
        # Anthropic
        ttk.Label(api_frame, text="Anthropic API Key:").grid(row=2, column=0, sticky=tk.W, pady=8)
        self.anthropic_key_var = tk.StringVar()
        anthropic_entry = ttk.Entry(api_frame, textvariable=self.anthropic_key_var, width=60, show="*")
        anthropic_entry.grid(row=2, column=1, padx=10, sticky=tk.EW)

        # Gemini
        ttk.Label(api_frame, text="Gemini API Key:").grid(row=3, column=0, sticky=tk.W, pady=8)
        self.gemini_key_var = tk.StringVar()
        gemini_entry = ttk.Entry(api_frame, textvariable=self.gemini_key_var, width=60, show="*")
        gemini_entry.grid(row=3, column=1, padx=10, sticky=tk.EW)

        # Grok
        ttk.Label(api_frame, text="Grok API Key:").grid(row=4, column=0, sticky=tk.W, pady=8)
        self.grok_key_var = tk.StringVar()
        grok_entry = ttk.Entry(api_frame, textvariable=self.grok_key_var, width=60, show="*")
        grok_entry.grid(row=4, column=1, padx=10, sticky=tk.EW)
        
        # Configure grid weights for proper resizing
        api_frame.columnconfigure(1, weight=1)
        
        # Button frame
        button_frame = ttk.Frame(api_frame)
        button_frame.grid(row=5, column=1, sticky=tk.E, pady=(15, 0))
        
        # Save Button
        save_btn = ttk.Button(button_frame, text="💾 Save Keys", command=self._save_keys, style='Accent.TButton')
        save_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Test Button
        test_btn = ttk.Button(button_frame, text="🧪 Test Connection", command=self._test_connection)
        test_btn.pack(side=tk.RIGHT)

    def _create_run_tab(self):
        # Project Configuration Section
        config_frame = ttk.LabelFrame(self.run_frame, text="📋 Project Configuration", padding=15)
        config_frame.pack(fill=tk.X, padx=20, pady=15)
        
        # Spec Selection
        ttk.Label(config_frame, text="Project Spec (YAML):").grid(row=0, column=0, sticky=tk.W, pady=8)
        self.spec_path_var = tk.StringVar()
        spec_entry = ttk.Entry(config_frame, textvariable=self.spec_path_var, width=60)
        spec_entry.grid(row=0, column=1, padx=10, sticky=tk.EW)
        ttk.Button(config_frame, text="📁 Browse", command=self._browse_spec).grid(row=0, column=2, padx=5)
        
        # Output Directory Selection
        ttk.Label(config_frame, text="Output Directory:").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.output_dir_var = tk.StringVar(value=os.getcwd())
        output_entry = ttk.Entry(config_frame, textvariable=self.output_dir_var, width=60)
        output_entry.grid(row=1, column=1, padx=10, sticky=tk.EW)
        ttk.Button(config_frame, text="📁 Browse", command=self._browse_output_dir).grid(row=1, column=2, padx=5)
        
        # Options Section
        options_frame = ttk.LabelFrame(self.run_frame, text="⚙️ Options", padding=15)
        options_frame.pack(fill=tk.X, padx=20, pady=15)
        
        # Provider Selection
        ttk.Label(options_frame, text="LLM Provider:").grid(row=0, column=0, sticky=tk.W, pady=8)
        self.provider_var = tk.StringVar(value="mock")
        provider_combo = ttk.Combobox(options_frame, textvariable=self.provider_var, 
                                    values=["mock", "openai", "ollama", "gemini", "grok"], 
                                    state="readonly", width=15)
        provider_combo.grid(row=0, column=1, padx=10, sticky=tk.W)
        provider_combo.bind('<<ComboboxSelected>>', self._on_provider_change)
        
        # Model Selection (for Ollama and other providers)
        ttk.Label(options_frame, text="Model:").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.model_var = tk.StringVar(value="llama3.1")
        self.model_combo = ttk.Combobox(options_frame, textvariable=self.model_var, 
                                      values=["llama3.1", "llama3.2", "mistral", "mixtral", "codellama", "phi3"], 
                                      state="readonly", width=28)
        self.model_combo.grid(row=1, column=1, padx=10, sticky=tk.W)

        # Refresh models for Ollama
        self.refresh_models_btn = ttk.Button(options_frame, text="🔄 Refresh Models", command=self._refresh_ollama_models)
        self.refresh_models_btn.grid(row=1, column=2, padx=5, sticky=tk.W)
        
        # Git Options
        self.skip_git_var = tk.BooleanVar(value=False)
        git_check = ttk.Checkbutton(options_frame, text="Skip Git Operations (for local testing)", 
                                   variable=self.skip_git_var)
        git_check.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=8)
        
        # Speed Optimization Options
        ttk.Label(options_frame, text="Speed Optimizations:").grid(row=3, column=0, sticky=tk.W, pady=8)
        self.enable_cache_var = tk.BooleanVar(value=True)
        cache_check = ttk.Checkbutton(options_frame, text="Enable Response Caching", 
                                     variable=self.enable_cache_var)
        cache_check.grid(row=3, column=1, sticky=tk.W, padx=10)
        
        self.enable_streaming_var = tk.BooleanVar(value=True)
        streaming_check = ttk.Checkbutton(options_frame, text="Enable Streaming Responses", 
                                       variable=self.enable_streaming_var)
        streaming_check.grid(row=4, column=1, sticky=tk.W, padx=10)
        
        # Enhanced Supervisor Options
        ttk.Label(options_frame, text="Enhanced Features:").grid(row=5, column=0, sticky=tk.W, pady=8)
        self.use_enhanced_supervisor_var = tk.BooleanVar(value=True)
        enhanced_check = ttk.Checkbutton(options_frame, text="Use Enhanced Supervisor", 
                                       variable=self.use_enhanced_supervisor_var)
        enhanced_check.grid(row=5, column=1, sticky=tk.W, padx=10)
        
        self.enable_advanced_recovery_var = tk.BooleanVar(value=True)
        recovery_check = ttk.Checkbutton(options_frame, text="Enable Advanced Recovery", 
                                        variable=self.enable_advanced_recovery_var)
        recovery_check.grid(row=6, column=1, sticky=tk.W, padx=10)
        
        # Provider descriptions
        provider_desc = ttk.Label(options_frame, text="💡 Mock: Free testing | OpenAI/Gemini/Grok: Paid AI models | Ollama: Local models", 
                                   font=('Segoe UI', 9, 'italic'))
        provider_desc.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
        
        # Configure grid weights
        config_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(1, weight=1)

        # Docker Status and Skip
        docker_frame = ttk.LabelFrame(self.run_frame, text="🐳 Docker", padding=12)
        docker_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(docker_frame, text="Status:").grid(row=0, column=0, sticky=tk.W)
        self.docker_status_var = tk.StringVar(value="Unknown")
        ttk.Label(docker_frame, textvariable=self.docker_status_var).grid(row=0, column=1, sticky=tk.W)
        ttk.Button(docker_frame, text="Check Docker", command=self._check_docker_status).grid(row=0, column=2, padx=10)
        self.skip_docker_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(docker_frame, text="Run without Docker", variable=self.skip_docker_var).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=8)
        docker_frame.columnconfigure(1, weight=1)
        
        # Action Section
        action_frame = ttk.Frame(self.run_frame)
        action_frame.pack(fill=tk.X, padx=20, pady=20)
        
        # Run Button
        self.run_btn = ttk.Button(action_frame, text="🚀 Run Supervisor", command=self._start_run, 
                                 style='Accent.TButton', width=20)
        self.run_btn.pack(pady=10)
        
        # Progress Section
        progress_frame = ttk.LabelFrame(self.run_frame, text="📊 Progress", padding=15)
        progress_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Logs
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=12, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Health Panel
        health_frame = ttk.LabelFrame(self.run_frame, text="🩺 System Health", padding=15)
        health_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(health_frame, text="Health Score:").grid(row=0, column=0, sticky=tk.W)
        self.health_score_var = tk.StringVar(value="N/A")
        ttk.Label(health_frame, textvariable=self.health_score_var).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(health_frame, text="Latest Errors:").grid(row=1, column=0, sticky=tk.W, pady=(10,0))
        self.error_listbox = tk.Listbox(health_frame, height=5)
        self.error_listbox.grid(row=1, column=1, sticky=tk.EW, pady=(10,0))
        health_frame.columnconfigure(1, weight=1)

    def _create_help_tab(self):
        help_text = tk.Text(self.help_frame, wrap=tk.WORD, padx=20, pady=20, 
                           font=('Segoe UI', 10), bg='#f8f9fa')
        help_text.pack(fill=tk.BOTH, expand=True)
        
        help_content = """
🤖 Auto-Dev Supervisor Help

📋 Getting Started:
1. Configure your API keys in the Configuration tab
2. Select a project specification YAML file
3. Choose your output directory for generated files
4. Choose your LLM provider (Mock for testing)
5. Configure speed optimizations and enhanced features
6. Click "Run Supervisor" to start automation

🔧 Configuration:
• Mock Provider: Free testing mode, no API calls
• OpenAI/Gemini/Grok: Real AI models, requires API keys
• Ollama: Local AI models (llama3.1, mistral, etc.)
• Model Selection: Choose specific model for each provider
• Skip Git: Test without committing to git
• Output Directory: Select where generated files will be created

⚡ Speed Optimizations:
• Response Caching: Cache LLM responses to avoid redundant API calls
• Streaming Responses: Get faster perceived performance with streaming

🔄 Enhanced Features:
• Enhanced Supervisor: Advanced error resolution with multiple recovery strategies
• Advanced Recovery: Context enhancement, alternative approaches, simplification
• Iterative Error Resolution: Automatically resolves errors until application is built and running
• Parallel Fallback: Try multiple providers simultaneously on failure
• Error Context Learning: Learn from past errors to fix issues faster

📊 Understanding the Process:
The supervisor follows an iterative development cycle:
PLAN → IMPLEMENT → BUILD → TEST → QA → FIX → COMMIT → PUSH

🛠️ Troubleshooting:
• Check logs for detailed error messages
• Ensure Docker is running for containerized builds
• Verify API keys are valid for chosen provider
• Use Mock mode to test supervisor logic
• Enable streaming for faster response times
• Use response caching to avoid redundant API calls

📁 Project Spec Format:
Your YAML file should define:
- Project name and version
- Repository URL and branch
- Services with types (backend/frontend/audio/ml)
- Dependencies between services
- Quality metrics for ML/Audio services

🔗 More Information:
• User Guide: docs/USER_GUIDE.md
• Architecture: docs/ARCHITECTURE.md
• Examples: examples/ directory
        """
        
        help_text.insert(1.0, help_content)
        help_text.config(state=tk.DISABLED)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.help_frame, orient=tk.VERTICAL, command=help_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        help_text.config(yscrollcommand=scrollbar.set)

    def _on_provider_change(self, event=None):
        """Update model selection based on provider"""
        provider = self.provider_var.get()
        
        # Update model options based on provider
        if provider == "ollama":
            self._refresh_ollama_models()
        elif provider == "openai":
            self._refresh_openai_models()
        elif provider == "gemini":
            self._refresh_gemini_models()
        elif provider == "grok":
            self._refresh_grok_models()
        else:
            # Mock provider - no model selection needed
            self.model_combo.config(values=["mock"])
            self.model_var.set("mock")

    def _refresh_ollama_models(self):
        """Fetch available local Ollama models and populate the model dropdown"""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = resp.read().decode("utf-8")
                tags = json.loads(data)
                models = []
                if isinstance(tags, dict) and "models" in tags:
                    for m in tags["models"]:
                        name = m.get("name") or m.get("tag") or ""
                        if name:
                            models.append(name)
                elif isinstance(tags, list):
                    for m in tags:
                        name = m.get("name") or m.get("tag") or ""
                        if name:
                            models.append(name)
                if not models:
                    models = ["llama3.1", "mistral", "codellama"]
                self.model_combo.config(values=models)
                self.model_var.set(models[0])
                self.status_var.set(f"Loaded {len(models)} local Ollama models")
        except Exception as e:
            self.status_var.set("Ollama not reachable; using defaults")
            self.model_combo.config(values=["llama3.1", "llama3.2", "mistral", "mixtral", "codellama", "phi3"]) 
            self.model_var.set("llama3.1")

    def _check_docker_status(self):
        try:
            dm = DockerManager(".")
            ok, msg = dm.is_available()
            self.docker_status_var.set("Available" if ok else f"Not available: {msg[:60]}")
        except Exception as e:
            self.docker_status_var.set(f"Not available: {str(e)[:60]}")

    def _refresh_openai_models(self):
        try:
            from openai import OpenAI
            api_key = self.openai_key_var.get().strip()
            client = OpenAI(api_key=api_key) if api_key else OpenAI()
            models = client.models.list()
            names = [m.id for m in getattr(models, "data", [])]
            if not names:
                names = ["gpt-4-turbo", "gpt-3.5-turbo"]
            self.model_combo.config(values=names)
            self.model_var.set(names[0])
            self.status_var.set(f"Loaded {len(names)} OpenAI models")
        except Exception:
            self.model_combo.config(values=["gpt-4-turbo", "gpt-3.5-turbo"]) 
            self.model_var.set("gpt-4-turbo")

    def _refresh_gemini_models(self):
        try:
            import google.generativeai as genai
            api_key = self.gemini_key_var.get().strip()
            if api_key:
                genai.configure(api_key=api_key)
            models = list(genai.list_models())
            names = []
            for m in models:
                name = getattr(m, "name", None) or getattr(m, "model", None)
                if name:
                    names.append(name)
            if not names:
                names = ["gemini-1.5-flash", "gemini-1.5-pro"]
            self.model_combo.config(values=names)
            self.model_var.set(names[0])
            self.status_var.set(f"Loaded {len(names)} Gemini models")
        except Exception:
            self.model_combo.config(values=["gemini-1.5-flash", "gemini-1.5-pro"]) 
            self.model_var.set("gemini-1.5-flash")

    def _refresh_grok_models(self):
        try:
            self.model_combo.config(values=["grok-beta", "grok-1"]) 
            self.model_var.set("grok-beta")
            self.status_var.set("Loaded Grok models")
        except Exception:
            self.model_combo.config(values=["grok-beta"]) 
            self.model_var.set("grok-beta")

    def _on_progress_update(self, metrics: dict):
        try:
            sysm = metrics.get("system", {})
            total = max(1, int(sysm.get("total_tasks", 0)))
            completed = int(sysm.get("completed_tasks", 0))
            errors = int(sysm.get("total_errors", 0))
            recovered = int(sysm.get("recovered_errors", 0))
            success_rate = completed / total
            error_penalty = min(1.0, errors / (total * 2))
            recovery_bonus = min(0.2, recovered / max(1, errors + 1))
            score = max(0.0, min(1.0, success_rate - error_penalty + recovery_bonus))
            self.health_score_var.set(f"{score*100:.1f}%")
            recent = metrics.get("recent_events", [])
            self.error_listbox.delete(0, tk.END)
            for ev in recent:
                if ev.get("type") == "error":
                    msg = ev.get("message", "")
                    sid = ev.get("task_id") or "N/A"
                    self.error_listbox.insert(tk.END, f"{sid}: {msg[:80]}")
        except Exception:
            pass

    def _browse_spec(self):
        filename = filedialog.askopenfilename(
            title="Select Project Specification File",
            filetypes=[
                ("YAML files", "*.yaml"),
                ("YAML files", "*.yml"), 
                ("All files", "*.*")
            ],
            initialdir="examples"
        )
        if filename:
            self.spec_path_var.set(filename)
            self.status_var.set(f"Selected: {os.path.basename(filename)}")

    def _browse_output_dir(self):
        directory = filedialog.askdirectory(
            title="Select Output Directory for Generated Project",
            initialdir=self.output_dir_var.get() or os.getcwd()
        )
        if directory:
            self.output_dir_var.set(directory)
            self.status_var.set(f"Output directory: {directory}")

    def _load_config(self):
        self.openai_key_var.set(self.config_manager.get_api_key("openai") or "")
        self.anthropic_key_var.set(self.config_manager.get_api_key("anthropic") or "")
        self.gemini_key_var.set(self.config_manager.get_api_key("gemini") or "")
        self.grok_key_var.set(self.config_manager.get_api_key("grok") or "")

    def _save_keys(self):
        """Save API keys with validation and feedback"""
        try:
            self.config_manager.set_api_key("openai", self.openai_key_var.get())
            self.config_manager.set_api_key("anthropic", self.anthropic_key_var.get())
            self.config_manager.set_api_key("gemini", self.gemini_key_var.get())
            self.config_manager.set_api_key("grok", self.grok_key_var.get())
            messagebox.showinfo("Success", "✅ API Keys saved successfully!")
            self.status_var.set("API keys saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save API keys: {e}")
            self.status_var.set("Error saving API keys")

    def _test_connection(self):
        provider = self.provider_var.get()
        if provider == "mock":
            messagebox.showinfo("Mock Mode", "✅ Mock mode is always available for testing!")
            return
        try:
            if provider == "openai":
                from openai import OpenAI
                api_key = self.openai_key_var.get().strip()
                if not api_key:
                    messagebox.showwarning("No API Key", "Enter OpenAI API key first.")
                    return
                client = OpenAI(api_key=api_key)
                models = client.models.list()
                names = [m.id for m in getattr(models, "data", [])]
                messagebox.showinfo("OpenAI", f"✅ Connected. Models: {len(names)}")
                self.status_var.set(f"OpenAI connected: {len(names)} models")
            elif provider == "gemini":
                import google.generativeai as genai
                api_key = self.gemini_key_var.get().strip()
                if not api_key:
                    messagebox.showwarning("No API Key", "Enter Gemini API key first.")
                    return
                genai.configure(api_key=api_key)
                models = list(genai.list_models())
                messagebox.showinfo("Gemini", f"✅ Connected. Models: {len(models)}")
                self.status_var.set(f"Gemini connected: {len(models)} models")
            elif provider == "grok":
                from openai import OpenAI
                api_key = self.grok_key_var.get().strip()
                if not api_key:
                    messagebox.showwarning("No API Key", "Enter Grok API key first.")
                    return
                client = OpenAI(base_url="https://api.x.ai/v1", api_key=api_key)
                _ = client.chat.completions.create(model="grok-beta", messages=[{"role":"user","content":"ping"}])
                messagebox.showinfo("Grok", "✅ Connected and able to chat.")
                self.status_var.set("Grok connected")
            elif provider == "ollama":
                import urllib.request, json
                req = urllib.request.Request("http://localhost:11434/api/version")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = resp.read().decode("utf-8")
                self.status_var.set("Ollama connected")
                self._refresh_ollama_models()
                messagebox.showinfo("Ollama", "✅ Connected and models loaded.")
            else:
                messagebox.showinfo("Provider", f"Unsupported provider: {provider}")
        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))
            self.status_var.set(f"Connection failed: {str(e)[:60]}")

    def _start_run(self):
        spec_path = self.spec_path_var.get()
        if not spec_path:
            messagebox.showerror("Error", "Please select a specification file.")
            return
            
        if not os.path.exists(spec_path):
            messagebox.showerror("Error", f"Specification file not found: {spec_path}")
            return
            
        self.run_btn.config(state=tk.DISABLED)
        self.is_running = True
        self.log_text.delete(1.0, tk.END)
        self.status_var.set("Starting supervisor...")
        
        # Start progress bar
        self.progress_bar.start()
        
        # Add timestamp to logs
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] Starting Auto-Dev Supervisor...\n")
        self.log_text.insert(tk.END, f"[{timestamp}] Project Spec: {os.path.basename(spec_path)}\n")
        self.log_text.insert(tk.END, f"[{timestamp}] Output Directory: {self.output_dir_var.get()}\n")
        self.log_text.insert(tk.END, f"[{timestamp}] LLM Provider: {self.provider_var.get()}\n")
        if self.provider_var.get() in ["openai", "ollama", "gemini", "grok"]:
            self.log_text.insert(tk.END, f"[{timestamp}] Model: {self.model_var.get()}\n")
        self.log_text.insert(tk.END, f"[{timestamp}] Skip Git: {self.skip_git_var.get()}\n")
        self.log_text.insert(tk.END, "-" * 60 + "\n")
        
        # Run in thread to keep GUI responsive
        thread = threading.Thread(target=self._run_supervisor, args=(spec_path, self.output_dir_var.get()))
        thread.daemon = True
        thread.start()

    def _run_supervisor(self, spec_path, output_dir):
        """Run the supervisor with proper status updates and error handling"""
        # Redirect stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)
        
        try:
            self.status_var.set("Initializing components...")
            
            # Setup components with user-selected output directory
            project_root = output_dir
            abs_project_root = os.path.abspath(project_root)
            
            # Create output directory if it doesn't exist
            os.makedirs(abs_project_root, exist_ok=True)
            self.log_text.insert(tk.END, f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Output directory: {abs_project_root}\n")
            
            self.status_var.set("Setting up planner...")
            planner = Planner()
            
            self.status_var.set(f"Configuring {self.provider_var.get()} provider...")
            provider = self.provider_var.get()
            if provider in ["openai", "ollama", "gemini", "grok"]:
                # Validate API key exists
                key_mapping = {
                    "openai": self.openai_key_var,
                    "gemini": self.gemini_key_var,
                    "grok": self.grok_key_var
                }
                
                if provider in key_mapping and not key_mapping[provider].get().strip():
                    raise ValueError(f"No API key configured for {provider}. Please add it in Configuration tab.")
                    
                # Use enhanced LLM client with speed optimizations
                opendevin = EnhancedGenAIOpenDevinClient(
                    provider=provider, 
                    model=self.model_var.get(), 
                    config_manager=self.config_manager,
                    project_root=abs_project_root,
                    enable_cache=self.enable_cache_var.get(),
                    enable_streaming=self.enable_streaming_var.get(),
                    max_parallel_requests=3
                )
            else:
                opendevin = MockOpenDevinClient()
                
            self.status_var.set("Setting up Docker manager...")
            docker_manager = DockerManager(abs_project_root)
            
            self.status_var.set("Setting up Git manager...")
            # We need to parse spec to get repo url for git manager
            try:
                spec = planner.parse_spec(spec_path)
                git_manager = GitManager(abs_project_root, spec.repository_url, spec.branch)
            except Exception:
                # If parsing fails here, supervisor will catch it too, or we just pass dummy
                git_manager = GitManager(abs_project_root, "dummy", "main")
            
            self.status_var.set("Setting up QA manager...")
            qa_manager = QAManager()
            
            self.status_var.set("Creating supervisor...")
            if self.use_enhanced_supervisor_var.get():
                supervisor = EnhancedSupervisor(
                    planner=planner,
                    opendevin=opendevin,
                    docker_manager=docker_manager,
                    git_manager=git_manager,
                    qa_manager=qa_manager,
                    project_root=abs_project_root,
                    skip_git=self.skip_git_var.get(),
                    skip_docker=self.skip_docker_var.get(),
                    enable_advanced_recovery=self.enable_advanced_recovery_var.get()
                )
            else:
                supervisor = Supervisor(
                    planner=planner,
                    opendevin=opendevin,
                    docker_manager=docker_manager,
                    git_manager=git_manager,
                    qa_manager=qa_manager,
                    project_root=abs_project_root,
                    skip_git=self.skip_git_var.get(),
                    skip_docker=self.skip_docker_var.get()
                )
            supervisor.progress_monitor.add_update_callback(self._on_progress_update)
            
            self.status_var.set("Running supervisor...")
            print(f"\n🚀 Starting supervisor execution...")
            print(f"📋 Spec: {os.path.basename(spec_path)}")
            print(f"🔧 Provider: {provider}")
            if provider in ["openai", "ollama", "gemini", "grok"]:
                print(f"🤖 Model: {self.model_var.get()}")
            print(f"📦 Skip Git: {self.skip_git_var.get()}")
            if self.skip_docker_var.get():
                print(f"🐳 Skip Docker: {self.skip_docker_var.get()}")
            print("-" * 60 + "\n")
            
            supervisor.run(spec_path)
            
            self.status_var.set("Completed successfully")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] ✅ Supervisor run completed successfully!")
            
            messagebox.showinfo("Success", "🎉 Supervisor run completed successfully!")
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)[:50]}...")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] ❌ Error: {e}")
            print(f"[{timestamp}] 💡 Check the logs above for more details.")
            messagebox.showerror("Error", f"An error occurred during supervisor execution:\n\n{e}\n\nCheck the logs for more details.")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.run_btn.config(state=tk.NORMAL)
            self.is_running = False
            self.progress_bar.stop()
            self.status_var.set("Ready")

def main():
    app = AutoDevApp()
    app.mainloop()

if __name__ == "__main__":
    main()
