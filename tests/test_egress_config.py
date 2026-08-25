"""The proxy configuration, checked without a daemon.

`tests/test_docker_backend.py` proves the control works and needs Docker, so it is gated
and CI is what keeps it honest. These are the parts that must never go untested on a
laptop with Docker closed: the allowlist comes out of a pack's manifest, and it is written
into a configuration file that decides what that pack can reach.
"""

import pytest

from touchstone.backends.egress import (
    PROXY_PORT,
    check_hosts,
    proxy_env,
    squid_config,
    start_command,
)


@pytest.mark.parametrize(
    "host",
    [
        "example.com\nhttp_access allow all",
        "example.com\rhttp_access allow all",
        "example.com http_access allow all",
        "https://api.openai.com",
        "api.openai.com:443",
        "api.openai.com/v1",
        "*.openai.com",
        ".openai.com",
        "",
        "localhost",
        "1.2.3.4",
        "127.0.0.1",
    ],
)
def test_a_host_that_is_not_a_hostname_is_refused(host):
    assert check_hosts([host]) == [host]
    with pytest.raises(ValueError):
        squid_config([host])


def test_the_injection_that_motivates_the_check():
    """A pack is the thing being contained, and it writes its own manifest. Without this
    the allowlist would be a suggestion the pack could edit."""
    with pytest.raises(ValueError):
        squid_config(["api.openai.com", "evil.com\nhttp_access allow all"])


@pytest.mark.parametrize(
    "host", ["api.openai.com", "API.OpenAI.com", "a.b.c.example.co.uk", "x1-y2.example.com"]
)
def test_a_real_hostname_is_accepted(host):
    assert check_hosts([host]) == []


def test_the_name_is_normalised_rather_than_the_author_corrected():
    """DNS is case insensitive and squid's acl is not."""
    assert "acl declared dstdomain api.openai.com" in squid_config(["API.OpenAI.com"])


def test_the_configuration_denies_by_default():
    config = squid_config(["api.openai.com"])
    assert config.strip().endswith("access_log stdio:/var/log/squid/access.log")
    assert "http_access deny all" in config
    assert config.index("http_access allow declared") < config.index("http_access deny all"), (
        "an allow after the final deny would be unreachable, and one before it is the only "
        "thing that grants anything"
    )


def test_only_the_declared_hosts_appear():
    config = squid_config(["api.openai.com", "api.anthropic.com"])
    declared = [line for line in config.splitlines() if line.startswith("acl declared")]
    assert declared == [
        "acl declared dstdomain api.openai.com",
        "acl declared dstdomain api.anthropic.com",
    ]


def test_a_subdomain_is_not_included_by_declaring_its_parent():
    """`dstdomain example.com` matches that host alone. A leading dot is what widens it,
    and a leading dot is refused, so a pack that needs a subdomain declares it."""
    assert "dstdomain example.com" in squid_config(["example.com"])
    assert ".example.com" not in squid_config(["example.com"])


def test_connect_is_confined_to_443():
    config = squid_config(["api.openai.com"])
    assert "http_access deny CONNECT !SSL_ports" in config
    assert "acl SSL_ports port 443" in config


def test_the_pack_is_told_in_every_spelling_a_client_reads():
    env = proxy_env()
    assert {"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"} <= set(env)
    assert all(str(PROXY_PORT) in value for value in env.values() if value)
    assert env["NO_PROXY"] == "", "a populated NO_PROXY would be a hole in the courtesy"


def test_the_config_is_quoted_into_the_start_command():
    """The configuration reaches the container through a shell, so it is quoted once and
    the quoting is what stops a hostile hostname reaching the shell. The host check is the
    first line of that defence and this is the second."""
    command = start_command(squid_config(["api.openai.com"]))
    assert command.startswith("printf %s '")
    assert "exec /usr/local/bin/entrypoint.sh" in command
