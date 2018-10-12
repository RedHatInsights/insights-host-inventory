FROM python:3

RUN mkdir /code
WORKDIR /code
ADD . /code
RUN pip install .[develop]
