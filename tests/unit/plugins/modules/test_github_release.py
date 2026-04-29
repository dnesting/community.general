# Copyright (c) Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from ansible_collections.community.internal_test_tools.tests.unit.plugins.modules.utils import (
    AnsibleExitJson,
    AnsibleFailJson,
    exit_json,
    fail_json,
    set_module_args,
)

from ansible_collections.community.general.plugins.modules import github_release


def make_fetch_url_response(body, status=200, extra_info=None):
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode("utf-8")
    info = {"status": status, "msg": f"HTTP {status}"}
    if extra_info:
        info.update(extra_info)
    return (response, info)


@pytest.fixture(autouse=True)
def patch_module():
    with patch.multiple(
        "ansible.module_utils.basic.AnsibleModule",
        exit_json=exit_json,
        fail_json=fail_json,
    ):
        yield


@pytest.fixture
def fetch_url_mock():
    with patch.object(github_release, "fetch_url") as mock:
        yield mock


def test_latest_release_returns_tag(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"tag_name": "v1.2.3"}, status=200)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert result["tag"] == "v1.2.3"
    assert result.get("changed") is not True


def test_latest_release_includes_api_version_header(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"tag_name": "v1.0.0"}, status=200)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleExitJson):
            github_release.main()

    headers = fetch_url_mock.call_args[1]["headers"]
    assert headers.get("X-GitHub-Api-Version") == "2026-03-10"


def test_latest_release_with_token(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"tag_name": "v2.0.0"}, status=200)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
            "token": "ghp_testtoken",
        }
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert result["tag"] == "v2.0.0"

    # Verify the Authorization header was set
    headers = fetch_url_mock.call_args[1]["headers"]
    assert headers["Authorization"] == "token ghp_testtoken"


def test_latest_release_no_releases_returns_null(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"message": "Not Found"}, status=404)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleExitJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert result["tag"] is None


def test_latest_release_rate_limit_403_with_header(fetch_url_mock):
    """403 + x-ratelimit-remaining=0 is a rate limit error."""
    reset_ts = str(int(time.time()) + 120)
    fetch_url_mock.return_value = make_fetch_url_response(
        {"message": "API rate limit exceeded"},
        status=403,
        extra_info={"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset_ts, "x-ratelimit-limit": "60"},
    )

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleFailJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert "rate limit" in result["msg"].lower()
    assert "resets in" in result["details"]
    # No token → hint about tokens should appear
    assert "token" in result["details"].lower()


def test_latest_release_rate_limit_429(fetch_url_mock):
    """HTTP 429 is always a rate limit error."""
    fetch_url_mock.return_value = make_fetch_url_response(
        {"message": "Too Many Requests"},
        status=429,
        extra_info={"x-ratelimit-remaining": "0", "x-ratelimit-limit": "60"},
    )

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
            "token": "ghp_testtoken",
        }
    ):
        with pytest.raises(AnsibleFailJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert "rate limit" in result["msg"].lower()
    # Token provided → no token hint
    assert "authenticating with a github token" not in result["details"].lower()


def test_latest_release_403_not_rate_limit(fetch_url_mock):
    """403 without x-ratelimit-remaining=0 is a plain access error."""
    fetch_url_mock.return_value = make_fetch_url_response(
        {"message": "Forbidden"},
        status=403,
        extra_info={"x-ratelimit-remaining": "59"},
    )

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleFailJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert "403" in result["msg"]
    assert "rate limit" not in result["msg"].lower()


def test_latest_release_auth_failure(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"message": "Unauthorized"}, status=401)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
            "token": "bad_token",
        }
    ):
        with pytest.raises(AnsibleFailJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert "401" in result["msg"]


def test_latest_release_server_error_fails(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"message": "Internal Server Error"}, status=500)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleFailJson) as exc:
            github_release.main()

    result = exc.value.args[0]
    assert "500" in result["msg"]


def test_latest_release_no_token_no_authorization_header(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"tag_name": "v0.1.0"}, status=200)

    with set_module_args(
        {
            "user": "testuser",
            "repo": "testrepo",
            "action": "latest_release",
        }
    ):
        with pytest.raises(AnsibleExitJson):
            github_release.main()

    headers = fetch_url_mock.call_args[1]["headers"]
    assert "Authorization" not in headers


def test_latest_release_with_password_uses_github3(fetch_url_mock):
    """latest_release + password should use github3, not fetch_url."""
    mock_release = MagicMock()
    mock_release.tag_name = "v3.0.0"
    mock_repo = MagicMock()
    mock_repo.latest_release.return_value = mock_release
    mock_gh = MagicMock()
    mock_gh.repository.return_value = mock_repo

    with patch.object(github_release, "HAS_GITHUB_API", True):
        with patch.object(github_release, "github3") as mock_github3:
            mock_github3.login.return_value = mock_gh
            mock_github3.exceptions.AuthenticationFailed = Exception
            mock_github3.exceptions.GitHubError = Exception

            with set_module_args(
                {
                    "user": "testuser",
                    "repo": "testrepo",
                    "action": "latest_release",
                    "password": "secret",
                }
            ):
                with pytest.raises(AnsibleExitJson) as exc:
                    github_release.main()

    # fetch_url must NOT have been called (github3 path was used instead)
    fetch_url_mock.assert_not_called()
    result = exc.value.args[0]
    assert result["tag"] == "v3.0.0"


def test_latest_release_with_password_fails_without_github3(fetch_url_mock):
    """latest_release + password should fail when github3 is unavailable."""
    with patch.object(github_release, "HAS_GITHUB_API", False):
        with set_module_args(
            {
                "user": "testuser",
                "repo": "testrepo",
                "action": "latest_release",
                "password": "secret",
            }
        ):
            with pytest.raises(AnsibleFailJson) as exc:
                github_release.main()

    result = exc.value.args[0]
    assert "github3" in result["msg"].lower()


def test_create_release_fails_without_github3(fetch_url_mock):
    with patch.object(github_release, "HAS_GITHUB_API", False):
        with set_module_args(
            {
                "user": "testuser",
                "repo": "testrepo",
                "action": "create_release",
                "tag": "v1.0.0",
                "token": "ghp_testtoken",
            }
        ):
            with pytest.raises(AnsibleFailJson) as exc:
                github_release.main()

    result = exc.value.args[0]
    assert "github3" in result["msg"].lower()
