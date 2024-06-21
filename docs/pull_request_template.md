# Overview

This PR is being created to address [RHINENG-xxxx](https://issues.redhat.com/browse/RHINENG-xxxx).
(A description of your PR's changes, along with why/context to the PR, goes here.)

## PR Checklist

- [ ] Keep PR title short, ideally under 72 characters
- [ ] Descriptive comments provided in complex code blocks
- [ ] Include raw query examples in the PR description, if adding/modifying SQL query
- [ ] Tests: validate optimal/expected output
- [ ] Tests: validate exceptions and failure scenarios
- [ ] Tests: edge cases
- [ ] Recovers or fails gracefully during potential resource outages (e.g. DB, Kafka)
- [ ] Uses [type hinting](https://docs.python.org/3/library/typing.html), if convenient
- [ ] Documentation, if this PR changes the way other services interact with host inventory
- [ ] Links to related PRs

## Secure Coding Practices Documentation Reference

You can find documentation on this checklist [here](https://github.com/RedHatInsights/secure-coding-checklist).

## Secure Coding Checklist

- [ ] Input Validation
- [ ] Output Encoding
- [ ] Authentication and Password Management
- [ ] Session Management
- [ ] Access Control
- [ ] Cryptographic Practices
- [ ] Error Handling and Logging
- [ ] Data Protection
- [ ] Communication Security
- [ ] System Configuration
- [ ] Database Security
- [ ] File Management
- [ ] Memory Management
- [ ] General Coding Practices
