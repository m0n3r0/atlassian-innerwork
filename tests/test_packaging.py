import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def test_installed_wheel_loads_packaged_catalog_resources():
    uv = shutil.which("uv")
    assert uv is not None, "uv must be installed to run packaging smoke test"
    with tempfile.TemporaryDirectory() as temp_dir:
        wheelhouse = Path(temp_dir) / "wheelhouse"
        target = Path(temp_dir) / "target"
        subprocess.run(
            [uv, "build", "--wheel", "--out-dir", str(wheelhouse)],
            check=True,
            capture_output=True,
            text=True,
        )
        wheel = next(wheelhouse.glob("atlassian_innerwork-*.whl"))
        subprocess.run(
            [uv, "pip", "install", str(wheel), "--target", str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(target)
        code = (
            "from innerwork.catalog import broker_catalog; "
            "print(broker_catalog()['services'][0]['id'])"
        )
        probe = subprocess.run(
            [sys.executable, "-c", code],
            check=False,
            cwd=temp_dir,
            env=environment,
            capture_output=True,
            text=True,
        )

    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "innerwork-edge-service"
