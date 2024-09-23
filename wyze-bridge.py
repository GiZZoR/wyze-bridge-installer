import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.request

from datetime import datetime
from filecmp import cmp as file_compare
from io import BytesIO
from pwd import getpwnam as check_user
from shutil import copyfile, rmtree
from tarfile import open as tarfile_open
from venv import create as venv_create

_SERVICE_MANAGER = None

_COLOR_RED = '31'
_COLOR_GREEN = '32'
_COLOR_CYAN = '36'
_COLOR_YELLOW = '33'
_COLOR_PURPLE = '35'
_COLOR_RESET = '0'

def _exec_command(command):
    """Runs a shell command."""
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        _print_color(f"Error: {e}", _COLOR_RED)

def _print_color(message, color):
    """Prints the message in the specified color."""
    print(f"\033[{color}m{message}\033[{_COLOR_RESET}m")

def _str2bool(value):
    if isinstance(value, bool):
        return value
    if value.lower() in {'yes', 'true', 't', 'y', '1'}:
        return True
    elif value.lower() in {'no', 'false', 'f', 'n', '0'}:
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

class _Config:
    def __init__(self):
        self.APP_CONF = "/etc/wyze-bridge/app.env"
        self.APP_GUNICORN = False
        self.APP_IP = "0.0.0.0"
        self.APP_PATH = "/srv/wyze-bridge"
        self.APP_PORT = 5000
        self.APP_USER = "wyze"
        self.APP_VERSION = "latest"
        self.MEDIA_MTX_VERSION = "latest"
        self.MEDIA_MTX_PATH = "/srv/mediamtx"
        self.INSTALLATION_CONF = "/etc/wyze-bridge/install.json"
        self.read_config_file()

    def get_description(self, name):
        descriptions = {
            "APP_CONF": "Path to env file containing docker-wyze-bridge settings.",
            "APP_IP": "IP address on which docker-wyze-bridge will listen.",
            "APP_PATH": "Location of docker-wyze-bridge application.",
            "APP_PORT": "Port on which docker-wyze-bridge will listen.",
            "APP_USER": "User account used to run the docker-wyze-bridge.",
            "APP_VERSION": "Version of docker-wyze-bridge to install.",
            "APP_GUNICORN": "Use Gunicorn for frontend service.",
            "MEDIA_MTX_VERSION": "Version of mediamtx to install.",
            "MEDIA_MTX_PATH": "Location of mediamtx application.",
            "INSTALLATION_CONF": "Path to file containing settings of this script, used for updates."
        }
        return descriptions[name]

    def read_config_file(self):
        if os.path.isfile(self.INSTALLATION_CONF):
            try:
                with open(self.INSTALLATION_CONF, "r") as file:
                    install_conf = json.load(file)
            except:
                _print_color(f"Unexpected error reading from: {self.INSTALLATION_CONF}")
            for key, value in install_conf.items():
                setattr(self, key, value)

    def write_config_file(self):
        if os.path.isdir(os.path.dirname(self.INSTALLATION_CONF)) == False:
            os.makedirs(os.path.dirname(self.INSTALLATION_CONF),750)
        with open(self.INSTALLATION_CONF, "w") as file:
            output_obj = self.__dict__.copy()
            del output_obj["INSTALLATION_CONF"]
            file.writelines(json.dumps(output_obj, indent=2))
            del output_obj

    def create_arguments(self, parser):
        app_group = parser.add_argument_group("Application Settings")
        mtx_group = parser.add_argument_group("MediaMTX Settings")

        for key, value in self.__dict__.items():
            try:
                desc = self.get_description(key)
            except:
                continue
            if key.startswith("APP"):
                app_group.add_argument(f"--{key}", type=str, default=None, help=f'{desc} CURRENT: {value}')
            elif key.startswith("MEDIA_MTX"):
                mtx_group.add_argument(f"--{key}", type=str, default=None, help=f'{desc} CURRENT: {value}')
            else:
                parser.add_argument(f"--{key}", type=str, default=None, help=f'{desc} CURRENT: {value}')

    def parse_arguments(self, args):
        if args.INSTALLATION_CONF != None:
            self.INSTALLATION_CONF = args.INSTALLATION_CONF
            self.read_config_file()
        for key, value in self.__dict__.items():
            if args.__dict__[key] == None: continue
            if value != args.__dict__[key]:
                if key == "APP_GUNICORN":
                    setattr(self, key, _str2bool(args.__dict__[key]))
                else:
                    setattr(self, key, args.__dict__[key])
        if args.action == "update" and args.APP_VERSION == None:
            self.APP_VERSION = "latest"

