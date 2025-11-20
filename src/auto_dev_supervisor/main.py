import typer
import os
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.core.supervisor import Supervisor
from auto_dev_supervisor.infra.opendevin import MockOpenDevinClient
from auto_dev_supervisor.infra.llm import GenAIOpenDevinClient
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.qa import QAManager

app = typer.Typer()

@app.command()
def run(
    spec_path: str = typer.Argument(..., help="Path to the project YAML specification"),
    project_root: str = typer.Option(".", help="Root directory for the project to be managed"),
    max_retries: int = typer.Option(3, help="Maximum retries for auto-fixing issues"),
    skip_git: bool = typer.Option(False, help="Skip git commit and push operations"),
    llm_provider: str = typer.Option("mock", help="LLM provider to use: 'mock' or 'openai'")
):
    """
    Run the Autonomous Developer Supervisor.
    """
    abs_project_root = os.path.abspath(project_root)
    
    # Initialize components
    planner = Planner()
    
    opendevin = None
    if llm_provider == "openai":
        opendevin = GenAIOpenDevinClient()
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
    
    supervisor = Supervisor(
        planner=planner,
        opendevin=opendevin,
        docker_manager=docker_manager,
        git_manager=git_manager,
        qa_manager=qa_manager,
        max_retries=max_retries,
        skip_git=skip_git
    )
    
    supervisor.run(spec_path)

if __name__ == "__main__":
    app()
