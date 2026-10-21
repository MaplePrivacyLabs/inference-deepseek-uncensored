"""Rename two pinned Tinfoil CC optimization guards at image build time.

No transport, inference, or safety predicate is otherwise changed. The complete
before/after hashes pin the expected source and fail the build on any drift.
"""

import ast
import hashlib
from importlib.metadata import version
import os
from pathlib import Path


BASE_VLLM_VERSION = "0.31.0"
BASE_VLLM_COMMIT = "db9527a46873454610df6dbedf79a36d6bf1a7f6"
OLD_MODEL_NAME = "deepseek-v4-1-flash"
MODEL_NAME = "deepseek-v4-1-flash-1017-uncensored"
MODULE_ROOT = Path("usr/local/lib/python3.12/dist-packages/vllm/v1/worker/gpu")
# Source: tinfoilsh/confidential-deepseek-v4-1-flash at
# 28775a51ed83ddd1cd295852db46499d7d50c480, patches 0005/0007 followed by 0011.
MODULE_HASHES = {
    "cc_readback.py": (
        "f9d219d6f6f0160b92fe6fa728a643de4b5d9a1bdc5de7f73c09a3d9b76d7b75",
        "8f0e91871bc457d3216f4b5c113a197ec67d52de484cf1d821377b1445f8b7e6",
    ),
    "cc_input_staging.py": (
        "74050440c95f894a0c8b235f769a9c05ee0651df5d3cd034e1c0fffe143e36b4",
        "226a659d65c20a4631d821cafb4becefd8b3100ec8512501a1ee2b9a1f28e331",
    ),
}


class IdentityPatchError(ValueError):
    """The base runtime is different from the source qualified for this patch."""


def validate_runtime(vllm_version: str, build_commit: str | None) -> None:
    if vllm_version != BASE_VLLM_VERSION or build_commit != BASE_VLLM_COMMIT:
        raise IdentityPatchError("Unexpected vLLM version/build commit; refusing patch")


def _model_assignment(tree: ast.Module) -> ast.Assign:
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_MODEL_NAME"
                for target in node.targets)
    ]
    if len(assignments) != 1:
        raise IdentityPatchError("Expected exactly one _MODEL_NAME assignment")
    return assignments[0]


def patched_source(name: str, source: bytes) -> bytes:
    if name not in MODULE_HASHES:
        raise IdentityPatchError(f"Unexpected module: {name}")
    before_hash, after_hash = MODULE_HASHES[name]
    if hashlib.sha256(source).hexdigest() != before_hash:
        raise IdentityPatchError(f"Unexpected original source hash: {name}")
    original_tree = ast.parse(source, filename=name)
    assignment = _model_assignment(original_tree)
    if not isinstance(assignment.value, ast.Constant) or assignment.value.value != OLD_MODEL_NAME:
        raise IdentityPatchError(f"Unexpected original model identity: {name}")
    old = f'_MODEL_NAME = "{OLD_MODEL_NAME}"'.encode()
    new = f'_MODEL_NAME = "{MODEL_NAME}"'.encode()
    if source.count(old) != 1:
        raise IdentityPatchError(f"Expected exactly one model-name replacement: {name}")
    result = source.replace(old, new, 1)
    if hashlib.sha256(result).hexdigest() != after_hash:
        raise IdentityPatchError(f"Unexpected patched source hash: {name}")
    result_tree = ast.parse(result, filename=name)
    # Normalize only that constant to prove the rest of the module is identical.
    _model_assignment(result_tree).value.value = OLD_MODEL_NAME
    if ast.dump(original_tree) != ast.dump(result_tree):
        raise IdentityPatchError(f"Unexpected source change beyond model identity: {name}")
    compile(result, name, "exec")
    return result


def apply_identity_patch(root: Path) -> None:
    directory = root / MODULE_ROOT
    # Validate both inputs before mutating either module.
    updates = {
        directory / name: patched_source(name, (directory / name).read_bytes())
        for name in MODULE_HASHES
    }
    for path, content in updates.items():
        path.write_bytes(content)
        # Do not leave cached code containing the original constant in the image.
        for cache in (path.parent / "__pycache__").glob(f"{path.stem}.*.pyc"):
            cache.unlink()
    for path, content in updates.items():
        if path.read_bytes() != content:
            raise IdentityPatchError(f"Patched module verification failed: {path.name}")


def main() -> None:
    validate_runtime(version("vllm"), os.environ.get("VLLM_BUILD_COMMIT"))
    apply_identity_patch(Path("/"))
    print(f"Verified two Tinfoil CC guards now serve {MODEL_NAME}")


if __name__ == "__main__":
    main()
