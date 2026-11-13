# UMI LAB self-hosted Draco decoder

This directory is populated by the Ubuntu installer **before** the release is activated.
The installer downloads the three matching Apache-2.0-licensed Draco 1.5.6 glTF decoder assets:
`draco_decoder.js`, `draco_decoder.wasm`, and `draco_wasm_wrapper.js`.
The browser never needs an external decoder URL. The installer validates the WASM
magic bytes and wrapper sizes, and refuses activation if deployment cannot supply
a complete local decoder set. Existing releases remain active on failure.

Official project: https://github.com/google/draco (Apache License 2.0).
