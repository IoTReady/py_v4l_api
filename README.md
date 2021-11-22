# Uses V4L2 to modify camera controls and capture frames

## Development

```
git clone git@github.com:IoTReady/aira_camera_api.git
cd repo_url
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_nuitka.txt
python app.py
```

## Build Binary
- Generates a release binary and copies it to $PWD

```
./build.sh
./app.bin
```

## Build Docker Image

```
docker build -t iotready/camera .
docker run --device=/dev/video0 -p 8000:8000 iotready/camera
```


## Usage

- Health check: `curl http://localhost:8000`
- Capture image: `./capture 1 0`

## TODO

- [x] Working camera capture
- [x] Working API
- [x] Working single file executable with Nuitka
- [x] Docker image
- [x] Generate images of dimension `2448 x 2448`
