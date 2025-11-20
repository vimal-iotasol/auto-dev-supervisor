# Autonomous Developer Supervisor (`auto-dev`)

A production-grade Autonomous Developer Supervisor Application that controls OpenDevin (or LLMs) like a real software developer employee.

## 📚 Documentation

- **[User Guide](docs/USER_GUIDE.md)**: Detailed setup, configuration, and usage instructions.
- **[Architecture](docs/ARCHITECTURE.md)**: System design and component overview.

## ✨ Features

- **Managerial Role**: Accepts YAML project specs and plans tasks.
- **Iterative Development**: PLAN -> IMPLEMENT -> BUILD -> TEST -> QA -> FIX -> COMMIT -> PUSH.
- **Dockerized Environments**: Builds and tests apps in isolated containers.
- **ML/Audio QA**: Enforces quality metrics (MCD, SNR, MOS) for AI apps.
- **Git Automation**: Commits only stable code with detailed messages.
- **GenAI Integration**: Uses LLMs (OpenAI) to write and fix code.
- **Flexible Workflow**: Supports `--skip-git` for local experimentation.

## 🚀 Quick Start

1.  **Install**:
    ```bash
    poetry install
    ```

2.  **Run Example (Mock Mode)**:
    ```bash
    poetry run auto-dev run examples/simple_app.yaml
    ```

3.  **Run with OpenAI**:
    ```bash
    export OPENAI_API_KEY="your-key"
    poetry run auto-dev run examples/simple_app.yaml --llm-provider openai --skip-git
    ```

## 🧪 Testing

Run the internal test suite to verify the supervisor itself:

```bash
poetry run pytest
```

## License

MIT
