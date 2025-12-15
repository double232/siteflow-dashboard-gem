"""Unit tests for input validators."""

import pytest
from app.validators import (
    ValidationError,
    validate_site_name,
    validate_domain,
    validate_branch,
    validate_git_url,
    validate_container_name,
    quote_shell_arg,
)


class TestValidateSiteName:
    def test_valid_names(self):
        assert validate_site_name("mysite") == "mysite"
        assert validate_site_name("my-site") == "my-site"
        assert validate_site_name("site123") == "site123"
        assert validate_site_name("a1b2c3") == "a1b2c3"

    def test_uppercase_converted_to_lowercase(self):
        assert validate_site_name("MySite") == "mysite"
        assert validate_site_name("ALLCAPS") == "allcaps"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_site_name("")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError, match="63 characters"):
            validate_site_name("a" * 64)

    def test_rejects_starting_with_hyphen(self):
        with pytest.raises(ValidationError):
            validate_site_name("-mysite")

    def test_rejects_ending_with_hyphen(self):
        with pytest.raises(ValidationError):
            validate_site_name("mysite-")

    def test_rejects_consecutive_hyphens(self):
        with pytest.raises(ValidationError, match="consecutive"):
            validate_site_name("my--site")

    def test_rejects_special_chars(self):
        with pytest.raises(ValidationError):
            validate_site_name("my_site")
        with pytest.raises(ValidationError):
            validate_site_name("my.site")
        with pytest.raises(ValidationError):
            validate_site_name("my site")

    def test_rejects_shell_injection(self):
        with pytest.raises(ValidationError):
            validate_site_name("site;rm -rf /")
        with pytest.raises(ValidationError):
            validate_site_name("$(whoami)")
        with pytest.raises(ValidationError):
            validate_site_name("`id`")


class TestValidateDomain:
    def test_valid_domains(self):
        assert validate_domain("example.com") == "example.com"
        assert validate_domain("sub.example.com") == "sub.example.com"
        assert validate_domain("my-site.example.com") == "my-site.example.com"

    def test_strips_protocol(self):
        assert validate_domain("https://example.com") == "example.com"
        assert validate_domain("http://example.com") == "example.com"

    def test_strips_path(self):
        assert validate_domain("example.com/path") == "example.com"
        assert validate_domain("https://example.com/path/to/page") == "example.com"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_domain("")

    def test_rejects_single_label(self):
        with pytest.raises(ValidationError, match="two labels"):
            validate_domain("localhost")

    def test_rejects_shell_injection(self):
        with pytest.raises(ValidationError):
            validate_domain("example.com;rm -rf /")


class TestValidateBranch:
    def test_valid_branches(self):
        assert validate_branch("main") == "main"
        assert validate_branch("develop") == "develop"
        assert validate_branch("feature/new-feature") == "feature/new-feature"
        assert validate_branch("release/v1.0.0") == "release/v1.0.0"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_branch("")

    def test_rejects_starting_with_hyphen(self):
        with pytest.raises(ValidationError, match="cannot start with hyphen"):
            validate_branch("-main")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValidationError, match="cannot contain"):
            validate_branch("../etc/passwd")

    def test_rejects_shell_injection(self):
        with pytest.raises(ValidationError):
            validate_branch("main;rm -rf /")


class TestValidateGitUrl:
    def test_valid_https_urls(self):
        url = validate_git_url("https://github.com/user/repo.git")
        assert url == "https://github.com/user/repo.git"

    def test_adds_git_suffix(self):
        url = validate_git_url("https://github.com/user/repo")
        assert url == "https://github.com/user/repo.git"

    def test_converts_git_at_format(self):
        url = validate_git_url("git@github.com:user/repo.git")
        assert url == "https://github.com/user/repo.git"

    def test_rejects_non_allowlisted_hosts(self):
        with pytest.raises(ValidationError, match="not allowed"):
            validate_git_url("https://evilsite.com/user/repo.git")

    def test_allows_github_gitlab_bitbucket(self):
        validate_git_url("https://github.com/user/repo.git")
        validate_git_url("https://gitlab.com/user/repo.git")
        validate_git_url("https://bitbucket.org/user/repo.git")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_git_url("")


class TestValidateContainerName:
    def test_valid_names(self):
        assert validate_container_name("mycontainer") == "mycontainer"
        assert validate_container_name("my-container") == "my-container"
        assert validate_container_name("my_container") == "my_container"
        assert validate_container_name("my.container") == "my.container"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_container_name("")

    def test_rejects_shell_injection(self):
        with pytest.raises(ValidationError):
            validate_container_name("container;rm -rf /")


class TestQuoteShellArg:
    def test_simple_string(self):
        assert quote_shell_arg("hello") == "hello"

    def test_string_with_spaces(self):
        result = quote_shell_arg("hello world")
        assert " " not in result or result.startswith("'")

    def test_string_with_special_chars(self):
        result = quote_shell_arg("test;rm -rf /")
        # Should be quoted to prevent injection
        assert ";" not in result or result.startswith("'")

    def test_string_with_quotes(self):
        result = quote_shell_arg("it's a test")
        # Should handle single quotes properly
        assert result  # Just verify it doesn't crash
