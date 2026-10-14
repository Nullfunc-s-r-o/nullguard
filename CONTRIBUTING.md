# Contributing to NullGuard

Thank you for your interest in contributing to NullGuard! We welcome issues, pull requests, and feedback.

## Developer Setup

1. Clone the repository.
2. Run `./install.sh --dev` to install with developer dependencies (like `ruff` and `pytest`).
3. Make sure you have `cmake` and `g++` (or equivalent) installed for C++ extension development.

## Commit Guidelines

We strictly follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.

Please ensure your commit messages follow this format:
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Allowed Types
- **feat**: A new feature (correlates with MINOR in Semantic Versioning).
- **fix**: A bug fix (correlates with PATCH in Semantic Versioning).
- **docs**: Documentation only changes.
- **style**: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc).
- **refactor**: A code change that neither fixes a bug nor adds a feature.
- **perf**: A code change that improves performance.
- **test**: Adding missing tests or correcting existing tests.
- **chore**: Changes to the build process or auxiliary tools and libraries such as documentation generation.

### Updating the Changelog
Whenever you submit a Pull Request that contains a `feat`, `fix`, `perf`, or breaking change, you **must** update the `CHANGELOG.md` under the `[Unreleased]` header.

## Pull Requests
- Ensure your code passes all linters (`ruff`).
- Describe the changes thoroughly in the PR description.
