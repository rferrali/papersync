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

def read_config(confirm=True):
    # check if config file exists
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
    # are projects valid? 
    for p_name, project in config['projects'].items():
        project = validate_project(p_name, project, config['libraries'])
    return config

def validate_project(project_name, project, libraries):
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
    clean_libraries = []
    for library in project['libraries']:
        library = validate_local_library(project_name, local, library, libraries)
        clean_libraries.append(library)
    project['local'] = local
    project['remote'] = remote
    project['libraries'] = clean_libraries
    return project

def validate_local_library(project_name, local_path, library, libraries):
    # check if library is defined in libraries
    if library not in libraries:
        raise click.ClickException(f"\u274c Project {project_name}: library '{library}' isn't defined in as a config file library.")
    # check if library path exists
    local_library_path = local_path.joinpath(library)
    library_path = Path(libraries[library])
    # test that the path exists
    if not local_library_path.exists():
        raise click.ClickException(f"\u274c Project {project_name}: {local_path} doesn't contain a symlink pointing to library '{library}'. Run 'papersync link' to fix.")
    # check if the path is a symlink
    if not local_library_path.is_symlink():
        raise click.ClickException(f"\u274c Project {project_name}: {local_library_path} isn't a symlink pointing to {libraries[library]}. Look at this is then run 'papersync link' to fix.")
    # check if the symlink points to the library
    if local_library_path.resolve().absolute() != library_path.absolute():
        raise click.ClickException(f"\u274c Project {project_name}: the {local_library_path} symlink doesn't point to {libraries[library]}. Run 'papersync link' to fix.")
    return local_library_path

def check_push(local, remote, assets):
    compare = dircmp(local, remote)
    # extract folder name from assets path
    assets = Path(assets).name
    return diff_files(compare, local, remote, assets)

def diff_files(dcmp, local, remote, assets, name=''):
    out = {
        "right_only": [],
        "diff_files": []
    }
    for v in dcmp.right_only:
        # ignore assets folder in root
        if name == '' and v == assets:
            continue
        out["right_only"].append(os.path.join(name, v))
    for v in dcmp.diff_files:
        v = os.path.join(name, v)
        local_path = os.path.join(local, v)
        remote_path = os.path.join(remote, v)
        # if remote is more recent than local, add to diff_files
        if os.path.getmtime(remote_path) > os.path.getmtime(local_path):
            out["diff_files"].append(v)
    for sub_name, sub_dcmp in dcmp.subdirs.items():
        # ignore assets folder in root
        if name == '' and sub_name == assets:
            continue
        o = diff_files(sub_dcmp, local, remote, assets, os.path.join(name, sub_name))
        out["right_only"].extend(o["right_only"])
        out["diff_files"].extend(o["diff_files"])
    return out

# copy contents of local to remote
def push_project(local, remote):
    rmtree(remote, ignore_errors=True)
    copytree(local, remote)

def pull_project(local, remote, assets):
    rmtree(local, ignore_errors=True)
    copytree(remote, local)
    assets_path = Path(assets)
    assets_link_path = Path(local).joinpath(assets_path.name)
    rmtree(assets_link_path, ignore_errors=True)
    assets_link_path.symlink_to(assets_path.absolute(), target_is_directory=True)