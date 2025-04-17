from dotenv import dotenv_values
from pathlib import Path
from importlib.resources import files
from yaml import safe_load
from filecmp import dircmp
import os
from shutil import copytree, rmtree
import click
from jsonschema import validate, ValidationError
import json
from git import Repo, InvalidGitRepositoryError

def read_projects(fix=False, yes=False):
    """
    Reads and validates the projects configuration.

    This function retrieves the projects from the configuration file,
    validates each project, and optionally fixes any issues based on
    the provided parameters.

    Args:
        fix (bool, optional): If True, attempts to fix any issues found
            during project validation. Defaults to False.
        yes (bool, optional): If True, automatically confirms any prompts
            during the fixing process. Defaults to False.

    Returns:
        dict: A dictionary containing the validated projects, where the
        keys are project names and the values are the validated project
        configurations.
    """
    config = validate_config()
    # are projects valid? 
    projects = {}
    for p_name, project in config['projects'].items():
        project = validate_project(p_name, project, config['libraries'], fix, yes)
        projects[p_name] = project
    return projects

def validate_config(): 
    config_file = Path("papersync.yaml")
    if not config_file.exists():
        raise click.ClickException(f"\u274c Config file 'papersync.yaml' not found. Perhaps you didn't run 'papersync create'? Or you're not using papersync at the root of the local directory.")
    # check if config file is valid
    # can it be loaded? 
    try:
        with config_file.open() as f:
            config = safe_load(f)
    except Exception as e:
        raise click.ClickException(f"\u274c Config file is not a well-formatted yaml.\n{e}")
    # Load the JSON schema
    schema_path = Path(files('papersync.data').joinpath('schema.json'))
    with schema_path.open() as schema_file:
        schema = json.load(schema_file)
    # Validate the YAML data against the schema
    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise click.ClickException(f"\u274c Config file invalid..\n{e}")
    if 'libraries' not in config:
        config['libraries'] = {}
    # are libraries valid? 
    for l_name, l_path in config['libraries'].items():
        library_path = Path(l_path)
        if not library_path.exists():
            raise click.ClickException(f"\u274c Library {l_name}: Path does not exist: {l_path}")
        config['libraries'][l_name] = library_path
    return config

def read_project(project_name, fix=False, yes=False):
    """
    Reads and validates a project configuration.

    Args:
        project_name (str): The name of the project to read.
        fix (bool, optional): Whether to attempt to fix issues in the project configuration. Defaults to False.
        yes (bool, optional): Automatically confirm prompts when fixing issues. Defaults to False.

    Returns:
        dict: The validated project configuration.

    Raises:
        click.ClickException: If the project is not found in the configuration file.
    """
    config = validate_config()
    # check if project exists
    if project_name not in config['projects']:
        raise click.ClickException(f"\u274c Project {project_name} not found in config file.")
    # check if project is valid
    project = validate_project(project_name, config['projects'][project_name], config['libraries'], fix, yes)
    return project

def validate_project(project_name, project, libraries, fix=False, yes=False):
    """
    Validates the configuration of a project by checking the existence and validity of 
    its local and remote directories, as well as its associated libraries.

    Args:
        project_name (str): The name of the project being validated.
        project (dict): A dictionary containing project configuration, including 'local', 
                        'remote', and 'libraries' keys.
        libraries (dict): A dictionary of available libraries for validation.
        fix (bool, optional): If True, attempts to fix issues found during validation. Defaults to False.
        yes (bool, optional): If True, automatically confirms prompts during the fixing process. Defaults to False.

    Raises:
        click.ClickException: If the local directory does not exist or is not a directory.
        click.ClickException: If the remote directory is not defined, does not exist, or is not a directory.
        click.ClickException: If both the configuration file and the .env file contain a remote path.

    Returns:
        dict: The updated project dictionary with validated and resolved 'local', 'remote', 
              and 'libraries' paths.
    """
    # check if local exists
    local = Path(project['local'])
    if not local.exists():
        raise click.ClickException(f"\u274c Project {project_name}: local directory not found: {project['local']}")
    if not local.is_dir():
        raise click.ClickException(f"\u274c Project {project_name}: local path is not a directory: {project['local']}")
    # check if remote exists
    # look in env file
    env_file = Path(".env")
    is_env = env_file.exists()
    is_valid_env = False
    env_remote = None
    if is_env:
        try: 
            env = dotenv_values(env_file)
            is_valid_env = True
        except Exception as e:
            env = None
            is_valid_env = False
    if is_env and is_valid_env:
        env_remote = env.get('PAPERSYNC_' + project_name.upper())
    # look in config file
    if 'remote' not in project and not env_remote:
        raise click.ClickException(f"\u274c Project {project_name}: remote path not defined. Ensure 'remote' is defined in the config file or 'PAPERSYNC_{project_name.upper()}' is set in the .env file (mind the case).")
    if env_remote:
        remote = Path(env_remote)
        if 'remote' in project:
            click.echo(f"\u2757 Project {project_name}: the config and the .env files both contain a remote path. Using the value from the .env file by default.")
    else:
        remote = Path(project['remote'])
    if not remote.exists():
        raise click.ClickException(f"\u274c Project {project_name}: remote directory not found: {remote}")
    if not remote.is_dir():
        raise click.ClickException(f"\u274c Project {project_name}: remote path is not a directory: {remote}")
    if 'libraries' not in project:
        project['libraries'] = []
    clean_libraries = {}
    for library in project['libraries']:
        library_path = validate_local_library(project_name, local, library, libraries, fix, yes)
        clean_libraries[library] = library_path
    project['local'] = local
    project['remote'] = remote
    project['libraries'] = clean_libraries
    return project

