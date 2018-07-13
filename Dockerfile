FROM python:3

RUN pip install pipenv
RUN mkdir /code
WORKDIR /code
ADD . /code
RUN pipenv install --python /usr/local/bin/python
