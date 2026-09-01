"""The docker backend, against a real daemon.

Skipped when no daemon is reachable, so a laptop with Docker closed still runs the suite.
That makes the CI job in `.github/workflows/ci.yml` the thing that keeps these honest:
a backend whose tests only ever skip is a backend nobody has tested.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from touchstone.backends import DockerBackend, RunSpec
from touchstone.contracts import ItemRecord
from touchstone.contracts.manifest import Resources
from touchstone.errors import BackendError

PACK = Path(__file__).resolve().parents[1] / "packs" / "example_pack"
IMAGE = "touchstone-example-pack:test"
BASE = "python:3.12-slim"
SYSTEMS = json.dumps({"system_under_test": {"type": "llm_api"}})


def daemon_is_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


pytestmark = pytest.mark.skipif(not daemon_is_up(), reason="no docker daemon")


@pytest.fixture(scope="module")
def image() -> str:
    subprocess.run(
        ["docker", "build", "-q", "-t", IMAGE, str(PACK)], check=True, capture_output=True
    )
    return IMAGE


@pytest.fixture(scope="module", autouse=True)
def base_image() -> None:
    """Put BASE in the local store, because the tests below run it without building it.

    They used to inherit it from the pack build, which is a bet on which builder ran:
    BuildKit keeps the base layers of a build in its own cache and never writes the
    image into the store `docker image inspect` reads, so the bet loses on any runner
    whose docker defaults to it. The inspect guard keeps a machine that already holds
    the image off the network.
    """
    if subprocess.run(["docker", "image", "inspect", BASE], capture_output=True).returncode:
        subprocess.run(["docker", "pull", BASE], check=True, capture_output=True)


@pytest.fixture
def backend() -> DockerBackend:
    return DockerBackend()


def spec(tmp_path: Path, image: str, **overrides) -> RunSpec:
    defaults = {
        "run_id": "example-pack-0",
        "pack_id": "example_pack",
        "image": image,
        "args": ["--systems-params", SYSTEMS, "--test-params", '{"max_items": 10, "seed": 7}'],
        "output_dir": tmp_path / "out",
    }
    return RunSpec(**(defaults | overrides))


def test_runs_a_pack_and_collects_its_records(backend, image, tmp_path):
    result = backend.run(spec(tmp_path, image))
    assert result.exit_code == 0
    assert result.termination is None

    lines = (tmp_path / "out" / "items.jsonl").read_text().splitlines()
    assert len(lines) == 10
    assert all(ItemRecord.model_validate_json(line) for line in lines)


def test_records_the_digest_of_what_actually_ran(backend, image, tmp_path):
    result = backend.run(spec(tmp_path, image))
    assert "sha256:" in result.image_digest
    assert result.backend == "docker"
    assert result.isolation == "container"


def test_a_pack_that_fails_is_a_result_not_an_error(backend, image, tmp_path):
    result = backend.run(
        spec(tmp_path, image, args=["--systems-params", "{}", "--test-params", "{}"])
    )
    assert result.exit_code != 0
    assert result.termination is None


def test_a_timeout_is_labelled_as_one(backend, tmp_path):
    result = backend.run(
        spec(
            tmp_path,
            BASE,
            run_id="touchstone-test-slow",
            args=["python", "-c", "import time; time.sleep(60)"],
            timeout_seconds=3,
        )
    )
    assert result.exit_code == 137
    assert result.termination == "timeout"


REACH = """
import json, sys, urllib.request
out = {}
for name, url in [("declared", "https://example.com"), ("undeclared", "https://api.github.com")]:
    try:
        urllib.request.urlopen(url, timeout=20)
        out[name] = "reached"
    except Exception as exc:
        out[name] = type(exc).__name__
direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    direct.open("https://example.com", timeout=15)
    out["bypass"] = "reached"
except Exception as exc:
    out["bypass"] = type(exc).__name__