class _Prerequisites:
    def detect_service_manager():
        """Identify if system is openrc or systemd."""
        global _SERVICE_MANAGER
        if os.path.isfile("/usr/bin/systemctl"):
            _SERVICE_MANAGER = "systemd"
            return None

        if os.path.isfile("/sbin/rc-update"):
            _SERVICE_MANAGER = "openrc"
            return None

        _print_color("Unable to identify system service manager (systemd/openrc).", _COLOR_RED)
        sys.exit(1)

    def python_version(min_version=(3, 10)):
        """Check that current Python version is above 3.10."""
        current_version = sys.version_info[:3]
        if current_version < min_version:
            print(f"\033[0;31mError: Python version must be {min_version[0]}.{min_version[1]} or higher. "
                f"Current version is {'.'.join(map(str, current_version))}.\033[0m")
            sys.exit(1)

    def internet_access(host: str = 'github.com', port: int = 443, timeout: int = 5):
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False

    def is_root():
        """Checks if the script is run as root."""
        if os.geteuid() != 0:
            _print_color("This script must be run as root.", _COLOR_RED)
            sys.exit(1)

class _FilesystemActions:
    def chmod(path: str, mode: str):
        """Changes the mode of a file or directory."""
        try:
            os.chmod(path, mode)
        except Exception as e:
            _print_color(f"Error changing mode: {e}", _COLOR_RED)
            sys.exit(1)

    def chown(path: str, user: str, group: str):
        """Changes the ownership of a file or directory recursively."""
        try:
            _exec_command(f"chown -R {user}:{group} {path}")
        except Exception as e:
            _print_color(f"Error changing ownership: {e}", _COLOR_RED)
            sys.exit(1)

    def extract_tarball(tar_data, path: str, file_name_contains: str = None, strip_dirs: int = 0):
        with tarfile_open(fileobj=tar_data, mode='r:gz') as tar:
            for member in tar.getmembers():
                if file_name_contains != None:
                    if file_name_contains in member.name:
                        if strip_dirs != 0:
                            member_path = member.name.split('/', strip_dirs)[-1]
                            member.name = member_path
                    else:
                        continue
                tar.extract(member, path)

    def create_application_folders(folders: list, service_user: str):
        """Creates the required folders for installation."""
        try:
            _print_color(f"Creating required folders: {','.join(folders)}", _COLOR_CYAN)
            for path in folders:
                os.makedirs(path, exist_ok=True)
                _FilesystemActions.chown(path, service_user, service_user)
        except Exception as e:
            _print_color(f"Error creating folders: {e}", _COLOR_RED)
            sys.exit(1)

