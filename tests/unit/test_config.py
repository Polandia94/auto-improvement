"""Unit tests for auto_improvement.config module."""

from __future__ import annotations

from pathlib import Path

import yaml

from auto_improvement.config import save_config
from auto_improvement.issues_tracker_clients.trac_client import TracClient
from auto_improvement.models import (
    Config,
    IssueTrackerConfig,
    LearningConfig,
    ProjectConfig,
    PRSelectionCriteria,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_nonexistent_file_returns_defaults(self) -> None:
        """Test loading from nonexistent file returns default config."""
        from auto_improvement.core import load_config as core_load_config

        config = core_load_config(Path("/nonexistent/path/config.yaml"))
        assert isinstance(config, Config)
        assert config.project.name is None

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        """Test loading from valid YAML file."""
        from auto_improvement.core import load_config as core_load_config

        config_data = {
            "project": {
                "name": "Test Project",
                "repo": "owner/repo",
            },
            "learning": {
                "max_attempts_per_pr": 5,
                "success_threshold": 0.9,
            },
        }

        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = core_load_config(config_file)
        assert config.project.name == "Test Project"
        assert config.project.repo == "owner/repo"
        assert config.learning.max_attempts_per_pr == 5
        assert config.learning.success_threshold == 0.9

    def test_load_with_issue_tracker_string(self, tmp_path: Path) -> None:
        """Test loading config with issue tracker as string."""
        from auto_improvement.core import load_config as core_load_config

        config_data = {
            "project": {"name": "Test"},
            "issue_tracker": {
                "client": "trac",
                "url": "https://code.djangoproject.com",
            },
        }

        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        config = core_load_config(config_file)
        assert config.issue_tracker.client == TracClient
        assert config.issue_tracker.url == "https://code.djangoproject.com"


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config_creates_file(self, tmp_path: Path) -> None:
        """Test that save_config creates the config file."""
        config = Config(
            project=ProjectConfig(name="Test Project", repo="owner/repo"),
        )

        config_file = tmp_path / "output.yaml"
        save_config(config, config_file)

        assert config_file.exists()

    def test_save_and_reload_config(self, tmp_path: Path) -> None:
        """Test saving and reloading config preserves values."""
        from auto_improvement.core import load_config as core_load_config

        original_config = Config(
            project=ProjectConfig(name="My Project", repo="test/repo"),
            learning=LearningConfig(max_attempts_per_pr=7, success_threshold=0.75),
            pr_selection=PRSelectionCriteria(
                min_files_changed=2,
                max_files_changed=30,
                days_back=90,
            ),
        )

        config_file = tmp_path / "config.yaml"
        save_config(original_config, config_file)

        loaded_config = core_load_config(config_file)
        assert loaded_config.project.name == "My Project"
        assert loaded_config.project.repo == "test/repo"
        assert loaded_config.learning.max_attempts_per_pr == 7
        assert loaded_config.learning.success_threshold == 0.75
        assert loaded_config.pr_selection.min_files_changed == 2
        assert loaded_config.pr_selection.max_files_changed == 30

    def test_save_config_with_tracker_class(self, tmp_path: Path) -> None:
        """Test saving config with issue tracker class."""
        config = Config(
            project=ProjectConfig(name="Test"),
            issue_tracker=IssueTrackerConfig(
                client=TracClient,
                url="https://trac.example.com",
            ),
        )

        config_file = tmp_path / "config.yaml"
        save_config(config, config_file)

        # Verify the file is valid YAML
        with open(config_file) as f:
            data = yaml.safe_load(f)

        assert "issue_tracker" in data
        # The client should be serialized as a string path or similar
        assert data["issue_tracker"]["url"] == "https://trac.example.com"
