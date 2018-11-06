FROM python:3.6

WORKDIR /usr/src/app
COPY . ./
RUN pip install -r requirements.txt
CMD ['python', './run.py']
