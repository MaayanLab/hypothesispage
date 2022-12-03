FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

#RUN pip install --upgrade pip

RUN apt-get update
RUN apt-get -y install \
    python3-pip \
	vim \
	wget \
	gcc \
	musl-dev \
    g++
	
RUN mkdir -p /hype
WORKDIR /hype

COPY requirements.txt /hype
RUN pip3 install -r requirements.txt

COPY main.py /hype
ADD static /hype/static
ADD templates /hype/templates

EXPOSE 5050

ENTRYPOINT ["uvicorn", "main:app", "--port", "5557", "--host", "0.0.0.0", "--proxy-headers"]
