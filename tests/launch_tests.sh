#!/usr/bin/env bash

pycodestyle --first webserver.py
python3 -m doctest -v webserver.py