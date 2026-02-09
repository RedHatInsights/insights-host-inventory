#
# Initial file (included as the first)
#

project_dir:=$(shell dirname $(abspath $(firstword $(MAKEFILE_LIST))))

# Define the AWK command; prefer gawk if available, fall back to awk
AWK := $(shell command -v gawk 2>/dev/null || echo awk)
