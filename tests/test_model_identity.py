import ast
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import patch_model_identity as identity


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / f"{name}.txt").read_bytes()


class SourceIdentityTests(unittest.TestCase):
    def test_source_fixtures_match_both_pinned_hashes(self):
        for name, (before_hash, _) in identity.MODULE_HASHES.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(fixture(name)).hexdigest(), before_hash)

    def test_each_output_has_expected_hash_and_one_line_delta(self):
        for name, (_, expected_hash) in identity.MODULE_HASHES.items():
            with self.subTest(name=name):
                original = fixture(name)
                result = identity.patched_source(name, original)
                self.assertEqual(hashlib.sha256(result).hexdigest(), expected_hash)
                self.assertEqual(
                    result,
                    original.replace(
                        f'_MODEL_NAME = "{identity.OLD_MODEL_NAME}"'.encode(),
                        f'_MODEL_NAME = "{identity.MODEL_NAME}"'.encode(),
                        1,
                    ),
                )
                self.assertNotIn(f'_MODEL_NAME = "{identity.OLD_MODEL_NAME}"'.encode(), result)
                self.assertEqual(result.count(f'_MODEL_NAME = "{identity.MODEL_NAME}"'.encode()), 1)

    def test_only_ast_identity_constant_changes(self):
        for name in identity.MODULE_HASHES:
            with self.subTest(name=name):
                original = ast.parse(fixture(name))
                result = ast.parse(identity.patched_source(name, fixture(name)))
                assignment = identity._model_assignment(result)
                self.assertEqual(assignment.value.value, identity.MODEL_NAME)
                assignment.value.value = identity.OLD_MODEL_NAME
                self.assertEqual(ast.dump(result), ast.dump(original))

    def test_patched_source_compiles_without_importing_gpu_dependencies(self):
        for name in identity.MODULE_HASHES:
            with self.subTest(name=name):
                compile(identity.patched_source(name, fixture(name)), name, "exec")

    def test_all_other_configuration_and_cc_guards_are_preserved(self):
        # Compare every conditional expression, not a hand-written imitation of
        # the qualification logic; the renamed assignment is outside the guards.
        for name in identity.MODULE_HASHES:
            with self.subTest(name=name):
                original = ast.parse(fixture(name))
                result = ast.parse(identity.patched_source(name, fixture(name)))
                before = [ast.dump(node) for node in ast.walk(original)
                          if isinstance(node, (ast.Compare, ast.BoolOp))]
                after = [ast.dump(node) for node in ast.walk(result)
                         if isinstance(node, (ast.Compare, ast.BoolOp))]
                self.assertEqual(before, after)
                self.assertIn("runner.model_config.served_model_name == _MODEL_NAME",
                              fixture(name).decode())

    def test_rejects_unexpected_module(self):
        with self.assertRaisesRegex(identity.IdentityPatchError, "Unexpected module"):
            identity.patched_source("model_runner.py", b"pass\n")

    def test_rejects_drift_in_other_guard(self):
        for name in identity.MODULE_HASHES:
            with self.subTest(name=name):
                changed = fixture(name).replace(b"_MAX_REQUESTS = 64", b"_MAX_REQUESTS = 65")
                with self.assertRaisesRegex(identity.IdentityPatchError, "original source hash"):
                    identity.patched_source(name, changed)

    def test_rejects_duplicate_identity_assignment(self):
        for name in identity.MODULE_HASHES:
            with self.subTest(name=name):
                changed = fixture(name) + b'\n_MODEL_NAME = "deepseek-v4-1-flash"\n'
                with self.assertRaises(identity.IdentityPatchError):
                    identity.patched_source(name, changed)

    def test_ast_validation_rejects_duplicate_or_missing_assignment(self):
        for source in ("pass", '_MODEL_NAME = "a"\n_MODEL_NAME = "b"'):
            with self.subTest(source=source):
                with self.assertRaisesRegex(identity.IdentityPatchError, "exactly one"):
                    identity._model_assignment(ast.parse(source))

    def test_rejects_missing_identity(self):
        name = "cc_readback.py"
        changed = fixture(name).replace(b'_MODEL_NAME = "deepseek-v4-1-flash"', b'_MODEL_NAME = "other"')
        with self.assertRaises(identity.IdentityPatchError):
            identity.patched_source(name, changed)

    def test_rejects_already_patched_source(self):
        for name in identity.MODULE_HASHES:
            with self.subTest(name=name):
                patched = identity.patched_source(name, fixture(name))
                with self.assertRaisesRegex(identity.IdentityPatchError, "original source hash"):
                    identity.patched_source(name, patched)

    def test_rejects_unexpected_result_hash(self):
        name = "cc_readback.py"
        before_hash, _ = identity.MODULE_HASHES[name]
        with patch.dict(identity.MODULE_HASHES, {name: (before_hash, "0" * 64)}):
            with self.assertRaisesRegex(identity.IdentityPatchError, "patched source hash"):
                identity.patched_source(name, fixture(name))


