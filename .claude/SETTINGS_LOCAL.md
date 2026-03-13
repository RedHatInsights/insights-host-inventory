# Claude Code Personal Settings

## What is `.claude/settings.local.json`?

This file allows you to configure **personal command permissions** for Claude Code. It eliminates repetitive permission prompts for commands you frequently use during development.

## Why Use It?

**Without this file:** Claude Code asks for permission every time it wants to run a command like `pytest`, `make style`, or `git status`.

**With this file:** Commands you've pre-approved run automatically, making your workflow faster and more efficient.

## Setup (One-Time)

1. Copy the example file:
   ```bash
   cp .claude/settings.local.json.example .claude/settings.local.json
   ```

2. Remove the `"_comment*"` lines (JSON doesn't support comments)

3. Customize the `"allow"` list for your workflow

4. **Important:** This file is already in `.gitignore` - do NOT commit it!

## Configuration Blocks

The example file contains two blocks:

### Block 1: UNIVERSAL (Recommended for Everyone)
```json
"Bash(make style:*)",
"Bash(pytest:*)",
"Bash(pipenv run pytest:*)",
"Bash(python3 -m pytest:*)",
"Bash(python -m py_compile:*)"
```
These are safe, commonly-used HBI development commands. **Everyone should enable these.**

### Block 2: RECOMMENDED (Personal Workflow Optimizations)
```json
"Bash(PIPENV_CUSTOM_VENV_NAME=insights-host-inventory-main pipenv run mypy:*)",
"Bash(PIPENV_PIPFILE=Pipfile.iqe PIPENV_CUSTOM_VENV_NAME=insights-host-inventory-iqe pipenv run:*)",
"Bash(grep:*)",
"Bash(kubectl exec:*)",
...
```

**Special Recommendation: `PIPENV_CUSTOM_VENV_NAME`**

Using `PIPENV_CUSTOM_VENV_NAME` ensures your virtualenvs remain consistent across sessions:
- `insights-host-inventory-main` - For main development (Pipfile)
- `insights-host-inventory-iqe` - For IQE tests (Pipfile.iqe)

See `CLAUDE.local.md` Session 17 for detailed explanation of why this matters.

## Security Note

⚠️ **Only auto-approve commands you understand and trust.**

Review each permission pattern carefully:
- `Bash(pytest:*)` - Safe: Just runs tests
- `Bash(kubectl exec:*)` - Caution: Executes commands in pods
- `Bash(make style:*)` - Safe: Just formats code

When in doubt, leave it out. Claude will ask for permission when needed.

## File vs. Directory Permissions

- **`.claude/settings.local.json`** - Your personal preferences (NOT committed)
- **`.claude/settings.json`** - Team-wide shared settings (committed to repo)

Both files work together. Personal settings take precedence.

## Learn More

For advanced permission options and features:
- [Claude Code Documentation](https://docs.anthropic.com/en/docs/build-with-claude/claude-for-sheets)
- See `.claude/settings.json` for team-wide settings examples
