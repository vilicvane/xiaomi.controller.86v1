"""Read-only independent checks of existing hook evidence and recorder API.

No adapter, device connection, or report writing. Adverse-evidence expansion
was stopped by root after the complete hardware experiment passed.
"""
from pathlib import Path
import importlib.util
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "analysis/persistence/hook-install-hardware-20261004-153157"

def independent_captured_bytes():
    stages = list(CAPTURE.glob("*/result.txt"))
    assert len(stages) == 29
    for path in stages:
        stage = path.parent
        original = (stage / "scratch-original.bin").read_bytes()
        restored = (stage / "scratch-restored.bin").read_bytes()
        assert len(original) == len(restored) == 1024 and original == restored
        before = (stage / "boot-initialized-config-before.bin").read_bytes()
        after = (stage / "boot-initialized-config-after.bin").read_bytes()
        assert len(before) == len(after) == 8 and before == after
        assert "context_restore_complete 1 test_error 0 cleanup_error 0" in path.read_text()
    for label, offset in [("entry", "150000"), ("payload", "824000")]:
        for phase, state in [("before", "original"), ("verified", "patched")]:
            data = (CAPTURE / f"sector-{label}-{phase}.bin").read_bytes()
            assert len(data) == 4096
            assert data == (ROOT / f"analysis/persistence/boot-hook-{state}-sector-{offset}.bin").read_bytes()

def main():
    independent_captured_bytes()
    path = ROOT / "analysis/persistence/record_boot_hook_hardware.py"
    spec = importlib.util.spec_from_file_location("offline_hook_record_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    installed = module.inspect_capture(str(CAPTURE), "install", str(ROOT / "diagnostics/mcu-boot-hook-install-result.txt"))
    assert installed["status"] == "passed", installed.get("reason")
    assert installed["native_call_count"] == 29
    restored = module.inspect_capture(str(ROOT / "analysis/persistence/hook-restore-hardware-20261004-153535"),
                                      "restore", str(ROOT / "diagnostics/mcu-boot-hook-restore-result.txt"))
    assert restored["status"] == "passed", restored.get("reason")
    assert restored["native_call_count"] == 33
    warm = module.inspect_marker(str(ROOT / "diagnostics/boot-hook-marker-warm.txt"), "patched")
    assert warm["status"] == "passed", warm.get("reason")
    cold = module.inspect_marker(str(ROOT / "diagnostics/boot-hook-marker-cold.txt"), "patched", cold_confirmed=True, cold=True)
    assert cold["status"] == "passed", cold.get("reason")
    assert module.inspect_marker(None, "patched", cold=True)["status"] == "pending"
    assert module.inspect_marker(str(ROOT / "diagnostics/boot-hook-marker-cold.txt"), "patched", cold=True)["status"] == "pending"
    assert module.inspect_capture(None, "restore", None)["status"] == "pending"
    print("READ_ONLY_PASS install29/restore33/warm/cold; missing cold/user-provenance/restore stays pending; no target or report writes")

if __name__ == "__main__":
    main()
