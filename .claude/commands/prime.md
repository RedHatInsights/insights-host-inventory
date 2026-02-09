# /prime - Orient Agent to HBI Codebase

Quick-start orientation to understand the HBI project structure and configuration.

## Instructions

1. Run `git ls-files | head -100` to get an overview of the project file structure.

2. Read these key files:
   - `CLAUDE.md` - Development guidance and architecture overview
   - `README.md` - Project documentation
   - `.claude/settings.json` - Claude Code hook configuration
   - `mk/private.mk` - Available development workflow and Claude Code recipes

3. List all files in `.claude/hooks/` and `.claude/commands/` and briefly describe each.

4. Read `dev.yml` to understand the Podman Compose service topology.

5. Report a concise summary to the user:
   - Project name and purpose
   - Key services and their roles
   - Available development commands (from CLAUDE.md)
   - Available `make` targets (from mk/private.mk)
   - Available Claude Code slash commands
   - Current git branch and recent commits (`git log --oneline -5`)
   - Podman service status if running (`podman compose -f dev.yml ps` - don't fail if not running)

Keep the output concise and focused on what a developer needs to start working.
