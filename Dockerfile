FROM bitnami/minideb:stretch

RUN install_packages python3 python3-pip

# RUN apt update

# RUN apt upgrade -y

# RUN apt-get install cmake build-essential ffmpeg libsm6 libxext6  -y

WORKDIR /app

COPY requirements.txt ./

RUN pip3 install -r requirements.txt

COPY camera.py ./

ENV HOME=/app

EXPOSE 8000

CMD ["python3", "camera.py"]
