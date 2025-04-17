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
def push():
    """Push projects to their remote directories."""
    click.echo(f"\u23f3 Pushing projects to their remote directories...")
    is_git_repo = True
    try: 
        repo = Repo()
    except InvalidGitRepositoryError:
        click.echo(f"\u2757 This is not a Git repository")
        is_git_repo = False
    if is_git_repo:
        # check if we're on the main branch
        if repo.active_branch.name != 'main':
            click.confirm(f"\u2757 You are about to push content from branch {repo.active_branch.name} instead of the main branch. Do you want to continue?", abort=True)
        if repo.is_dirty():
            click.confirm(f"\u2757 You are about to push content that has not been committed. Do you want to continue?", abort=True)
        # check if we're on the latest commit
        remote = repo.remote()
        remote.fetch()
        if repo.head.commit != remote.refs[0].commit:
            click.confirm(f"\u2757 You are behind the latest commit. You might be pushing content that is not up to date. Do you want to continue?", abort=True)
    ok = True
    config = utils.read_config()
    for project in config['projects']:
        click.echo(f"Project {project['name']}: checking that everything is ok...", nl=False)
        # compare local and remote
        check = utils.check_push(project['local'], project['remote'], config['assets'])
        if len(check['right_only']) > 0 or len(check['diff_files']) > 0:
            ok = False
            click.echo(f"\n  \u2757 Pushing may delete some content you need in the remote directory.")
            if len(check['right_only']) > 0:
                click.echo(f"  These files and directories are not in local:")
                for f in check['right_only']:
                    click.echo(f"    {f}")
            if len(check['diff_files']) > 0:
                click.echo(f"  These files are more recent in remote:")
                for f in check['diff_files']:
                    click.echo(f"    {f}")
        else: 
            click.echo(f" \u2705")
    if not ok:
        click.confirm("Are you sure you want to push?", abort=True)
    for project in config['projects']:
        click.echo(f"Project {project['name']}: pushing {project['local']} to {project['remote']}", nl=False)
        utils.push_project(project['local'], project['remote'])
        click.echo(f" \u2705")
    click.echo(f"Done!")

@click.command()
def pull():
    """Pull projects from their remote directories."""
    click.echo(f"\u23f3 Pulling projects from their remote directories...")
    is_git_repo = True
    try: 
        repo = Repo()
    except InvalidGitRepositoryError:
        click.echo(f"\u2757 This is not a Git repository")
        is_git_repo = False
    if is_git_repo:
        # check if repo is dirty
        if repo.is_dirty():
            click.confirm(f"\u2757 The repo has changes that have not been committed. Pulling may overwrite them. Do you want to continue?", abort=True)
    config = utils.read_config(confirm=True)
    for project in config['projects']:
        click.echo(f"Project {project['name']}: pulling {project['remote']} to {project['local']}", nl=False)
        utils.pull_project(project['local'], project['remote'], config['assets'])
        click.echo(f" \u2705")
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
@click.option('-y', '--yes', is_flag=True, help='Runs non-interactively by saying yes to prompts')
def link(yes, project):
    """Create symlinks pointing shared libraries in PROJECT's local directory. If PROJECT is not specified, all projects are linked."""
    if not project:
        click.echo(f"\u23f3 Creating symlinks...")
        utils.read_config(fix=True, confirm=not yes)
    else:
        click.echo(f"\u23f3 Creating symlinks for project {project}...")
        utils.read_project(project, fix=True, confirm=not yes)
    click.echo(f"Done!")

cli.add_command(create)
cli.add_command(push)
cli.add_command(pull)
cli.add_command(link)