class _Github:
    def __init__(self, author: str, repo_name: str):
        self.repo_name = repo_name
        self._api_url_ = f"https://api.github.com/repos/{author}/{repo_name}"

    def download_file(self, url):
        """Downloads a file from a URL into memory using urllib."""
        try:
            with urllib.request.urlopen(url) as response:
                if response.status != 200:
                    raise Exception(f"Error: HTTP {response.status}")
                return BytesIO(response.read())
        except Exception as e:
            print(f"[{self.repo_name}] Error downloading file: {e}", file=sys.stderr)
            sys.exit(1)

    def fetch_release_url(self, version="latest"):
        """Fetches the release URL based on the specified version."""
        if version == "latest":
            return f"{self._api_url_}/releases/latest"

        try:
            response = urllib.request.urlopen(f"{self._api_url_}/releases")
            if response.status != 200:
                _print_color(f"[{self.repo_name}] Error fetching release info: {response.status} - {response.read().decode()}", _COLOR_RED)
                sys.exit(2)

            while "next" in response.headers.get('link', ''):
                releases = json.loads(response.read().decode())
                for release in releases:
                    if release["name"] == version or release["tag_name"] in [version, f"v{version}"]:
                        return release["url"]
                next_link = response.headers['link'].split(',')[0].split(';')[0].strip('<> ')
                response = urllib.request.urlopen(next_link)

            raise Exception(f"[{self.repo_name}] Unable to locate release: {version}")

        except Exception as e:
            _print_color(f"[{self.repo_name}] Error locating release URL: {e}", _COLOR_RED)
            sys.exit(1)

    def get_release(self, version, asset_pattern=None, debug=False):
        """Fetches the release information and returns the relevant asset URL."""
        release_url = self.fetch_release_url(version)
        try:
            response = urllib.request.urlopen(release_url)
            release_info = json.loads(response.read().decode())

            if debug:
                print(f"[{self.repo_name}] Found release: {release_info['name']}")

            if "assets" in release_info and asset_pattern:
                for asset in release_info["assets"]:
                    if asset_pattern in asset["name"]:
                        return {"tag_name": release_info["tag_name"], "tarball": asset["browser_download_url"]}
            else:
                return {"tag_name": release_info["tag_name"], "tarball": release_info["tarball_url"]}

        except json.JSONDecodeError as e:
            _print_color(f"[{self.repo_name}] Error decoding JSON response: {e}", _COLOR_RED)
            _print_color(f"[{self.repo_name}] Response content: {response.read().decode()}", _COLOR_RED)
            sys.exit(1)
        except Exception as e:
            _print_color(f"[{self.repo_name}] Unexpected error: {e}", _COLOR_RED)
            sys.exit(1)