class RuntimeIdentityTests(unittest.TestCase):
    def test_accepts_exact_runtime_only(self):
        identity.validate_runtime(identity.BASE_VLLM_VERSION, identity.BASE_VLLM_COMMIT)

    def test_rejects_wrong_runtime_version_or_commit(self):
        for version, commit in (("0.32.0", identity.BASE_VLLM_COMMIT),
                                (identity.BASE_VLLM_VERSION, "different"),
                                (identity.BASE_VLLM_VERSION, None)):
            with self.subTest(version=version, commit=commit):
                with self.assertRaises(identity.IdentityPatchError):
                    identity.validate_runtime(version, commit)


class FilesystemPatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.modules = self.root / identity.MODULE_ROOT
        self.modules.mkdir(parents=True)
        for name in identity.MODULE_HASHES:
            (self.modules / name).write_bytes(fixture(name))

    def test_patches_both_modules_and_removes_only_their_cached_code(self):
        caches = self.modules / "__pycache__"
        caches.mkdir()
        for name in identity.MODULE_HASHES:
            (caches / f"{Path(name).stem}.cpython-312.pyc").write_bytes(b"old code")
        unrelated = caches / "model_runner.cpython-312.pyc"
        unrelated.write_bytes(b"leave alone")
        marker = self.modules / "unrelated.py"
        marker.write_bytes(b"pass\n")
        identity.apply_identity_patch(self.root)
        for name in identity.MODULE_HASHES:
            self.assertEqual((self.modules / name).read_bytes(),
                             identity.patched_source(name, fixture(name)))
            self.assertFalse(list(caches.glob(f"{Path(name).stem}.*.pyc")))
        self.assertEqual(unrelated.read_bytes(), b"leave alone")
        self.assertEqual(marker.read_bytes(), b"pass\n")

    def test_bad_second_module_does_not_partially_patch_first(self):
        (self.modules / "cc_input_staging.py").write_bytes(b"unexpected\n")
        with self.assertRaises(identity.IdentityPatchError):
            identity.apply_identity_patch(self.root)
        self.assertEqual((self.modules / "cc_readback.py").read_bytes(), fixture("cc_readback.py"))

    def test_missing_second_module_does_not_partially_patch_first(self):
        (self.modules / "cc_input_staging.py").unlink()
        with self.assertRaises(FileNotFoundError):
            identity.apply_identity_patch(self.root)
        self.assertEqual((self.modules / "cc_readback.py").read_bytes(), fixture("cc_readback.py"))

    def test_rejects_second_application(self):
        identity.apply_identity_patch(self.root)
        with self.assertRaises(identity.IdentityPatchError):
            identity.apply_identity_patch(self.root)


class DockerContractTests(unittest.TestCase):
    def test_exact_base_digest_and_inherited_entrypoint(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        instructions = [line.strip() for line in dockerfile.splitlines()
                        if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(instructions[0],
                         "FROM ghcr.io/tinfoilsh/confidential-deepseek-v4-1-flash@"
                         "sha256:01dae35f82bd4fb13376a9d1f0330e4109c1c03a07532f8df3bb12f9b0e58880")
        self.assertEqual([line.split()[0] for line in instructions], ["FROM", "COPY", "RUN"])
        self.assertIn("python3 -B /tmp/patch_model_identity.py", instructions[-1])


if __name__ == "__main__":
    unittest.main()
