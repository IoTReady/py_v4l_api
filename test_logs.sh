#!/bin/bash

for ((i = 0 ; i < ${1:-100} ; i++)); do
	echo Storing Log
	curl -X POST http://${3:-localhost}:${4:-8000}/logs -H 'Content-Type: application/json' -d '{"uptime": 100}'
	sleep ${2:-10}
done
