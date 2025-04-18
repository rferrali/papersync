import click
from dotenv import set_key
from pathlib import Path
import shutil
from importlib.resources import files
import papersync.utils as utils
from git import Repo, InvalidGitRepositoryError

@click.group()
def cli():
    pass

@click.command()
@click.argument('project', default=None, required=False)
@click.option('-y', '--yes', is_flag=True, help='Bypass confirmation prompts')
def push(yes, project):
    """
    Pushes project(s) to their respective remote directories.
    This command can operate in two modes:
    1. If a specific project name is provided as an argument, it pushes only that project.
    2. If no project name is provided, it pushes all projects.

    Arguments:
        project (str, optional): The name of the project to push. If not provided, 
        all projects are pushed.
    """
    # git-related checks
    utils.validate_git_state('push', yes=yes)
    if not project:
        click.echo(f"\u23f3 Pushing all projects to their remote directories...")
        # check if any project is malformed
        projects = utils.read_projects(fix=False, yes=yes)
        # check file overwrites
        ok = True
        for project_name, project in projects.items():
            click.echo(f"Project {project_name}: ", nl=False)
            # check if project is malformed
            ok = utils.validate_push_files_overwrite(project, yes=True)
        if not ok:
            click.confirm("Are you sure you want to push?", abort=True)
        for project_name, project in projects.items():
            click.echo(f"Project {project_name}: ", nl=False)
            utils.push_project(project)
    else:
        click.echo(f"\u23f3 Pushing project {project} to its remote directory...")
        # check if project is malformed
        project = utils.read_project(project, fix=False, yes=yes)
        # check file overwrites
        utils.validate_push_files_overwrite(project, yes=yes)
        utils.push_project(project)
    click.echo(f"Done!")

@click.command()
@click.argument('project', default=None, required=False)
@click.option('-y', '--yes', is_flag=True, help='Bypass confirmation prompts')
def pull(yes, project):
    """
    Pulls project(s) from their remote directories.

    Pulls project(s) from their respective remote directories.
    This command can operate in two modes:
    1. If a specific project name is provided as an argument, it pulls only that project.
    2. If no project name is provided, it pulls all projects.

    Argumentss:
        project (str, optional):  The name of the project to push. If not provided, 
        all projects are pulled.
    """
    # git-related checks
    utils.validate_git_state('pull', yes=yes)
    if not project:
        click.echo(f"\u23f3 Pulling all projects from their remote directories...")
        # check if any project is malformed
        projects = utils.read_projects(fix=False, yes=yes)
        for project_name, project in projects.items():
            click.echo(f"Project {project['name']}: ", nl=False)
            utils.pull_project(project)
    else:
        click.echo(f"\u23f3 Pulling project {project} from its remote directory...")
        # check if project is malformed
        project = utils.read_project(project, fix=False, yes=yes)
        utils.pull_project(project)
    click.echo(f"Done!")

@click.command()
def create():
    """Initialize a repo"""
    click.echo(f"\u23f3 Initializing...")
    env_file = Path(".env")
    config_file = Path("papersync.yaml")
    # Create the papersync.yaml file if it does not exist.
    if config_file.exists():
        click.echo(f"\u2757 Config file already exists. Skipping...")
        return
    shutil.copyfile(files('papersync.data').joinpath('papersync.yaml'), config_file)
    # Create the .env file if it does not exist.
    if not env_file.exists():
        click.echo(f"Creating .env file...")
        env_file.touch(mode=0o600, exist_ok=False)
    set_key(env_file, "PAPERSYNC_ARTICLE", "/some/path/to/article")
    click.echo(f"\u2705 Done! Please update papersync.yaml and .env with your own paths.")

@click.command()
@click.argument('project', default=None, required=False)
@click.option('-y', '--yes', is_flag=True, help='Bypass confirmation prompts')
def link(yes, project):
    """
    Creates symlinks in project(s), pointing to the relevant libraries or repairs them.

    This command can operate in two modes:
    1. If a specific project name is provided as an argument, it creates symlinks only for that project.
    2. If no project name is provided, it creates symlinks for all projects.

    Arguments:
        project (str, optional): The name of the project to create symlinks for. If not provided, 
        symlinks are created for all projects.
    """
    if not project:
        click.echo(f"\u23f3 Creating symlinks...")
        utils.read_config(fix=True, yes=yes)
    else:
        click.echo(f"\u23f3 Creating symlinks for project {project}...")
        utils.read_project(project, fix=True, yes=yes)
    click.echo(f"\u2705 Done!")

cli.add_command(create)
cli.add_command(push)
cli.add_command(pull)
cli.add_command(link)
