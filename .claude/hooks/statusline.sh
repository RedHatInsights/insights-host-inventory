#!/bin/bash
# HBI Claude Code status line — shows model, git branch, context usage, and cost.
# Receives JSON session data via stdin from Claude Code.

input=$(cat)

# Model
MODEL=$(echo "$input" | jq -r '.model.display_name // "—"')

# Context window
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
BAR_WIDTH=10
FILLED=$((PCT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=$(printf "%${FILLED}s" | tr ' ' '#')$(printf "%${EMPTY}s" | tr ' ' '-')

# Color context bar: green <50%, yellow 50-79%, red 80%+
if [ "$PCT" -ge 80 ]; then
    COLOR='\033[31m'  # red
elif [ "$PCT" -ge 50 ]; then
    COLOR='\033[33m'  # yellow
else
    COLOR='\033[32m'  # green
fi
RESET='\033[0m'

# Cost
COST=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
COST_FMT=$(printf '$%.2f' "$COST")

# Project name (directory name of the workspace)
PROJECT=$(echo "$input" | jq -r '.workspace.project_dir // .workspace.current_dir // ""' | xargs basename 2>/dev/null || echo "—")

# Git branch (cached: re-read at most every 5s via find -mtime)
CACHE_FILE="/tmp/.claude_hbi_git_cache"
BRANCH="—"
STALE=1
if [ -f "$CACHE_FILE" ]; then
    # File exists and was modified less than 5 seconds ago → not stale
    if [ -z "$(find "$CACHE_FILE" -mmin +0.08 2>/dev/null)" ]; then
        STALE=0
    fi
fi
if [ "$STALE" -eq 1 ]; then
    BRANCH=$(git branch --show-current 2>/dev/null || echo "—")
    echo "$BRANCH" > "$CACHE_FILE" 2>/dev/null
else
    BRANCH=$(cat "$CACHE_FILE" 2>/dev/null || echo "—")
fi

echo -e "[${MODEL}] ${PROJECT}:${BRANCH} | ${COLOR}${BAR}${RESET} ${PCT}% | ${COST_FMT}"