class _WyzeBridgeInstallation:
    def __init__(self, install_path: str, version: str):
        self.version = version
        self.install_path = install_path
        self._env_file = os.path.join(install_path,".env")
        self.installed = False
        if os.path.isfile(os.path.join(install_path,"frontend.py")):
            self.installed = True

    def backup(self, output_path):
        os.makedirs(os.path.join(self.user_home, 'wyze-backups'), exist_ok=True)

        for dir_name in [self.install_path, "/tokens"]:
            tar_path = f"{output_path}-{dir_name.split('/')[-1]}.tgz"
            _print_color(f"Backing up {dir_name} to: {tar_path}", _COLOR_CYAN)
            with tarfile_open(tar_path, "w:gz") as tar:
                tar.add(dir_name, arcname=os.path.basename(dir_name))
            _FilesystemActions.chmod(tar_path,0o600)

        _FilesystemActions.chown(os.path.join(self.user_home, f'wyze-backups'),self.service_user,self.service_user)

    def create_pyvenv(self, path):
        """Creates a Python virtual environment."""
        try:
            _print_color(f"Creating python virtual environment at: {path}", _COLOR_CYAN)
            venv_create(env_dir=path, with_pip=True)
            _FilesystemActions.chown(path, self.service_user, self.service_user)
        except Exception as e:
            _print_color(f"Error creating python virtual environment: {e}", _COLOR_RED)
            sys.exit(1)
        self.venv_path = path

    def create_service_user(self, user_name: str):
        """Creates the service user if it does not exist."""
        try:
            check_user(user_name)
        except KeyError:
            _print_color(f"User {user_name} doesn't exist. Creating system account.", _COLOR_YELLOW)
            useradd = subprocess.run("useradd", shell=True, capture_output=True)
            if useradd.returncode == 127:
                _exec_command(f'addgroup -S {user_name}')
                _exec_command(f'adduser -S -G {user_name} -h /home/{user_name} -s /bin/ash {user_name}')
            else:
                _exec_command(f'useradd --system --create-home --user-group --home-dir /home/{user_name} --shell /usr/bin/bash {user_name}')

        self.user_home = os.path.expanduser(f'~{user_name}')
        self.service_user = user_name

    def create_settings_file(self, file_path: str):
        """Creates the settings environment configuration file."""
        try:
            _print_color(f"Creating persistent settings file at: {file_path}", _COLOR_CYAN)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as file:
                file.write("""# [OPTIONAL] Credentials can be set in the WebUI
# API Key and ID can be obtained from the wyze dev portal:
# https://developer-api-console.wyze.com/#/apikey/view
#WYZE_EMAIL=
#WYZE_PASSWORD=
#API_ID=
#API_KEY=

# WebUI and Stream authentication:
# Set WB_AUTH to false to disable web and stream auth.
WB_AUTH=True
# WB_USERNAME=
# WB_PASSWORD=
# STREAM_AUTH=

## Additional Options can be configured here, as per
## https://github.com/mrlt8/docker-wyze-bridge/wiki/Advanced-Option""")

            _FilesystemActions.chown(file_path, self.service_user, self.service_user)
            _FilesystemActions.chmod(file_path, 0o600)
        except Exception as e:
            _print_color(f"Error creating user environment: {e}", _COLOR_RED)
            sys.exit(1)

    def get_installed_dwb_version(self):
        if os.path.isfile(self._env_file):
            with open(self._env_file, 'r') as file:
                for line in file:
                    if line.startswith('VERSION'):
                        return line.split('=')[1].strip()
        return None

    def install_docker_wyze_bridge_app(self):
        """Installs the docker-wyze-bridge."""
        try:
            dwb_git = _Github(author="mrlt8", repo_name="docker-wyze-bridge")
            get_version = self.version
            dwb_release = dwb_git.get_release(version=get_version)
            version_tag = dwb_release.get('tag_name', '').lstrip('v')

            _print_color(f"Installing docker-wyze-bridge version: {version_tag}", _COLOR_PURPLE)
            tar_data = dwb_git.download_file(url=dwb_release["tarball"])
            _FilesystemActions.extract_tarball(tar_data=tar_data,path=self.install_path,file_name_contains="/app/", strip_dirs=2)

            self.update_env_file(key="VERSION", value=version_tag)
        except Exception as e:
            _print_color(f"Unexpected error: {e}", _COLOR_RED)
            sys.exit(1)

    def install_ffmpeg(self):
        """Installs ffmpeg-for-homebridge for docker-wyze-brige, if ffmpeg doesn't exist."""
        _print_color("Installing ffmpeg-for-homebridge", _COLOR_CYAN)

        ffmpeg = subprocess.run("ffmpeg", shell=True, capture_output=True)
        if ffmpeg.returncode == 1:
            _print_color("ffmpeg already installed", _COLOR_GREEN)
        else:
            ffmpeg_git = _Github("homebridge", "ffmpeg-for-homebridge")
            ffmpeg_latest = ffmpeg_git.get_release(version="latest", asset_pattern="x86_64")
            ffmpeg_latest_release = ffmpeg_git.download_file(ffmpeg_latest["tarball"])
            _FilesystemActions.extract_tarball(tar_data=ffmpeg_latest_release,path="/")
            ffmpeg = subprocess.run("ffmpeg", shell=True, capture_output=True)
            if ffmpeg.returncode == 127:
                _print_color("Error installing ffmpeg", _COLOR_RED)
                sys.exit(1)
            else:
                _print_color("Installed ffmpeg", _COLOR_GREEN)

    def install_service_systemd(self):
        """Installs the Flask service on a Debian-based system."""
        try:
            _print_color("Installing systemd service.", _COLOR_CYAN)
            service_file_path = "/etc/systemd/system/wyze-bridge.service"

            if scriptConfig.APP_GUNICORN:
                CMD = f"{self.venv_path}/bin/gunicorn --bind={scriptConfig.APP_IP}:{scriptConfig.APP_PORT} --workers=1 --threads=1 'frontend:create_app()'"
            else:
                CMD = f"{self.venv_path}/bin/flask --app frontend run --host {scriptConfig.APP_IP} --port {scriptConfig.APP_PORT}"

            service_file_content = """[Unit]
Description=wyze-bridge daemon
After=network.target

[Service]
User={SERVICE_USER}
Group={SERVICE_USER}
WorkingDirectory={INSTALL_DIR}
EnvironmentFile={INSTALL_DIR}/.env
EnvironmentFile={USER_CONF}
ExecStart={CMD}
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always

[Install]
WantedBy=multi-user.target""".format(
                VENV_DIR=self.venv_path,
                USER_CONF=scriptConfig.APP_CONF,
                LISTEN_IP=scriptConfig.APP_IP,
                LISTEN_PORT=scriptConfig.APP_PORT,
                SERVICE_USER=scriptConfig.APP_USER,
                INSTALL_DIR=scriptConfig.APP_PATH,
                CMD=CMD
            )
            with open(service_file_path, 'w') as service_file:
                service_file.write(service_file_content)

            _exec_command('systemctl daemon-reload')
            _exec_command('systemctl enable wyze-bridge.service')

        except Exception as e:
            _print_color(f"Error installing Flask service on Debian-based system: {e}", _COLOR_RED)
            sys.exit(1)

    def install_service_openrc(self):
        """Installs the Flask service on an Alpine-based system."""
        try:
            _print_color("Installing OpenRC service on Alpine-based system.", _COLOR_CYAN)

            if scriptConfig.APP_GUNICORN:
                CMD = f"{self.venv_path}/bin/gunicorn"
                CMD_ARGS = f"--bind={scriptConfig.APP_IP}:{scriptConfig.APP_PORT} --workers=1 --threads=1 -u {scriptConfig.APP_USER} -g {scriptConfig.APP_USER} frontend:create_app()"
                APP = "gunicorn"
            else:
                CMD = f"{self.venv_path}/bin/flask"
                CMD_ARGS = f"--app frontend run --host {scriptConfig.APP_IP} --port {scriptConfig.APP_PORT}"
                APP = "flask"

            service_file_content = """#!/sbin/openrc-run

description="wyze-bridge daemon"

command="{CMD}"
command_args="{CMD_ARGS}"
command_user="{SERVICE_USER}"
command_background="yes"
output_log="/var/log/wyze-bridge.log"

depend() {{
    need net
}}

start_pre() {{
    ebegin "Setting up environment"
    if [ -f {INSTALL_DIR}/.env ]; then
        export $(grep -v '^#' {INSTALL_DIR}/.env | xargs)
    fi
    if [ -f {USER_CONF} ]; then
        export $(grep -v '^#' {USER_CONF} | xargs)
    fi
}}

start() {{
    ebegin "Starting wyze-bridge"
    start-stop-daemon -S -d {INSTALL_DIR} -x $command -- $command_args >> $output_log 2>&1 &
    eend $?
}}

stop() {{
    ebegin "Stopping wyze-bridge"
    start-stop-daemon --stop --retry 3 --name {APP}
    eend $?
}}
""".format(
                VENV_DIR=self.venv_path,
                USER_CONF=scriptConfig.APP_CONF,
                LISTEN_IP=scriptConfig.APP_IP,
                LISTEN_PORT=scriptConfig.APP_PORT,
                SERVICE_USER=scriptConfig.APP_USER,
                INSTALL_DIR=scriptConfig.APP_PATH,
                CMD=CMD,
                CMD_ARGS=CMD_ARGS,
                APP=APP
            )

            service_file_path = "/etc/init.d/wyze-bridge"

            with open(service_file_path, 'w') as service_file:
                service_file.write(service_file_content)

            os.chmod(service_file_path, 0o755)
            _exec_command('rc-update add wyze-bridge default')
            _exec_command('rc-service wyze-bridge start')
        except Exception as e:
            _print_color(f"Error installing service on Alpine-based system: {e}", _COLOR_RED)
            sys.exit(1)

    def install_gunicorn(self):
        """Install gunicorn for wsgi, instead of using flask."""
        try:
            _print_color("Installing gunicorn", _COLOR_CYAN)
            _exec_command(f'{self.venv_path}/bin/pip install --disable-pip-version-check gunicorn')
        except Exception as e:
            _print_color(f"Error installing Python requirements: {e}", _COLOR_RED)
            sys.exit(1)

    def install_iotc_library(self):
        """Installs the TUTK IOTC library."""
        try:
            lib_path = "/usr/local/lib/libIOTCAPIs_ALL.so"
            source_lib_path = os.path.join(self.install_path, f'lib/lib.amd64')

            if not os.path.isfile(lib_path):
                _print_color("Installing TUTK IOTC library.", _COLOR_CYAN)
                copyfile(source_lib_path, lib_path)
                _FilesystemActions.chown(lib_path, self.service_user, self.service_user)
            else:
                if file_compare(source_lib_path, lib_path, shallow=False):
                    _print_color("TUTK IOTC library already installed", _COLOR_GREEN)
                else:
                    _print_color("Updating TUTK IOTC library.", _COLOR_CYAN)
                    copyfile(source_lib_path, lib_path)
                    _FilesystemActions.chown(lib_path, self.service_user, self.service_user)
        except Exception as e:
            _print_color(f"Error installing/updating TUTK IOTC library: {e}", _COLOR_RED)
            sys.exit(1)

    def install_mediamtx(self, version, path):
        """Installs or updates the mediamtx library."""
        CHANGED = False
        try:
            current_mtx_version = None

            mediamtx_bin=os.path.join(path,"mediamtx")
            if os.path.isfile(mediamtx_bin):
                try:
                    result = subprocess.run([mediamtx_bin, "--version"], capture_output=True, text=True)
                    if result.returncode == 0:
                        current_mtx_version = result.stdout.strip().split(" ")[-1].strip('v')
                except Exception as e:
                    _print_color(f"Error checking current mediamtx version: {e}", _COLOR_RED)

            mediamtx_git = _Github(author="bluenviron", repo_name="mediamtx")
            mediamtx_release = mediamtx_git.get_release(version=version, asset_pattern=f"linux_amd64")
            latest_mtx_tag = mediamtx_release.get('tag_name', '').lstrip('v')

            if current_mtx_version != latest_mtx_tag:
                if current_mtx_version == None:
                    _print_color(f"Installing mediamtx version: {latest_mtx_tag}.", _COLOR_CYAN)
                else:
                    _print_color(f"Updating mediamtx from: {current_mtx_version} to: {latest_mtx_tag}.", _COLOR_CYAN)
                tar_data = mediamtx_git.download_file(url=mediamtx_release["tarball"])
                _FilesystemActions.extract_tarball(tar_data=tar_data,path=path,file_name_contains="mediamtx")
                _FilesystemActions.chown(path, self.service_user, self.service_user)
                _FilesystemActions.chmod(mediamtx_bin, 0o755)
                _print_color(f"mediamtx version {latest_mtx_tag} installed successfully.", _COLOR_GREEN)
                CHANGED = True
            else:
                _print_color(f"mediamtx is already up-to-date.", _COLOR_GREEN)
            self.update_env_file(key="MTX_TAG", value=latest_mtx_tag)
        except urllib.error.URLError as e:
            _print_color(f"Error downloading mediamtx: {e}", _COLOR_RED)
            sys.exit(1)
        except subprocess.SubprocessError as e:
            _print_color(f"Error running subprocess: {e}", _COLOR_RED)
            sys.exit(1)
        except Exception as e:
            _print_color(f"Unexpected error: {e}", _COLOR_RED)
            sys.exit(1)
        return CHANGED

    def install_python_requirements(self):
        """Installs the Python requirements."""
        requirements_file = os.path.join(self.install_path, "requirements.txt")
        if os.path.isfile(requirements_file) == False:
            _print_color("Requirements file is missing. Something went wrong when installing docker-wyze-bridge", _COLOR_RED)
            sys.exit(1)
        try:
            _print_color("Installing Python requirements", _COLOR_CYAN)
            _exec_command(f'{self.venv_path}/bin/pip install --disable-pip-version-check -r {requirements_file}')
        except Exception as e:
            _print_color(f"Error installing Python requirements: {e}", _COLOR_RED)
            sys.exit(1)

    def patch_mediamtx_path(self, path):
        """Patches the mediamtx path in the configuration."""
        try:
            mtx_server_file = os.path.join(self.install_path, 'wyzebridge', 'mtx_server.py')
            if os.path.isfile(mtx_server_file):
                _print_color(f"Patching path to mediamtx in {mtx_server_file}", _COLOR_YELLOW)
                with open(mtx_server_file, 'r') as file:
                    data = file.read()
                data = data.replace('/app/mediamtx', os.path.join(path,"mediamtx"))
                with open(mtx_server_file, 'w') as file:
                    file.write(data)
        except Exception as e:
            _print_color(f"Error patching mediamtx path: {e}", _COLOR_RED)
            sys.exit(1)

    def update_env_file(self, key, value):
        """Updates the .env file with the specified key-value pair."""
        try:
            if not os.path.exists(self._env_file):
                _print_color(f"Error: .env file not found at {self._env_file}", _COLOR_RED)
                sys.exit(1)

            new_line = f"{key}={value}\n"
            with open(self._env_file, 'r') as env_file:
                env_content = env_file.readlines()

            key_exists = False
            for i, line in enumerate(env_content):
                if line.startswith(f"{key}="):
                    old_value = line.split('=')[1].strip()
                    if old_value != value:
                        _print_color(f"Updating {self._env_file}: {key} from: {old_value} to: {value}", _COLOR_YELLOW)
                    env_content[i] = new_line
                    key_exists = True
                    break

            if not key_exists:
                env_content.append(new_line)

            with open(self._env_file, 'w') as env_file:
                env_file.writelines(env_content)
        except Exception as e:
            _print_color(f"Error updating .env file: {e}", _COLOR_RED)
            sys.exit(1)

