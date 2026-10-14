# Contributing

Thanks for helping improve StreamPort. Please use the MIT license terms in `LICENSE` for contributions. Keep changes focused, document user-visible configuration changes and add tests for bug fixes where feasible.

Before opening a pull request, run the relevant tests described in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md). In particular, check that no API keys, database files, personal filesystem paths, private network addresses, media titles/listings from your own library, Android signing material or binary release artifacts are staged. Keep bug reports reproducible with **sanitized** logs and examples.

For a possible security vulnerability, use private reporting rather than publishing exploit details or secrets in an issue. This is a community project; API/third-party service integrations should respect their official terms and must not introduce media acquisition or credential-sharing features.
