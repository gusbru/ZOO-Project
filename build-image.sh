#!/bin/bash
set -e

docker build \
  -t public.ecr.aws/k4l9p8h0/eoepca/zoo-project:0.0.47 \
  --build-arg CONDA_ENV_NAME=env_zoo_calrissian \
  --build-arg PY_VER=3.10 \
  --build-arg CONDA_ENV_FILE=https://raw.githubusercontent.com/gusbru/eoepca-proc-service-template/testArgoAdesV2/.devcontainer/environment.yml \
  --no-cache \
  -f docker/dru/Dockerfile  .

docker push public.ecr.aws/k4l9p8h0/eoepca/zoo-project:0.0.47
