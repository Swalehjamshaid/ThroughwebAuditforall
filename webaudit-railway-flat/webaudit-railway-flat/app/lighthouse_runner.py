
import json
import os
import subprocess
import tempfile

def run_lighthouse(url: str, form_factor: str = "desktop", categories=None, timeout_sec=120):
    if categories is None:
        categories = ["performance", "accessibility", "best-practices", "seo", "pwa"]

    cmd = ["lighthouse", url, "--output=json", "--quiet"]
    if form_factor == "desktop":
        cmd += ["--preset=desktop"]
    for cat in categories:
        cmd += ["--only-categories", cat]

    out_json = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    cmd += ["--output-path", out_json.name]
    try:
        subprocess.run(cmd, check=True, timeout=timeout_sec)
        with open(out_json.name, "r", encoding="utf-8") as f:
            lhr = json.load(f)
        return lhr
    finally:
        try:
            os.unlink(out_json.name)
        except Exception:
            pass
