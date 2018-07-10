FROM python:3

RUN mkdir /code
WORKDIR /code
ADD . /code
RUN pip install pipenv
RUN pipenv install --dev --python /usr/local/bin/python
