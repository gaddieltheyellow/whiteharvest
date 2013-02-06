#!/bin/bash

cur=$(dirname $0)
pylint --rcfile $cur/.pylintrc $cur/whiteharvest.py
