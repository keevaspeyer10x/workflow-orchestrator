
from src.healing.applicator import FixApplicator
from unittest.mock import MagicMock

# Mock dependencies
git = MagicMock()
storage = MagicMock()
execution = MagicMock()

applicator = FixApplicator(git, storage, execution)

# Test malicious command
malicious_command = "pip install requests; echo 'Vulnerable!'"
is_allowed = applicator._is_command_allowed(malicious_command)

print(f"Command: {malicious_command}")
print(f"Is allowed: {is_allowed}")

if is_allowed:
    print("VULNERABILITY CONFIRMED: Suffix injection is possible.")
else:
    print("Safe: Command was rejected.")
