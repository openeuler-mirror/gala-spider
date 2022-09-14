#!/bin/bash

INFER_CONF="config/gala-inference.yaml"
TARGET_CONF_PATH="/etc/gala-inference/"

if [[ -n "$prometheus_server" ]]; then
    sed -i "s/localhost:9090/${prometheus_server}/g" $INFER_CONF
fi

if [[ -n "$arangodb_server" ]]; then
    sed -i "s/localhost:8529/${arangodb_server}/g" $INFER_CONF
fi

if [[ -n "$kafka_server" ]]; then
    sed -i "s/localhost:9092/${kafka_server}/g" $INFER_CONF
fi

if [[ -n "$log_level" ]]; then
    sed -i "s/log_level: INFO/log_level: ${log_level}/g" $INFER_CONF
fi

# copy config file to target path
if [ ! -d "${TARGET_CONF_PATH}" ]; then
    mkdir -p ${TARGET_CONF_PATH}
fi

for conf_file in `ls config/`; do
    if [ ! -f "${TARGET_CONF_PATH}${conf_file}" ]; then
        cp config/${conf_file} ${TARGET_CONF_PATH}
    fi
done

exec "$@"