open("/output/reach.json", "w").write(json.dumps(out))
"""
"""Three questions asked from inside the container: the host the pack declared, one it did
not, and the declared host again with the proxy variables deliberately ignored."""


def test_a_declared_allowlist_is_enforced_and_cannot_be_bypassed(backend, tmp_path):
    """The whole control, in one run against a real daemon.

    The third answer is the one that matters. A pack is not asked to route through the
    proxy, it is put on a network with no route anywhere else, so a pack that ignores
    HTTPS_PROXY reaches nothing rather than reaching everything.
    """
    result = backend.run(
        spec(
            tmp_path,
            BASE,
            run_id="touchstone-test-egress",
            args=["python", "-c", REACH],
            egress=["example.com"],
        )
    )
    assert result.egress_enforced is True

    reach = json.loads((tmp_path / "out" / "reach.json").read_text())
    assert reach["declared"] == "reached", reach
    assert reach["undeclared"] != "reached", reach
    assert reach["bypass"] != "reached", reach


def test_the_proxy_log_of_what_was_attempted_lands_in_the_output(backend, tmp_path):
    """A denial in here is a finding, not an error. It records that the pack tried."""
    backend.run(
        spec(
            tmp_path,
            BASE,
            run_id="touchstone-test-egress-log",
            args=["python", "-c", REACH],
            egress=["example.com"],
        )
    )
    log = (tmp_path / "out" / "touchstone-test-egress-log.egress.log").read_text()
    assert "example.com" in log
    assert "TCP_DENIED" in log, log


def test_the_proxy_and_its_network_do_not_outlive_the_run(backend, tmp_path):
    run_id = "touchstone-test-egress-teardown"
    backend.run(
        spec(
            tmp_path,
            BASE,
            run_id=run_id,
            args=["python", "-c", "pass"],
            egress=["example.com"],
        )
    )
    left = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True
    )
    assert f"{run_id}-proxy" not in left.stdout
    networks = subprocess.run(
        ["docker", "network", "ls", "--format", "{{.Name}}"], capture_output=True, text=True
    )
    assert f"{run_id}-net" not in networks.stdout


def test_a_declared_host_that_is_not_a_hostname_is_refused(backend, tmp_path):
    """The allowlist is written into a proxy configuration file, so a host carrying a
    newline would append a rule. It is refused rather than escaped."""
    with pytest.raises(BackendError, match="not a hostname"):
        backend.run(
            spec(
                tmp_path,
                BASE,
                egress=["example.com\nhttp_access allow all"],
            )
        )


def test_the_override_grants_the_whole_network_and_says_so(backend, image, tmp_path):
    """Still available, still a downgrade, and still the thing that marks the bundle."""
    result = backend.run(
        spec(tmp_path, image, egress=["api.openai.com"], allow_unenforced_egress=True)
    )
    assert result.egress_enforced is False


def test_a_pack_that_exceeds_its_memory_is_killed_and_named_as_such(backend, tmp_path):
    """Docker reports an out of memory kill as exit 137, and so does a timeout. Recording
    both the same way would put a pack that was too big into the bundle as a pack that was
    too slow, and the remediation for those is not the same."""
    result = backend.run(
        spec(
            tmp_path,
            BASE,
            run_id="touchstone-test-oom",
            args=["python", "-c", "b = bytearray(400 * 1024 * 1024); print(len(b))"],
            timeout_seconds=90,
            resources=Resources(memory_mb=64),
        )
    )
    assert result.exit_code == 137
    assert result.termination == "out_of_memory"
    assert result.termination != "timeout"


def test_a_pack_that_stays_inside_its_memory_is_not_marked(backend, tmp_path):
    result = backend.run(
        spec(
            tmp_path,
            BASE,
            run_id="touchstone-test-within",
            args=["python", "-c", "b = bytearray(8 * 1024 * 1024); print(len(b))"],
            timeout_seconds=90,
            resources=Resources(memory_mb=256),
        )
    )
    assert result.exit_code == 0
    assert result.termination is None


def test_a_pack_cannot_fork_its_way_past_the_process_limit(backend, tmp_path):
    """ASQI caps neither processes nor swap, so a pack that forks in a loop takes the host
    down without ever exceeding its memory limit."""
    forker = (
        "import os\n"
        "n = 0\n"
        "try:\n"
        "    while n < 400:\n"
        "        if os.fork() == 0: os._exit(0)\n"
        "        n += 1\n"
        "except BlockingIOError:\n"
        "    pass\n"
        "open('/output/forks.txt','w').write(str(n))\n"
    )
    backend.run(
        spec(
            tmp_path,
            BASE,
            run_id="touchstone-test-pids",
            args=["python", "-c", forker],
            timeout_seconds=90,
            resources=Resources(memory_mb=256, pids=32),
        )
    )
    forks = int((tmp_path / "out" / "forks.txt").read_text())
    assert forks < 400, "the pack forked as much as it liked"


def test_stdout_is_not_written_unless_asked(backend, image, tmp_path):
    backend.run(spec(tmp_path, image))
    assert list((tmp_path / "out").glob("*.stdout.log")) == []

    backend.run(spec(tmp_path, image, run_id="example-pack-1", capture_stdout=True))
    assert (tmp_path / "out" / "example-pack-1.stdout.log").is_file()


def test_reads_the_manifest_without_running_the_image(backend, image):
    manifest = backend.extract_manifest(image)
    assert manifest.name == "example_pack"
    assert {stratum.name for stratum in manifest.strata} == {"language", "difficulty"}


def test_reports_which_images_are_present(backend, image):
    assert backend.check_images([image, "touchstone/nope:0"]) == {
        image: True,
        "touchstone/nope:0": False,
    }


SLEEPER = ["python", "-c", "import time; time.sleep(300)"]


def container_state(run_id: str) -> str:
    done = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", run_id],
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else "gone"


def wait_for(run_id: str, state: str, seconds: int = 30) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = container_state(run_id)
        if found == state:
            return found
        time.sleep(0.25)
    return container_state(run_id)


def test_shutdown_reaps_the_containers_a_killed_harness_left_behind(tmp_path):
    """The recovery path, against a harness that actually died rather than a simulated one.

    `_run` removes its container in a `finally`, and SIGKILL runs no `finally`. So the
    premise this rests on is real: a harness killed mid-run leaves a container holding the
    memory, the CPU share and the output mount it was given. `shutdown` keys on nothing but
    the run id, which is what a new process recovering from a crash has, and this checks
    that the key is enough.
    """
    run_id = "touchstone-test-crash"
    subprocess.run(["docker", "rm", "--force", run_id], capture_output=True)

    harness = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from touchstone.backends import DockerBackend, RunSpec\n"
            "DockerBackend().run(RunSpec("
            f"run_id={run_id!r}, pack_id='sleeper', image='python:3.12-slim', "
            f"args={SLEEPER!r}, output_dir={str(tmp_path / 'out')!r}))",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert wait_for(run_id, "running") == "running", "the container never started"

        harness.kill()
        harness.wait(timeout=30)

        assert container_state(run_id) == "running", (
            "the premise: a killed harness runs no cleanup, so the container outlives it"
        )

        DockerBackend().shutdown([run_id])

        assert container_state(run_id) == "gone"
    finally:
        harness.kill()
        subprocess.run(["docker", "rm", "--force", run_id], capture_output=True)


def test_shutdown_is_quiet_about_a_container_that_is_already_gone():
    """Recovery is run against the ids the ledger holds, and some of them finished cleanly
    before the crash. Raising on those would make the recovery path fail on a healthy run."""
    DockerBackend().shutdown(["touchstone-test-never-existed"])
