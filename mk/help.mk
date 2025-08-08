##@ Help
#
# This file only contains the rule that generate the
# help content from the comments in the different files.
#
# Use '##@ My group text' at the beginning of a line to
# print out a group text.
#
# Use '## My help text' at the end of a rule to print out
# content related with a rule. Try to short the description.
#

MAKE_DOC=docs/make.md

.PHONY: help
help: ## Print out the help content
	@echo "Available targets: $(MAKEFILE_LIST)"
	$(AWK) 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: generate-help-doc
generate-help-doc: ## Generate 'make help' markdown in docs/
	@echo '# Make documentation' > $(MAKE_DOC)
	@echo '```' >> $(MAKE_DOC)
	@make -s help | sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,2})?)?[mGK]//g" >> $(MAKE_DOC)
	@echo '```' >> $(MAKE_DOC)

.PHONY: validate-help-doc
validate-help-doc: generate-help-doc ## Compare example configuration
	@git diff --exit-code $(MAKE_DOC)