def run_install():
    """Performs the installation of the Wyze Bridge."""
    wyze_bridge = _WyzeBridgeInstallation(install_path=scriptConfig.APP_PATH, version=scriptConfig.APP_VERSION)
    dwb_git = _Github(author="mrlt8", repo_name="docker-wyze-bridge")
    latest_version_number = ""
    if scriptConfig.APP_VERSION == "latest":
        dwb_latest_release = dwb_git.get_release(version="latest")
        latest_version_number = dwb_latest_release.get('tag_name', '').strip('v')
    skip_app_install = False
    if wyze_bridge.installed:
        installed_version = wyze_bridge.get_installed_dwb_version()
        if installed_version != None:
            if installed_version == latest_version_number:
                _print_color(f"docker-wyze-bridge {installed_version} already installed at {scriptConfig.APP_PATH}", _COLOR_PURPLE)
                skip_app_install = True
            else:
                _print_color(f"docker-wyze-bridge {installed_version} found at {scriptConfig.APP_PATH}. You supplied version: {scriptConfig.APP_VERSION}", _COLOR_RED)
        else:
            _print_color("Unexpected error with existing docker-wyze-bridge install.", _COLOR_RED)

    wyze_bridge.create_service_user(scriptConfig.APP_USER)
    _FilesystemActions.create_application_folders(folders=['/img', '/tokens', scriptConfig.APP_PATH], service_user=scriptConfig.APP_USER)
    if skip_app_install == False: wyze_bridge.install_docker_wyze_bridge_app()
    wyze_bridge.create_pyvenv(path=os.path.join(wyze_bridge.user_home,".wyze-venv"))
    wyze_bridge.install_python_requirements()
    wyze_bridge.install_iotc_library()
    wyze_bridge.create_settings_file(scriptConfig.APP_CONF)
    wyze_bridge.install_mediamtx(version=scriptConfig.MEDIA_MTX_VERSION, path=scriptConfig.MEDIA_MTX_PATH)
    wyze_bridge.patch_mediamtx_path(scriptConfig.MEDIA_MTX_PATH)
    wyze_bridge.install_ffmpeg()

    if scriptConfig.APP_GUNICORN: wyze_bridge.install_gunicorn()

    if _SERVICE_MANAGER == "openrc": wyze_bridge.install_service_openrc()
    elif _SERVICE_MANAGER == "systemd": wyze_bridge.install_service_systemd()

    _FilesystemActions.chown(scriptConfig.APP_PATH, scriptConfig.APP_USER, scriptConfig.APP_USER)
    _print_color("Installation completed.", _COLOR_GREEN)
    if _SERVICE_MANAGER == "openrc":
        _print_color("Check log output at /var/log/wyze-bridge.log for wbadmin password, otherwise update configuration file to configure service.", _COLOR_CYAN)
    if _SERVICE_MANAGER == "systemd":
        _print_color("Check log ouput by running `journalctl -u wyze-bridge.service` for wbadmin password, otherwise update configuration file to configure service.", _COLOR_CYAN)
        restart_service()
    _print_color(f"!!WARNING!! Any changes made to the .env file in the application folder will be lost when the application is updated!", _COLOR_PURPLE)
    _print_color(f"Store any required configuration in {scriptConfig.APP_CONF}", _COLOR_GREEN)

