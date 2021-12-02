import os
import logging
import flask
import typer
from sys import exit
from io import BytesIO
from datetime import datetime
from subprocess import call
from PIL import Image, ImageStat
from v4l2py import Device
from mdns import init_service

app = flask.Flask(__name__)
log = logging.getLogger(__name__)

cam = None
stream = None 

default_host = "0.0.0.0"
g_width = 3264
g_height = 2448
g_xoffset = 408
g_yoffset = 0
g_path = "/tmp"

g_enable_single_color_rejection = True
g_enable_brightness_optimisation = True
g_enable_hue_optimisation = False
g_enable_contrast_optimisation = True

g_brightness_optimal = 37
g_brightness_diff = 2
g_exposure_auto = False
g_exposure_absolute = 300
g_exposure_absolute_min = 25
g_exposure_absolute_max = 1000
g_exposure_absolute_step = 25
brightness_slope = 1
brightness_intercept = 0
best_brightness_diff = 1E10
best_exposure = 0

g_hue_min = 80
g_hue_max = 150

g_contrast_optimal = 30
g_contrast_diff = 3
g_contrast_control = 32
g_contrast_control_min = 32
g_contrast_control_max = 48
g_contrast_control_step = 2

g_max_attempts = 50


def success(result):
    payload = {"ok": True, **result}
    log.debug(payload)
    return payload


def error(message: str):
    payload = {"ok": False, "time": datetime.now(), "message": message}
    log.error(payload)
    return payload


def estimate_brightness(img):
    im = img.convert('L')
    stat = ImageStat.Stat(im)
    return stat.rms[0]


def estimate_hue(img):
    im = img.convert('HSV')
    stat = ImageStat.Stat(im)
    return stat.mean[0]


def estimate_contrast(img):
    im = img.convert('L')
    stat = ImageStat.Stat(im)
    return stat.stddev[0]


def calc_optimal_exposure():
    print("Calculating optimal exposure")
    global brightness_slope
    global brightness_intercept
    global g_exposure_absolute
    global best_brightness_diff
    g_exposure_absolute = g_exposure_absolute_min
    r1 = capture_and_calculate()
    g_exposure_absolute = g_exposure_absolute_max
    # Reset diff before next capture
    best_brightness_diff = 1E10
    r2 = capture_and_calculate()
    brightness_slope = (r2['brightness'] - r1['brightness']) / \
        (g_exposure_absolute_max - g_exposure_absolute_min)
    brightness_intercept = r2['brightness'] - \
        brightness_slope * g_exposure_absolute_max
    g_exposure_absolute = int(
        (g_brightness_optimal - brightness_intercept)/brightness_slope)
    # This is a hack to account for the camera not giving us accurate images/exposures
    if g_exposure_absolute <= g_exposure_absolute_min or g_exposure_absolute >= g_exposure_absolute_max:
        g_exposure_absolute = int(
            (g_exposure_absolute_min + g_exposure_absolute_max)/2)
    print(f"\nOptimal Exposure: {g_exposure_absolute}\n")


def capture_and_calculate():
    cam.video_capture.set_exposure(g_exposure_absolute)
    cam.video_capture.set_contrast(g_contrast_control)
    # Skip one frame
    next(stream)
    image_bytes = BytesIO(next(stream))
    image = Image.open(image_bytes)
    width = image.size[0]
    height = image.size[1]
    image = image.crop((g_xoffset, g_yoffset, width -
                       g_xoffset, height - g_yoffset))
    result = {
        "exposure": g_exposure_absolute,
        "contrast_control": g_contrast_control,
        "image": image_bytes,
        "brightness": estimate_brightness(image),
        "contrast": estimate_contrast(image),
        "hue": estimate_hue(image)
    }
    return result


def optimise():
    global g_exposure_absolute
    global g_contrast_control
    global best_exposure
    best_brightness_diff = 1E10
    ret = {}
    count = 0
    for count in range(0, g_max_attempts):
        ret = capture_and_calculate()
        print(f"{ret}")
        brightness = ret['brightness']
        hue = ret['hue']
        contrast = ret['contrast']
        brightness_diff = g_brightness_optimal - brightness
        contrast_diff = g_contrast_optimal - contrast
        if abs(brightness_diff) < abs(best_brightness_diff):
            # An optimisation was found
            best_brightness_diff = brightness_diff
            best_exposure = g_exposure_absolute
        is_brightness_optimised = not(g_enable_brightness_optimisation) or abs(
            brightness_diff) <= g_brightness_diff
        is_hue_optimised = not(g_enable_hue_optimisation) or not (g_hue_min <= hue <= g_hue_max) 
        is_contrast_optimised = not(g_enable_contrast_optimisation) or abs(
            contrast_diff) <= g_contrast_diff
        if not (is_brightness_optimised and is_hue_optimised and is_contrast_optimised):
            if not is_brightness_optimised:
                g_exposure_absolute += int((brightness_diff /
                                            abs(brightness_diff))*g_exposure_absolute_step)
                if g_exposure_absolute > g_exposure_absolute_max:
                    g_exposure_absolute = g_exposure_absolute_max
                elif g_exposure_absolute < g_exposure_absolute_min:
                    g_exposure_absolute = g_exposure_absolute_min
            if not is_contrast_optimised:
                g_contrast_control += int((contrast_diff /
                                           abs(contrast_diff))*g_contrast_control_step)
                if g_contrast_control > g_contrast_control_max:
                    g_contrast_control = g_contrast_control_max
                elif g_contrast_control < g_contrast_control_min:
                    g_contrast_control = g_contrast_control_min
        else:
            print("\nOptimised!\n")
            g_exposure_absolute = best_exposure
            break
    now = int(datetime.now().timestamp())
    tmppath = f"/tmp/{now}.jpg"
    fpath = f"{g_path}/{now}.jpg"
    image = ret.pop('image')
    with open(tmppath, 'wb') as f:
        f.write(image.getbuffer())
    # Only needed until we figure out how to use crop directly within v4l2
    call(f"convert {tmppath} -crop {g_width-2*g_xoffset}x{g_height-2*g_yoffset}+{g_xoffset}+{g_yoffset} {fpath}", shell=True)
    ret['path'] = fpath
    ret['attempts'] = count + 1
    return ret


