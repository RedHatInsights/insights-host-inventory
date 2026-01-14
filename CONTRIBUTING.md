# Contributing to Insights Host Inventory

Thank you for your interest in contributing to the Insights Host Based Inventory (HBI) service!

## Commit Message Format

We follow the [Angular Conventional Commits](https://www.conventionalcommits.org/) format for commit messages. This helps us maintain a clear and consistent git history.

### Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

### Types

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that do not affect the meaning of the code (white-space, formatting, etc)
- **refactor**: A code change that neither fixes a bug nor adds a feature
- **perf**: A code change that improves performance
- **test**: Adding missing tests or correcting existing tests
- **build**: Changes that affect the build system or external dependencies
- **ci**: Changes to CI configuration files and scripts
- **chore**: Other changes that don't modify src or test files

### Scope

The scope should be the **ticket number** (e.g., RHINENG-12345).

**Ticket is required for `feat` and `fix` types.**

### Examples

```
feat(RHINENG-12345): add support for system profile filtering

fix(RHINENG-456): correct staleness calculation for edge devices

docs: update API documentation for groups endpoint

refactor: simplify host repository query logic

test(RHINENG-789): add coverage for export service edge cases

build(deps): bump sqlalchemy from 1.4.0 to 1.4.1
```

### Guidelines

1. Keep the subject line under 72 characters
2. Use the imperative mood in the subject line ("add" not "added" or "adds")
3. Do not end the subject line with a period
4. Separate subject from body with a blank line
5. Use the body to explain what and why vs. how
6. Always include a ticket number in the scope for `feat` and `fix` types

## Development Setup

See [CLAUDE.md](./CLAUDE.md) for detailed development commands and environment setup instructions.

## Testing

Before submitting a pull request:

1. Run all tests: `pytest --cov=.`
2. Check code formatting: `make style`
3. Ensure all CI checks pass

## Questions?

If you have questions about contributing, please reach out to the team or open an issue for discussion.
