#!/usr/bin/env python3
from flask import Flask
from time import sleep

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/5s_delay')
def slow_startup():
    sleep(5)
    return "5 second delay"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port="8080")

