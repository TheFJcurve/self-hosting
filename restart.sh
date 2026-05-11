#!/bin/bash

cur_dir=$(pwd)
docker_compose_files=$(ls -d */)

for sh_dir in $docker_compose_files; do
	cd $cur_dir/$sh_dir
	docker-compose down
	sleep 1
	docker-compose up -d
done

cd $cur_dir

echo 'Done Restarting Containers!'
