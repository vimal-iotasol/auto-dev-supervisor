# User Guide - Autonomous Developer Supervisor (`auto-dev`)

This guide provides detailed instructions on how to set up, configure, and run the `auto-dev` system.

## 1. Prerequisites

Before running `auto-dev`, ensure you have the following installed:

- **Python 3.11+**: The core language for the supervisor.
- **Docker & Docker Compose**: Required for creating isolated build and test environments.
- **Git**: Required for version control operations.
- **Poetry**: The package manager used for dependency management.

## 2. Installation

1.  **Clone the Repository** (if you haven't already):
    ```bash
    git clone <your-repo-url>
    cd auto-dev-supervisor
    ```

2.  **Install Dependencies**:
    ```bash
    poetry install
    ```
    This will create a virtual environment and install all required packages, including `openai`, `docker`, and `gitpython`.

## 3. Configuration

### Environment Variables

If you plan to use the Generative AI features (OpenAI), you must set your API key:

**Linux/macOS:**
```bash
export OPENAI_API_KEY="sk-..."
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY="sk-..."
```

### Project Specification (YAML)

The supervisor runs based on a YAML specification file. Create a file (e.g., `my_app.yaml`) with the following structure:

```yaml
name: "My Application"
version: "0.1.0"
repository_url: "https://github.com/user/my-app.git"
branch: "main"

services:
  - name: "backend"
    type: "backend"
    description: "A Flask-based REST API"
    docker_image_base: "python:3.11-slim"
    
  - name: "frontend"
    type: "frontend"
    description: "React frontend"
    dependencies: ["backend"]
```

## 4. Running the Application

The CLI tool is named `auto-dev`. You can run it using `poetry run auto-dev`.

### Use Case A: Simulation / Mock Mode (Default)

Best for testing the supervisor logic without spending API credits or performing real git pushes.

```bash
poetry run auto-dev run examples/simple_app.yaml
```

- **Behavior**: Uses `MockOpenDevinClient`. It simulates code generation and test passing.
- **Git**: Will attempt to commit to the local repo defined in the spec (or create one).

### Use Case B: Real AI Development (OpenAI)

Uses OpenAI's GPT-4 (or configured model) to actually write code files based on your spec.

```bash
export OPENAI_API_KEY="sk-..."
poetry run auto-dev run examples/simple_app.yaml --llm-provider openai
```

- **Behavior**: Sends prompts to OpenAI. Writes actual files to disk.
- **Note**: Ensure your spec description is detailed enough for the AI to understand what to build.

### Use Case C: Local Experimentation (Skip Git)

If you want to generate code but don't want to pollute your git history or don't have a remote set up.

```bash
poetry run auto-dev run examples/simple_app.yaml --skip-git
```

- **Behavior**: Runs the full Plan -> Implement -> Verify cycle but skips `git commit` and `git push`.

### Use Case D: Full Autonomous Mode

The "Real Deal". Uses GenAI and pushes to Git.

```bash
export OPENAI_API_KEY="sk-..."
poetry run auto-dev run examples/simple_app.yaml --llm-provider openai
```

## 5. Troubleshooting

### Docker Issues
- **Error**: `DockerException: Error while fetching server API version`
- **Fix**: Ensure Docker Desktop is running. Try running `docker ps` in your terminal to verify.

### OpenAI Issues
- **Error**: `Error: No API Key provided for GenAI client.`
- **Fix**: Set the `OPENAI_API_KEY` environment variable.

### Git Issues
- **Error**: Authentication failed during push.
- **Fix**: Ensure your local git is configured with credentials, or use SSH keys. For the supervisor, it uses the local git configuration.

## 6. Advanced: ML/Audio Metrics

If your service has `type: audio` or `ml`, you can define quality metrics in the YAML:

```yaml
  - name: "tts-engine"
    type: "audio"
    ml_metrics:
      - name: "mcd"
        threshold: 6.0
        operator: "<"
```

The supervisor will parse the test output for `MCD: <value>` and fail the task if the threshold is not met.
