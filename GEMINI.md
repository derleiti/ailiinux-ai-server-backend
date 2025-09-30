# Gemini Workspace Analysis

This document provides a comprehensive overview of the projects and development conventions within this workspace. It is intended to be used as a guide for developers and AI agents to understand the codebase and contribute effectively.

## Project Overview

This workspace contains the `ailinux-ai-server-backend` project, a machine learning server built with FastAPI (Python). It provides AI-powered services and leverages libraries like `torch`, `transformers`, and `pillow`. The application is structured in a modular way, with different routers for services like agents, chat, crawler, models, stable diffusion, and vision.

## Building and Running

The following commands are used to build, run, and test the project.

*   **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
*   **Run Development Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
*   **Run in a production-like environment:**
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 9100
    ```
*   **Run Tests:**
    ```bash
    pytest
    ```

## Development Conventions

The following development conventions are used in this project.

*   **Source Code:** Source code is located in the `app/` directory, organized by domain. Core logic is delegated to `app/services/` and shared helpers to `app/utils/`.
*   **Tests:** Tests are located in the `tests/` directory and mirror the source code structure. Shared fixtures are in `tests/conftest.py`.
*   **Commits:** Commits should follow the Conventional Commits specification.
*   **Pull Requests:** Pull requests should have a concise description and be linked to an issue.
*   **Security:** Never commit secrets. Use a local `.env` file.
*   **Formatting:** Use PEP 8, with four-space indentation and snake_case for variables, functions, and modules. `CamelCase` is used for Pydantic models or classes.
