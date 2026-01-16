"""Tests for SubprocessDetector - Phase 1 Detection & Fingerprinting."""

import pytest


class TestSubprocessDetector:
    """Tests for detecting errors from subprocess output."""

    def test_detect_success_no_errors(self):
        """Exit code 0 returns empty list."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        errors = detector.detect(
            exit_code=0, stdout="Success!", stderr="", command="echo hello"
        )

        assert len(errors) == 0

    def test_detect_python_error(self):
        """Parses Python error from stderr."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = """Traceback (most recent call last):
  File "main.py", line 10, in <module>
    result = process(data)
TypeError: 'NoneType' object is not subscriptable"""

        errors = detector.detect(
            exit_code=1, stdout="", stderr=stderr, command="python main.py"
        )

        assert len(errors) == 1
        assert errors[0].error_type == "TypeError"
        assert errors[0].fingerprint is not None

    def test_detect_python_traceback(self):
        """Extracts stack trace."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = """Traceback (most recent call last):
  File "/home/user/app.py", line 42, in main
    do_something()
ValueError: invalid literal"""

        errors = detector.detect(
            exit_code=1, stdout="", stderr=stderr, command="python app.py"
        )

        assert len(errors) == 1
        assert errors[0].stack_trace is not None
        assert "Traceback" in errors[0].stack_trace

    def test_detect_pytest_failure(self):
        """Parses pytest failure output."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = """FAILED tests/test_main.py::test_feature - AssertionError
FAILED tests/test_utils.py::test_helper - TypeError"""

        errors = detector.detect(
            exit_code=1, stdout="", stderr=stderr, command="pytest tests/"
        )

        assert len(errors) >= 1  # At least one error detected

    def test_detect_rust_error(self):
        """Parses Rust compiler error."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = """error[E0382]: borrow of moved value: `x`
 --> src/main.rs:5:20
  |
4 |     let y = x;
  |             - value moved here
5 |     println!("{}", x);
  |                    ^ value borrowed here after move"""

        errors = detector.detect(
            exit_code=1, stdout="", stderr=stderr, command="cargo build"
        )

        assert len(errors) == 1
        assert "E0382" in errors[0].description or "E0382" in (
            errors[0].error_type or ""
        )

    def test_detect_go_panic(self):
        """Parses Go panic."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = """panic: runtime error: index out of range [5] with length 3

goroutine 1 [running]:
main.main()
    /home/user/main.go:10 +0x45"""

        errors = detector.detect(
            exit_code=2, stdout="", stderr=stderr, command="go run main.go"
        )

        assert len(errors) == 1
        assert "panic" in errors[0].description.lower()

    def test_detect_node_error(self):
        """Parses Node.js error."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = """Error: Cannot find module 'express'
    at Function.Module._resolveFilename (internal/modules/cjs/loader.js:815:15)
    at Object.<anonymous> (/home/user/app.js:1:17)"""

        errors = detector.detect(
            exit_code=1, stdout="", stderr=stderr, command="node app.js"
        )

        assert len(errors) == 1
        assert "Cannot find module" in errors[0].description

    def test_detect_unknown_error(self):
        """Returns generic error for unrecognized patterns."""
        from src.healing.detectors.subprocess import SubprocessDetector
        from src.healing.fingerprint import Fingerprinter

        fp = Fingerprinter()
        detector = SubprocessDetector(fp)

        stderr = "Something went wrong"

        errors = detector.detect(
            exit_code=1, stdout="", stderr=stderr, command="./unknown_command"
        )

        assert len(errors) == 1
        assert errors[0].description == stderr or "Something went wrong" in errors[0].description
