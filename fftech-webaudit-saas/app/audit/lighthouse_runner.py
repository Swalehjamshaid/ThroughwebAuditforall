import json
import subprocess
import tempfile

def run_lighthouse(url: str) -> dict:
    # Requires Node.js and lighthouse (installed in Dockerfile)
    # Generates a JSON report
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        out_path = tmp.name
    cmd = [
        'lighthouse', url,
        '--quiet', '--chrome-flags=--headless', '--output=json', f'--output-path={out_path}'
    ]
    subprocess.run(cmd, check=True)
    with open(out_path, 'r') as f:
        data = json.load(f)
    return data
