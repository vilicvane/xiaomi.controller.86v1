"""Download only three small public HAL files; no device access."""
from pathlib import Path
import hashlib
import json
import urllib.request

base = "https://raw.githubusercontent.com/openharmony/device_soc_bestechnic/master/bes2600/liteos_m/sdk/bsp/platform/hal/"
out = Path(__file__).resolve().parent / "reference"
sources = []
for relative in ("hal_wdt.c", "best2003/hal_cmu_best2003.c", "best2003/reg_cmu_best2003.h"):
    url = base + relative
    data = urllib.request.urlopen(url, timeout=20).read(300_001)
    if len(data) > 300_000:
        raise ValueError("Unexpected source size; refusing larger download")
    target = out / Path(relative).name
    if target.exists() and target.read_bytes() != data:
        raise ValueError("Existing reference differs; refusing overwrite")
    target.write_bytes(data)
    sources.append({"url": url, "local": str(target.relative_to(Path(__file__).resolve().parents[2])),
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
(out / "watchdog-source-manifest.json").write_text(json.dumps(sources, indent=2) + "\n")
print(f"Public small watchdog/CMU references saved: {len(sources)}")
