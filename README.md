# wyze-bridge
Install [docker-wyze-bridge](https://github.com/mrlt8/docker-wyze-bridge), but without using docker. Designed for LXC or VM, to avoid nested virtualization.

wyze-bridge.py will download and install (or update to) the latest version of docker-wyze-bridge and as well as it's dependcy: [mediamtx](https://github.com/bluenviron/mediamtx).
If ffmpeg is not installed, it'll install the latest version of [ffmpeg-for-homebridge](https://github.com/homebridge/ffmpeg-for-homebridge).
It'll configure the appropriate system service (openrc/systemd), and accommodates running the service using Flask or gunicorn.

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
 - INSTALLATION_CONF: Path to file containing settings of this script, used for updates. DEFAULT: /etc/wyze-bridge/install.json
 - APP_CONF: Path to env file containing docker-wyze-bridge settings. DEFAULT: /etc/wyze-bridge/app.env
 - APP_GUNICORN: Use Gunicorn for frontend service. DEFAULT: False
 - APP_IP: IP address on which docker-wyze-bridge will listen. DEFAULT: 0.0.0.0
 - APP_PATH: Location of docker-wyze-bridge application. DEFAULT: /srv/wyze-bridge
 - APP_PORT: Port on which docker-wyze-bridge will listen. DEFAULT: 5000
 - APP_USER: User account used to run the docker-wyze-bridge. DEFAULT: wyze
 - APP_VERSION: Version of docker-wyze-bridge to install. DEFAULT: latest
 - MEDIA_MTX_VERSION: Version of mediamtx to install. DEFAULT: latest
 - MEDIA_MTX_PATH: Location of mediamtx application. DEFAULT: /srv/mediamtx

Example: `python3 wyze-bridge.py install --APP_IP 127.0.0.1 --APP_PORT 8080 --APP_USER gizzor --APP_VERSION 2.10.1 --APP_GUNICORN 1`
