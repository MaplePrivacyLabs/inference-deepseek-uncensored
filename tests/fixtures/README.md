# Pinned runtime source fixtures

These two text fixtures reconstruct only the modules whose guarded model identity
this repository changes. They are not imported or executed during unit tests.

Source: [`tinfoilsh/confidential-deepseek-v4-1-flash`, commit
`28775a51ed83ddd1cd295852db46499d7d50c480`](https://github.com/tinfoilsh/confidential-deepseek-v4-1-flash/tree/28775a51ed83ddd1cd295852db46499d7d50c480).

- `cc_readback.py.txt`: added by patch `0005-dspark-reply-readback.patch`, then
  modified by `0011-static-verification-transfers.patch`.
- `cc_input_staging.py.txt`: added by `0007-dspark-text-input-staging.patch`, then
  modified by `0011-static-verification-transfers.patch`.

Both retain their upstream SPDX Apache-2.0 copyright/license headers. Copyright
contributors to the vLLM project. Licensed under the [Apache License,
Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).

These are source-derived expectations. The Docker build independently verifies
that the actual pinned base image contains exactly this source before patching.
An offline unit-test pass does not prove the base image contents, a successful
container build, GPU performance, attestation, or a live deployment.
