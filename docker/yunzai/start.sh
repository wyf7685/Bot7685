#!/bin/bash

redis-server --port 6379 --save 900 1 --save 300 10 --daemonize yes
gosu yunzai node app
