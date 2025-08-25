#
# Entrypoint for the Makefile
#
# It is composed at mk/includes.mk by including
# small make files which provides all the necessary
# rules.
#
# Some considerations:
#
# - By default the 'help' rule is executed.
# - No parallel jobs are executed from the main Makefile,
#   so that multiple rules from the command line will be
#   executed in serial.
# - Create 'mk/private.mk' for custom targets.
#

include mk/*.mk

.NOT_PARALLEL:

# Set the default rule
.DEFAULT_GOAL := help
