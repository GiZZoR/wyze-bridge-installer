# wyze-bridge

## Purpose
I wrote wyze-bridge.py to install the app [docker-wyze-bridge](https://github.com/mrlt8/docker-wyze-bridge) natively, not using docker.
This is useful for those who use other virtualization methods (lxc, kvm), and don't want to (or can't) run nested virtualization.

## Script explanation
When using the `install` action, this script will download the app from the latest release of [docker-wyze-bridge](https://github.com/mrlt8/docker-wyze-bridge), and install it to `/srv/wyze-bridge`.

It'll create a service account called `wyze`, and install the required Python modules into a virtual environment (venv) in the service account's home folder.

It also installs the latest version of [mediamtx](https://github.com/bluenviron/mediamtx) and installs it to `/srv/mediamtx`.

If ffmpeg is not found on your system, it'll install the latest release of [ffmpeg-for-homebridge](https://github.com/homebridge/ffmpeg-for-homebridge).

To keep your customized configuration from being overwritten, a separate environment (settings) file is created at `/etc/wyze-bridge/app.env`.


The script also includes an `update` action, that will update mediamtx and docker-wyze-bridge to the latest versions.

## Requirements
- Python 3.10 or newer
- On debian/ubuntu: appropriate python-venv package

## Usage

### Installation
Download the script, eg: `wget https://github.com/GiZZoR/wyze-bridge-installer/raw/refs/heads/main/wyze-bridge.py`

Run the script with the "install" action, eg: `python3 wyze-bridge.py install`

### Update
Run the script with the "update" action, eg: `python3 wyze-bridge.py update`

### Settings
You can view the settings for the script by running: `python3 wyze-bridge.py show-settings`

Available command line options:
| Parameter | Description | Default Value |
| ------------- | ------------- | ------------- |
| --APP_CONF | Path to env file containing docker-wyze-bridge settings. | /etc/wyze-bridge/app.env |
| --APP_GUNICORN | Use Gunicorn for frontend service. | False |
| --APP_IP | IP address on which docker-wyze-bridge will listen. | 0.0.0.0 |
| --APP_PATH | Location of docker-wyze-bridge application. | /srv/wyze-bridge |
| --APP_PORT | Port on which docker-wyze-bridge will listen. | 5000 |
| --APP_USER | User account used to run the docker-wyze-bridge. | wyze |
| --APP_VERSION | Version of docker-wyze-bridge to install. | latest |
| --MEDIA_MTX_VERSION | Version of mediamtx to install. | latest |
| --MEDIA_MTX_PATH | Location of mediamtx application. | /srv/mediamtx |
| --INSTALLATION_CONF | Path to file containing settings of this script, used for updates. | /etc/wyze-bridge/install.json |

Example: `python3 wyze-bridge.py install --APP_IP 127.0.0.1 --APP_PORT 8080 --APP_USER gizzor --APP_VERSION 2.10.1 --APP_GUNICORN 1`
