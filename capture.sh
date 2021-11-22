#!/bin/bash

for ((i = 0 ; i < ${1:-100} ; i++)); do
	echo Capturing Image
	curl -X POST http://${3:-localhost}:${4:-8000}/
	sleep ${2:-10}
done
