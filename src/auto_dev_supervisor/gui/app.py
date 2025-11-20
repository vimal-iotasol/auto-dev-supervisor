import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import sys
import io
from typing import Optional

from auto_dev_supervisor.core.config import ConfigManager
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.core.supervisor import Supervisor
from auto_dev_supervisor.infra.opendevin import MockOpenDevinClient
from auto_dev_supervisor.infra.llm import GenAIOpenDevinClient
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
        self.title("Auto-Dev Supervisor")
        self.geometry("800x600")
        
        self.config_manager = ConfigManager()
        
        self._create_widgets()
        self._load_config()

    def _create_widgets(self):
        # Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Run
        self.run_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.run_frame, text="Run")
        self._create_run_tab()
        
        # Tab 2: Configuration
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="Configuration")
        self._create_config_tab()

    def _create_config_tab(self):
        frame = ttk.LabelFrame(self.config_frame, text="API Keys", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=10)
        
        # OpenAI
        ttk.Label(frame, text="OpenAI API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.openai_key_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.openai_key_var, width=50, show="*").grid(row=0, column=1, padx=5)
        
        # Anthropic (Placeholder)
        ttk.Label(frame, text="Anthropic API Key:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.anthropic_key_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.anthropic_key_var, width=50, show="*").grid(row=1, column=1, padx=5)

        # Gemini
        ttk.Label(frame, text="Gemini API Key:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.gemini_key_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.gemini_key_var, width=50, show="*").grid(row=2, column=1, padx=5)

        # Grok
        ttk.Label(frame, text="Grok API Key:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.grok_key_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.grok_key_var, width=50, show="*").grid(row=3, column=1, padx=5)
        
        # Save Button
        ttk.Button(frame, text="Save Keys", command=self._save_keys).grid(row=4, column=1, sticky=tk.E, pady=10)

    def _create_run_tab(self):
        # Spec Selection
        spec_frame = ttk.Frame(self.run_frame)
        spec_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(spec_frame, text="Project Spec (YAML):").pack(side=tk.LEFT)
        self.spec_path_var = tk.StringVar()
        ttk.Entry(spec_frame, textvariable=self.spec_path_var, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(spec_frame, text="Browse", command=self._browse_spec).pack(side=tk.LEFT)
        
        # Options
        opts_frame = ttk.Frame(self.run_frame)
        opts_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.skip_git_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Skip Git Operations", variable=self.skip_git_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Label(opts_frame, text="LLM Provider:").pack(side=tk.LEFT, padx=5)
        self.provider_var = tk.StringVar(value="mock")
        ttk.Combobox(opts_frame, textvariable=self.provider_var, values=["mock", "openai", "ollama", "gemini", "grok"]).pack(side=tk.LEFT)
        
        # Run Button
        self.run_btn = ttk.Button(self.run_frame, text="Run Supervisor", command=self._start_run)
        self.run_btn.pack(pady=10)
        
        # Logs
        log_frame = ttk.LabelFrame(self.run_frame, text="Logs", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _browse_spec(self):
        filename = filedialog.askopenfilename(filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")])
        if filename:
            self.spec_path_var.set(filename)

    def _load_config(self):
        self.openai_key_var.set(self.config_manager.get_api_key("openai") or "")
        self.anthropic_key_var.set(self.config_manager.get_api_key("anthropic") or "")
        self.gemini_key_var.set(self.config_manager.get_api_key("gemini") or "")
        self.grok_key_var.set(self.config_manager.get_api_key("grok") or "")

    def _save_keys(self):
        self.config_manager.set_api_key("openai", self.openai_key_var.get())
        self.config_manager.set_api_key("anthropic", self.anthropic_key_var.get())
        self.config_manager.set_api_key("gemini", self.gemini_key_var.get())
        self.config_manager.set_api_key("grok", self.grok_key_var.get())
        messagebox.showinfo("Success", "API Keys saved successfully!")

    def _start_run(self):
        spec_path = self.spec_path_var.get()
        if not spec_path:
            messagebox.showerror("Error", "Please select a specification file.")
            return
            
        self.run_btn.config(state=tk.DISABLED)
        self.log_text.delete(1.0, tk.END)
        
        # Run in thread to keep GUI responsive
        thread = threading.Thread(target=self._run_supervisor, args=(spec_path,))
        thread.daemon = True
        thread.start()

    def _run_supervisor(self, spec_path):
        # Redirect stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)
        
        try:
            # Setup components
            project_root = "." # Use current working directory
            abs_project_root = os.path.abspath(project_root)
            
            planner = Planner()
            
            provider = self.provider_var.get()
            if provider in ["openai", "ollama", "gemini", "grok"]:
                opendevin = GenAIOpenDevinClient(provider=provider, config_manager=self.config_manager)
            else:
                opendevin = MockOpenDevinClient()
                
            docker_manager = DockerManager(abs_project_root)
            
            # We need to parse spec to get repo url for git manager
            # But supervisor does that too. 
            # Let's just init git manager with placeholders if we skip git, or try to parse.
            # For robustness in this demo, we'll assume git manager handles lazy init or we parse here.
            try:
                spec = planner.parse_spec(spec_path)
                git_manager = GitManager(abs_project_root, spec.repository_url, spec.branch)
            except Exception:
                # If parsing fails here, supervisor will catch it too, or we just pass dummy
                git_manager = GitManager(abs_project_root, "dummy", "main")
            
            qa_manager = QAManager()
            
            supervisor = Supervisor(
                planner=planner,
                opendevin=opendevin,
                docker_manager=docker_manager,
                git_manager=git_manager,
                qa_manager=qa_manager,
                skip_git=self.skip_git_var.get()
            )
            
            supervisor.run(spec_path)
            
            messagebox.showinfo("Finished", "Supervisor run completed.")
            
        except Exception as e:
            print(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.run_btn.config(state=tk.NORMAL)

def main():
    app = AutoDevApp()
    app.mainloop()

if __name__ == "__main__":
    main()
