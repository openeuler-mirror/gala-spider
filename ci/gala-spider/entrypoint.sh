#!/bin/bash

SPIDER_CONF="config/gala-spider.yaml"
TARGET_CONF_PATH="/etc/gala-spider/"

if [[ -n "$data_source" ]]; then
    sed -i "s/data_source: \"prometheus\"/data_source: \"${data_source}\"/g" $SPIDER_CONF
fi

if [[ -n "$prometheus_server" ]]; then
    sed -i "s/localhost:9090/${prometheus_server}/g" $SPIDER_CONF
fi

if [[ -n "$arangodb_server" ]]; then
    sed -i "s/localhost:8529/${arangodb_server}/g" $SPIDER_CONF
fi

if [[ -n "$kafka_server" ]]; then
    sed -i "s/localhost:9092/${kafka_server}/g" $SPIDER_CONF
fi

if [[ -n "$metadata_topic" ]]; then
    sed -i "s/gala_gopher_metadata/${metadata_topic}/g" $SPIDER_CONF
fi

if [[ -n "$log_level" ]]; then
    sed -i "s/log_level: INFO/log_level: ${log_level}/g" $SPIDER_CONF
fi

if [[ -n "$aom_server" ]]; then
    sed -i "s#base_url: \"\"#base_url: \"${aom_server}\"#g" $SPIDER_CONF
fi

if [[ -n "$aom_project_id" ]]; then
    sed -i "s/project_id: \"\"/project_id: \"${aom_project_id}\"/g" $SPIDER_CONF
fi

if [[ -n "$aom_auth_type" ]]; then
    sed -i "s/auth_type: \"token\"/auth_type: \"${aom_auth_type}\"/g" $SPIDER_CONF
fi

if [[ -n "$aom_app_code" ]]; then
    sed -i "s/app_code: \"\"/app_code: \"${aom_app_code}\"/g" $SPIDER_CONF
fi

if [[ -n "$iam_server" ]]; then
    sed -i "s#iam_server: \"\"#iam_server: \"${iam_server}\"#g" $SPIDER_CONF
fi

if [[ -n "$iam_domain" ]]; then
    sed -i "s/iam_domain: \"\"/iam_domain: \"${iam_domain}\"/g" $SPIDER_CONF
fi

if [[ -n "$iam_user_name" ]]; then
    sed -i "s/iam_user_name: \"\"/iam_user_name: \"${iam_user_name}\"/g" $SPIDER_CONF
fi

if [[ -n "$iam_password" ]]; then
    sed -i "s/iam_password: \"\"/iam_password: \"${iam_password}\"/g" $SPIDER_CONF
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