def validate_local_library(project_name, local_path, library, libraries, fix=False, yes=False):
    """
    Validates the local library configuration for a given project.

    This function ensures that the specified library is properly configured
    as a symlink in the local project directory. It performs several checks
    and optionally fixes issues if requested.

    Args:
        project_name (str): The name of the project being validated.
        local_path (Path): The local path to the project's directory.
        library (str): The name of the library to validate.
        libraries (dict): A dictionary mapping library names to their shared paths.
        fix (bool, optional): Whether to attempt fixing issues automatically. Defaults to False.
        yes (bool, optional): If True, skips confirmation prompts when fixing issues. Defaults to False.

    Raises:
        click.ClickException: If validation fails and `fix` is False, or if an issue cannot be resolved.

    Returns:
        dict: A dictionary containing:
            - "local" (Path): The local symlink path to the library.
            - "shared" (Path): The shared path to the library.
    """
    # check if library is defined in libraries
    if library not in libraries:
        raise click.ClickException(f"\u274c Project {project_name}: library '{library}' isn't defined in as a config file library.")
    # check if library path exists
    local_library_path = local_path.joinpath(library)
    library_path = Path(libraries[library])
    # check if the path is a directory
    is_dir = library_path.is_dir()
    # test that the path exists
    if not local_library_path.exists():
        if fix:
            click.echo(f"\u2757 Project {project_name}: {local_path} doesn't contain a symlink pointing to library '{library}'. Fixing...")
            local_library_path.symlink_to(library_path.absolute(), target_is_directory=is_dir)
        else:
            raise click.ClickException(f"\u274c Project {project_name}: {local_path} doesn't contain a symlink pointing to library '{library}'. Run 'papersync link' to fix.")
    # check if the path is a symlink
    if not local_library_path.is_symlink():
        if fix:
            click.echo(f"\u2757 Project {project_name}: {local_library_path} isn't a symlink pointing to {libraries[library]}. Fixing...")
            if not yes:
                click.confirm(f"Do you want to delete {local_library_path} and create a symlink instead? (you may lose data)", abort=True)
            local_library_path.unlink()
            local_library_path.symlink_to(library_path.absolute(), target_is_directory=is_dir)
        else:
            raise click.ClickException(f"\u274c Project {project_name}: {local_library_path} isn't a symlink pointing to {libraries[library]}. Look at this then run 'papersync link' to fix.")
    # check if the symlink points to the library
    if local_library_path.resolve().absolute() != library_path.absolute():
        if fix:
            click.echo(f"\u2757 Project {project_name}: the {local_library_path} symlink doesn't point to {libraries[library]}. Fixing...")
            local_library_path.unlink()
            local_library_path.symlink_to(library_path.absolute(), target_is_directory=is_dir)
        else:
            raise click.ClickException(f"\u274c Project {project_name}: the {local_library_path} symlink doesn't point to {libraries[library]}. Run 'papersync link' to fix.")
    return {
        "local": local_library_path,
        "shared": library_path,
    }

def validate_git_state(action, yes=False):
    """
    Validate the state of the git repository before performing an action.

    Args:
        action (str): The action being performed ('push' or 'pull').
        yes (bool): If True, skip confirmation prompts.
    """
    try:
        repo = Repo()
    except InvalidGitRepositoryError:
        return  # Not a git repository, no validation needed

    if repo.is_dirty() and not yes:
        click.confirm(f"\u2757 The repo is dirty. Do you want to continue with the {action}?", abort=True)

    if action == 'push':
        try:
            remote = repo.remote()
            remote.fetch()
            if repo.head.commit != remote.refs[0].commit and not yes:
                click.confirm(
                    f"\u2757 You are behind the latest commit. You might be pushing content that is not up to date. "
                    f"Do you want to continue?", abort=True)
        except Exception:
            pass

