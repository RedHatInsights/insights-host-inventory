#
# Initial file (included as the first)
#

project_dir:=$(shell dirname $(abspath $(firstword $(MAKEFILE_LIST))))

# Define the AWK command based on platform (gawk on macOS, awk elsewhere)
AWK = awk
ifeq ($(shell uname),Darwin)
AWK = gawk
endif