@app.get("/")
def index():
    result = {"time": datetime.now()}
    return success(result)


@app.post("/")
def trigger():
    result = optimise()
    return success(result)


@app.post("/logs")
def store_logs():
    print(flask.request.json)
    log.debug(flask.request.json)
    return success({})

def start(
        host: str = default_host,
        port: int = 8000,
        device: int = 0,
        width: int = 3264,
        height: int = 2448,
        xoffset: int = g_xoffset,
        yoffset: int = g_yoffset,
        skip: int = 2,
        max_attempts: int = g_max_attempts,
        brightness_optimal: int = g_brightness_optimal,
        brightness_diff: int = g_brightness_diff,
        enable_single_color_rejection: bool = g_enable_single_color_rejection,
        enable_brightness_optimisation: bool = g_enable_brightness_optimisation,
        enable_hue_optimisation: bool = g_enable_hue_optimisation,
        enable_contrast_optimisation: bool = g_enable_contrast_optimisation,
        path: str = g_path,
        hue_min: int = g_hue_min,
        hue_max: int = g_hue_max,
        contrast_optimal: int = g_contrast_optimal,
        contrast_diff: int = g_contrast_diff,
        contrast_control_min: int = g_contrast_control_min,
        contrast_control_max: int = g_contrast_control_max,
        contrast_control_step: int = g_contrast_control_step,
        exposure_absolute_min: int = g_exposure_absolute_min,
        exposure_absolute_max: int = g_exposure_absolute_max,
        exposure_absolute_step: int = g_exposure_absolute_step,
        exposure_auto: bool = typer.Option(g_exposure_auto),
        version: bool = typer.Option(False),
        servicename: str = "camera",
        logfile: str = "accumen_camera.log",
):
    if version:
        print("0.1.0")
        exit(0)
    global g_path
    global g_xoffset
    global g_yoffset
    global g_enable_single_color_rejection
    global g_enable_brightness_optimisation
    global g_enable_hue_optimisation
    global g_enable_contrast_optimisation
    global g_brightness_optimal
    global g_brightness_diff
    global g_hue_min
    global g_hue_max
    global g_contrast_optimal
    global g_contrast_diff
    global g_contrast_control_min
    global g_contrast_control_max
    global g_contrast_control_step
    global g_exposure_absolute_min
    global g_exposure_absolute_max
    global g_exposure_absolute_step
    global g_exposure_auto
    global g_max_attempts
    global cam
    global stream
    g_xoffset = xoffset
    g_yoffset = yoffset
    g_enable_single_color_rejection = enable_single_color_rejection
    g_enable_brightness_optimisation = enable_brightness_optimisation
    g_enable_hue_optimisation = enable_hue_optimisation
    g_enable_contrast_optimisation = enable_contrast_optimisation
    g_hue_min = hue_min
    g_hue_max = hue_max
    g_contrast_optimal = contrast_optimal
    g_contrast_diff = contrast_diff
    g_contrast_control_min = contrast_control_min
    g_contrast_control_max = contrast_control_max
    g_contrast_control_step = contrast_control_step
    g_brightness_optimal = brightness_optimal
    g_brightness_diff = brightness_diff
    g_exposure_auto = exposure_auto
    g_exposure_absolute_min = exposure_absolute_min
    g_exposure_absolute_max = exposure_absolute_max
    g_exposure_absolute_step = exposure_absolute_step
    g_path = path
    g_max_attempts = max_attempts
    assert os.path.exists(g_path), f"Directory '{g_path}' does not exist"
    logging.basicConfig(
        level=logging.DEBUG,
        filename=logfile,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    if host == default_host:
        init_service(host=None, port=port, name=servicename)
    else:
        init_service(host=host, port=port, name=servicename)
    print("Starting Camera")
    with Device.from_id(device) as cam:
        # Camera is now open and locked.
        # And it's held open until we close it
        cam.video_capture.set_format(width, height, "MJPG")
        # WIP: Cropping does not appear to be supported by this camera.
        #cam.video_capture.set_crop(xoffset, yoffset, width, height)
        stream = iter(cam)
        # Camera is started once we call next(stream)
        # We skip a few frames at the start
        for i in range(skip):
            next(stream)
        calc_optimal_exposure()
        app.run(host=host, port=port)

if __name__ == "__main__":
    typer.run(start)
