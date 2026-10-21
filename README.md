# DeepSeek V4.1 Flash 1017 uncensored

Source preparation for a separately released confidential container serving
[`dealignai/DeepSeek-V4.1-Flash-1017-UNCENSORED-FP8`](https://huggingface.co/dealignai/DeepSeek-V4.1-Flash-1017-UNCENSORED-FP8)
as **`deepseek-v4-1-flash-1017-uncensored`**. This repository does not alter the
stock [Maple DeepSeek configuration](https://github.com/MaplePrivacyLabs/inference-deepseek).

The image derives from Tinfoil's digest-pinned **v0.0.6+b300** runtime. It retains
the vLLM 0.31.0 runtime, offline FlashInfer artifacts, sidecar, and tuned TP4
recipe. A bounded source patch changes the optimized paths' model-identity
checks to the distinct uncensored ID. The public API and engine use the same
ID; consumers need no stock-model alias or special response rewriting.
This change preserves eligibility for those optimizations; runtime performance
and model quality still require qualification on actual hardware.

## Pinned inputs

- Runtime: `ghcr.io/tinfoilsh/confidential-deepseek-v4-1-flash@sha256:01dae35f82bd4fb13376a9d1f0330e4109c1c03a07532f8df3bb12f9b0e58880`.
- Weights: Dealign revision `c19ca5ca4eaeb79d29fdf08aea8327da95b1116a`.
- Model pack: schema 2, verity root `b4afadcff93f3790600e196b1565a0bde218f51e34d7a064c064a7bfd87ca8bf`.
- Starting recipe: four B300 GPUs, TP4, 1M-token context, GPU-resident Engram,
  FP8 MLA KV cache, 64 maximum sequences, static five-token DSpark.

The weights are not copied into this repository or the Docker image. The
configuration identifies their verified model pack separately.
`VLLM_API_KEY` and `METRICS_API_KEY` are deployment-provided secrets; their
values must never be committed. Application authentication is provided by
vLLM and the sidecar; `shim.authenticated: false` avoids shared-inference key
validation. The shim forwards only the explicitly listed API/health paths.

## Validate source

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
docker build --platform linux/amd64 -t deepseek-uncensored:local .
```

These checks validate the bounded identity patch and image build. They do not
load the checkpoint or establish GPU/attestation/inference readiness.
Pull requests and pushes to `main` run these checks without publishing an
image or release.

## Release

**The source `tinfoil-config.yml` is a template, not a deployed or measured
release.** Its `:build-required` image placeholder is replaced only after a
successful image build. Deploy the config from a published, verified release
tag rather than from `main`.

Run **Tinfoil Release** manually from the reviewed source branch, supplying a
canonical version such as `v0.1.0-rc.1`. The standard Tinfoil two-phase workflow:

1. Tests and builds the AMD64 image, then publishes its distinct package at
   `ghcr.io/mapleprivacylabs/inference-deepseek-uncensored`.
2. Pins the returned image digest into `tinfoil-config.yml` on a release-only
   commit and creates an immutable tag such as `v0.1.0-rc.1+b300`.
   It leaves the source branch unchanged.
3. Dispatches the publish workflow on that tag to measure the config, publish
   its GitHub attestation, and attach `tinfoil-deployment.json` and
   `tinfoil.hash` to the release. Release candidates are marked prerelease.

Publishing does not deploy a container or promote GitHub's latest release.
Do not run the publish workflow on a source branch. Existing release tags
cannot be reused; issue a new version for changes.

**First package publication:** ensure the repository and resulting GHCR package
are public. New GHCR packages may initially be private even when their source
repository is public. Set the package visibility explicitly and verify an
anonymous pull of its exact digest before deploying. Public source, releases
and attestations also support Tinfoil's normal verification/freshness path.

Workflows use only the standard repository `GITHUB_TOKEN`, with job-scoped
contents/packages/actions/OIDC/attestation permissions. No private registry or
model-download credential is required for the pinned public inputs. An image
build and measured release still need separate hardware qualification before
production use.
