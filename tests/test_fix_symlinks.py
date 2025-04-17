import os
from pathlib import Path
from papersync.cli import link
from click.testing import CliRunner
import tempfile

def test_read_projects(monkeypatch):
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a mock `papersync.yaml` file
        yaml_file = temp_path / "papersync.yaml"
        yaml_file.write_text("""
        libraries:
          assets: ./assets
        projects:
          article:
            local: ./tex/article
            remote: /home/user/tex/article
            libraries:
              - assets
        """)

        # Create a mock `.env` file
        env_file = temp_path / ".env"
        env_file.write_text("PAPERSYNC_ARTICLE=/home/user/dropbox/tex/article")

        # Mock the existence of the directories in papersync.yaml
        (temp_path / "tex" / "article").mkdir(parents=True, exist_ok=True)
        (temp_path / "assets").mkdir(parents=True, exist_ok=True)
        (temp_path / "static").mkdir(parents=True, exist_ok=True)

        # Monkeypatch Path.exists and Path.is_dir for the remote path
        # Save references to the original methods
        original_exists = Path.exists
        original_is_dir = Path.is_dir
        # Monkeypatch Path.exists and Path.is_dir for the remote path
        def mock_exists(path):
            if str(path) == "/home/user/tex/article":
                return True
            if str(path) == "/home/user/dropbox/tex/article":
                return True
            return original_exists(path)

        def mock_is_dir(path):
            if str(path) == "/home/user/tex/article":
                return True
            if str(path) == "/home/user/dropbox/tex/article":
                return True
            return original_is_dir(path)

        monkeypatch.setattr(Path, "exists", mock_exists)
        monkeypatch.setattr(Path, "is_dir", mock_is_dir)

        # Change the working directory to the temp directory
        original_cwd = Path.cwd()
        try:
            # Switch to the temporary directory
            os.chdir(temp_path)

            # Use CliRunner to invoke the `link` command
            runner = CliRunner()
            result = runner.invoke(link, ["--yes", "article"])
            # Check the output
            print(result.output)
            # Assert the command ran successfully
            assert result.exit_code == 0
            
            # Check if the symlink was created
            local_library_path = temp_path / "tex" / "article" / "assets"
            library_path = temp_path / "assets"
            assert local_library_path.exists(), f"Symlink {local_library_path} was not created."
            assert local_library_path.is_symlink(), f"{local_library_path} is not a symlink."
            assert local_library_path.resolve() == library_path.resolve(), f"Symlink {local_library_path} does not point to {library_path}."
        finally:
            # Restore the original working directory
            os.chdir(original_cwd)