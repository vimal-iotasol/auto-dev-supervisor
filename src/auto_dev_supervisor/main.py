import typer
import os
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.core.supervisor import Supervisor
from auto_dev_supervisor.core.enhanced_supervisor import EnhancedSupervisor
from auto_dev_supervisor.infra.opendevin import MockOpenDevinClient
from auto_dev_supervisor.infra.llm import GenAIOpenDevinClient
from auto_dev_supervisor.infra.enhanced_llm import EnhancedGenAIOpenDevinClient
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.qa import QAManager
from auto_dev_supervisor.gui.app import main as gui_main

app = typer.Typer()

@app.command()
def gui():
    """
    Launch the Auto-Dev Supervisor GUI.
    """
    gui_main()

@app.command()
def run(
    spec_path: str = typer.Argument(..., help="Path to the project YAML specification"),
    project_root: str = typer.Option(".", "--project-root", help="Root directory for the project to be managed"),
    max_retries: int = typer.Option(5, "--max-retries", help="Maximum retries for auto-fixing issues (enhanced supervisor uses 5 by default)"),
    skip_git: bool = typer.Option(False, "--skip-git", help="Skip git commit and push operations"),
    llm_provider: str = typer.Option("openai", "--llm-provider", help="LLM provider to use: 'mock', 'openai', 'ollama', 'gemini', 'grok'"),
    model: str = typer.Option(None, "--model", help="Specific model to use (e.g., 'gpt-4-turbo', 'gemini-1.5-flash', 'llama3.1', 'mixtral')"),
    skip_docker: bool = typer.Option(False, "--skip-docker", help="Run without Docker build/test"),
    enable_cache: bool = typer.Option(True, "--enable-cache", help="Enable response caching for faster performance"),
    enable_streaming: bool = typer.Option(True, "--enable-streaming", help="Enable streaming responses for faster perceived performance"),
    use_enhanced_supervisor: bool = typer.Option(True, "--use-enhanced-supervisor", help="Use enhanced supervisor with iterative error resolution"),
    enable_advanced_recovery: bool = typer.Option(True, "--enable-advanced-recovery", help="Enable advanced recovery strategies"),
    max_parallel_requests: int = typer.Option(3, "--max-parallel-requests", help="Maximum parallel LLM requests for faster processing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    Run the Autonomous Developer Supervisor.
    """
    import logging
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    abs_project_root = os.path.abspath(project_root)
    
    # Initialize components
    planner = Planner()
    
    opendevin = None
    if llm_provider in ["openai", "ollama", "gemini", "grok"]:
        # Set appropriate default models for each provider
        default_models = {
            "openai": "gpt-4-turbo",
            "ollama": "llama3.1",
            "gemini": "gemini-1.5-flash",
            "grok": "grok-beta"
        }
        selected_model = model or default_models.get(llm_provider, "gpt-4-turbo")
        # Use enhanced LLM client for better performance
        opendevin = EnhancedGenAIOpenDevinClient(
            provider=llm_provider, 
            model=selected_model,
            project_root=abs_project_root,
            enable_cache=enable_cache,
            enable_streaming=enable_streaming,
            max_parallel_requests=max_parallel_requests
        )
    else:
        opendevin = MockOpenDevinClient()
        
    docker_manager = DockerManager(abs_project_root)
    
    # For GitManager, we need to parse the spec first to get the repo URL, 
    # but the Supervisor does that. 
    # So we'll initialize GitManager with placeholders and let it re-init if needed,
    # or better, we pass the factory or just init it with the root and let it handle the rest.
    # For simplicity, we'll assume the spec is available or we parse it quickly here to get the repo URL.
    spec = planner.parse_spec(spec_path)
    git_manager = GitManager(abs_project_root, spec.repository_url, spec.branch)
    
    qa_manager = QAManager()
    
    # Use enhanced supervisor for better error resolution and speed
    if use_enhanced_supervisor:
        supervisor = EnhancedSupervisor(
            planner=planner,
            opendevin=opendevin,
            docker_manager=docker_manager,
            git_manager=git_manager,
            qa_manager=qa_manager,
            project_root=abs_project_root,
            max_retries=max_retries,
            skip_git=skip_git,
            skip_docker=skip_docker,
            enable_advanced_recovery=enable_advanced_recovery
        )
    else:
        supervisor = Supervisor(
            planner=planner,
            opendevin=opendevin,
            docker_manager=docker_manager,
            git_manager=git_manager,
            qa_manager=qa_manager,
            project_root=abs_project_root,
            max_retries=max_retries,
            skip_git=skip_git,
            skip_docker=skip_docker
        )
    
    supervisor.run(spec_path)

if __name__ == "__main__":
    app()