def validate_push_files_overwrite(project, yes=False):
    """
    Validates whether it is safe to overwrite files during a push operation.

    This function checks for potential conflicts between local and remote files
    in the specified project. It identifies files that are present only in the
    remote directory or files that are more recent in the remote directory. If
    such conflicts are found, the user is warned and prompted for confirmation
    before proceeding with the push operation.

    Args:
        project: The project object or path containing the files to be validated.
        yes (bool, optional): If True, skips the confirmation prompt and assumes
            the user agrees to proceed. Defaults to False.

    Returns:
        bool: True if it is safe to proceed with the push operation, False otherwise.

    Raises:
        click.Abort: If the user chooses not to proceed when prompted for confirmation.

    Notes:
        - The function uses the `diff_files` utility to determine differences
          between local and remote directories.
        - User interaction is handled via the `click` library for terminal output
          and confirmation prompts.
    """
    click.echo(f"Checking that files are safe for owerwrite...", nl=False)
    ok = True
    diff = diff_files(project)
    if len(diff['right_only']) > 0 or len(diff['diff_files']) > 0:
        ok = False
        click.echo(f"\n  \u2757 Pushing may delete some content you need in the remote directory.")
        if len(diff['right_only']) > 0:
            click.echo(f"  These files and directories are not in local:")
            for f in diff['right_only']:
                click.echo(f"    {f}")
        if len(diff['diff_files']) > 0:
            click.echo(f"  These files are more recent in remote:")
            for f in diff['diff_files']:
                click.echo(f"    {f}")
    else: 
        click.echo(f" \u2705")
    if not ok and not yes:
        click.confirm("Are you sure you want to push?", abort=True)
    return ok

def diff_files(project, name='', dcmp=None):
    """
    Compare the contents of two directories (local and remote) and identify files
    that are either only present in the remote directory or differ between the two.

    Args:
        project (dict): A dictionary containing the following keys:
            - 'local' (str): Path to the local directory.
            - 'remote' (str): Path to the remote directory.
            - 'libraries' (list): A list of library names to ignore in the root directory.
        name (str, optional): The relative path within the directory structure being compared.
                              Defaults to an empty string, representing the root.
        dcmp (filecmp.dircmp, optional): A dircmp object used for directory comparison.
                                         If None, a new dircmp object is created using the
                                         local and remote paths. Defaults to None.

    Returns:
        dict: A dictionary with the following keys:
            - "right_only" (list): A list of file paths that are only present in the remote directory.
            - "diff_files" (list): A list of file paths that differ between the local and remote directories,
                                   where the remote file is more recent than the local file.

    Notes:
        - Files or directories listed in the 'libraries' key of the project dictionary are ignored
          when they are in the root directory.
        - The function recursively compares subdirectories and aggregates the results.
    """
    if dcmp is None:
        dcmp = dircmp(project['local'], project['remote'])
    out = {
        "right_only": [],
        "diff_files": []
    }
    for v in dcmp.right_only:
        # ignore libraries in root
        if name == '' and v in project['libraries']:
            continue
        out["right_only"].append(os.path.join(name, v))
    for v in dcmp.diff_files:
        v = os.path.join(name, v)
        local_path = os.path.join(project['local'], v)
        remote_path = os.path.join(project['remote'], v)
        # ignore libraries in root
        if name == '' and Path(v).name in project['libraries']:
            continue
        # if remote is more recent than local, add to diff_files
        if os.path.getmtime(remote_path) > os.path.getmtime(local_path):
            out["diff_files"].append(v)
    for sub_name, sub_dcmp in dcmp.subdirs.items():
        # ignore library folders in root
        if name == '' and sub_name in project['libraries']:
            continue
        o = diff_files(sub_dcmp, project, os.path.join(name, sub_name))
        out["right_only"].extend(o["right_only"])
        out["diff_files"].extend(o["diff_files"])
    return out

# copy contents of local to remote
def push_project(project):
    """
    Pushes a project from a local directory to a remote directory.

    This function removes the contents of the remote directory (if it exists),
    then copies the contents of the local directory to the remote directory.

    Args:
        project (dict): A dictionary containing the following keys:
            - 'local' (str): The path to the local directory.
            - 'remote' (str): The path to the remote directory.

    Raises:
        OSError: If an error occurs during the removal or copying of directories.

    Side Effects:
        Prints status messages to the console using `click.echo`.
    """
    click.echo(f"Pushing {project['local']} to {project['remote']}", nl=False)
    rmtree(project, ignore_errors=True)
    copytree(project['local'], project['remote'])
    click.echo(f" \u2705")

def pull_project(project):
    click.echo(f"Pulling {project['remote']} to {project['local']}", nl=False)
    rmtree(project['local'], ignore_errors=True)
    copytree(project['remote'], project['local'])
    for library_name, library in project['libraries'].items():
        library_local_path = project['local'].joinpath(library['local'])
        library_shared_path = Path(library['shared'])
        rmtree(library_local_path, ignore_errors=True)
        is_dir = library_shared_path.is_dir()
        library_local_path.symlink_to(library_shared_path.absolute(), target_is_directory=is_dir)
    click.echo(f" \u2705")