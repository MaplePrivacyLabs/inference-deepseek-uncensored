# syntax=docker/dockerfile:1.6
# Retain Tinfoil's qualified B300 runtime, CC transfers, kernels and entrypoint.
# The only runtime source delta is the two guarded model-name constants.
FROM ghcr.io/tinfoilsh/confidential-deepseek-v4-1-flash@sha256:01dae35f82bd4fb13376a9d1f0330e4109c1c03a07532f8df3bb12f9b0e58880

COPY scripts/patch_model_identity.py /tmp/patch_model_identity.py
RUN python3 -B /tmp/patch_model_identity.py && rm /tmp/patch_model_identity.py
