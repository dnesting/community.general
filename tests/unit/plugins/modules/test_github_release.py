# Copyright (c) Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
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


def make_fetch_url_response(body, status=200):
    response = MagicMock()
    response.read.return_value = json.dumps(body).encode("utf-8")
    info = {"status": status, "msg": f"HTTP {status}"}
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
    call_args = fetch_url_mock.call_args
    headers = call_args[1]["headers"]
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


def test_latest_release_rate_limit_fails(fetch_url_mock):
    fetch_url_mock.return_value = make_fetch_url_response({"message": "API rate limit exceeded"}, status=403)

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

    call_args = fetch_url_mock.call_args
    headers = call_args[1]["headers"]
    assert "Authorization" not in headers


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
