FROM python:3.7-slim-buster

MAINTAINER "algorithmofdish"<hexiujun1@huawei.com>

WORKDIR /home/gala-inference

ENV PYTHONPATH "${PYTHONPATH}:./"

COPY requirements.txt requirements.txt
COPY spider ./spider/
COPY cause_inference ./cause_inference/
COPY config/gala-inference.yaml config/ext-observe-meta.yaml config/infer-rule.yaml config/cause-keyword.yaml ./config/

COPY ci/gala-inference/entrypoint.sh /
RUN chmod +x /entrypoint.sh

# config pip source
# RUN pip3 config set global.index-url https://mirrors.tools.huawei.com/pypi/simple \
#     && pip3 config set install.trusted-host mirrors.tools.huawei.com
RUN pip3 install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "/entrypoint.sh" ]

CMD [ "python3", "./cause_inference/__main__.py" ]