def restart_service():
    """Restarts wyze-bridge service."""
    _print_color("Restarting wyze-bridge service.", _COLOR_PURPLE)
    if _SERVICE_MANAGER == "openrc": _exec_command('rc-service wyze-bridge restart')
    if _SERVICE_MANAGER == "systemd": _exec_command('systemctl restart wyze-bridge')

def run_update():
    """Performs the update of the Wyze Bridge."""

    _print_color("Checking for docker-wyze-bridge updates...", _COLOR_CYAN)
    dwb_git = _Github(author="mrlt8", repo_name="docker-wyze-bridge")
    dwb_release = dwb_git.get_release(version=scriptConfig.APP_VERSION)
    latest_ver_num = dwb_release.get('tag_name', '').strip('v')
    wyze_bridge = _WyzeBridgeInstallation(install_path=scriptConfig.APP_PATH, version=scriptConfig.APP_VERSION)
    wyze_bridge.create_service_user(scriptConfig.APP_USER)
    installed_ver_num = wyze_bridge.get_installed_dwb_version()

    if not latest_ver_num:
        _print_color(f"Error getting latest version info from: https://api.github.com/repos/mrlt8/docker-wyze-bridge/releases/latest", _COLOR_RED)
        sys.exit(1)

    DWB_UPDATED = False
    if installed_ver_num != latest_ver_num:
        _print_color(f"Updating docker-wyze-bridge from {installed_ver_num} to {latest_ver_num}.", _COLOR_GREEN)
        home_folder = os.path.expanduser(f'~{scriptConfig.APP_USER}')
        backup_path = os.path.join(home_folder, f'wyze-backups/v{installed_ver_num}-{datetime.now().strftime("%Y%m%d-%H%M")}')
        wyze_bridge.backup(output_path=backup_path)

        _print_color(f"Deleting old version of docker-wyze-bridge at: {scriptConfig.APP_PATH}", _COLOR_PURPLE)
        rmtree(scriptConfig.APP_PATH)
        wyze_bridge.install_docker_wyze_bridge_app()
        wyze_bridge.venv_path = os.path.join(wyze_bridge.user_home,".wyze-venv")
        wyze_bridge.install_python_requirements()

        _FilesystemActions.chown(scriptConfig.APP_PATH, scriptConfig.APP_USER, scriptConfig.APP_USER)
        DWB_UPDATED = True
    else:
        _print_color("docker-wyze-bridge is already up-to-date.", _COLOR_GREEN)

    MEDIAMTX_UPDATED = wyze_bridge.install_mediamtx(version=scriptConfig.MEDIA_MTX_VERSION, path=scriptConfig.MEDIA_MTX_PATH)
    if MEDIAMTX_UPDATED: wyze_bridge.patch_mediamtx_path(scriptConfig.MEDIA_MTX_PATH)

    if DWB_UPDATED or MEDIAMTX_UPDATED: return True
    else: return False


if __name__ == '__main__':
    _Prerequisites.is_root()
    _Prerequisites.python_version()

    scriptConfig = _Config()

    parser = argparse.ArgumentParser(description='Manage Wyze Bridge installation and updates.')
    parser.add_argument('action', choices=['install', 'update', 'show-settings'], help='Action to perform.')

    scriptConfig.create_arguments(parser)

    args = parser.parse_args()
    scriptConfig.parse_arguments(args)

    if args.action == 'show-settings':
        for key, value in scriptConfig.__dict__.items():
            try:
                desc = scriptConfig.get_description(key)
            except:
                continue
            _print_color(f"# {desc}",_COLOR_CYAN)
            _print_color(f"{key} = {value}\n",_COLOR_GREEN)
        sys.exit(0)

    scriptConfig.write_config_file()

    _Prerequisites.detect_service_manager()

    connected = _Prerequisites.internet_access()
    if not connected:
        _print_color("Error connecting to github.com", _COLOR_RED)
        sys.exit(1)

    if args.action == 'install':
        run_install()

    elif args.action == 'update':
        UPDATED = run_update()
        if UPDATED == True: restart_service()
