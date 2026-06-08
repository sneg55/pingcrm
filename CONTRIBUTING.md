# Contributing to PingCRM

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/sneg55/pingcrm.git
   cd pingcrm
   ```

2. **Start the database and Redis**
   ```bash
   cp .env.docker.example .env  # edit POSTGRES_PASSWORD and SECRET_KEY
   docker compose up -d postgres redis
   ```

3. **Backend**
   ```bash
   cd backend
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # Fill in required values
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

4. **Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. **Run tests**
   ```bash
   cd backend && pytest
   cd frontend && npm test
   ```

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Make your changes with tests
3. Ensure all tests pass
4. Submit a PR with a clear description of what and why

## Code Style

- **Python:** snake_case, type hints, async where appropriate
- **TypeScript:** camelCase for variables/functions, PascalCase for components
- See `CLAUDE.md` for full conventions

## Reporting Issues

Use GitHub Issues with the provided templates. Include steps to reproduce for bugs.

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license.
