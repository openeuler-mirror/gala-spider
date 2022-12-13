#  配置文件介绍

## gala-spider配置

### 配置文件说明

gala-spider 配置文件 `/etc/gala-spider/gala-spider.yaml` 配置项说明如下。

- global：全局配置信息
  - data_source：指定观测指标采集的数据库，当前支持 prometheus，aom 。
  - data_agent：指定观测指标采集代理，当前只支持 gala_gopher
- spider：
  - log_conf：日志配置信息
    - log_path：日志文件路径
    - log_level：日志打印级别，值包括 DEBUG/INFO/WARNING/ERROR/CRITICAL 。
    - max_size：日志文件大小，单位为兆字节（MB）。
    - backup_count：日志备份文件数量
- storage：拓扑图存储服务的配置信息
  - period：存储周期，单位为秒，表示每隔多少秒存储一次拓扑图。
  - database：存储的图数据库，当前只支持 arangodb 。
  - db_conf：图数据库的配置信息
    - url：图数据库的服务器地址
    - db_name：拓扑图存储的数据库名称
- kafka：kafka配置信息
  - server：kafka服务器地址
  - metadata_topic：观测对象元数据消息的topic名称
  - metadata_group_id：观测对象元数据消息的消费者组ID
- prometheus：prometheus数据库配置信息
  - base_url：prometheus服务器地址
  - instant_api：单个时间点采集API
  - range_api：区间采集API
  - step：采集时间步长，用于区间采集API
  
- aom：华为云对接指标数据库的配置信息

  - base_url：aom服务器地址

  - project_id：aom项目ID

  - auth_type：aom服务器鉴权类型，支持 token 、appcode 两种方式。

  - auth_info：aom服务器鉴权配置信息

    对于 token 鉴权方式，包括如下配置，

    - iam_server：iam服务器
    - iam_domain：iam域
    - iam_user_name：iam用户名
    - iam_password：iam用于密码
    - ssl_verify：是否开启 SSL 证书验证，默认为 0 表示关闭。

    对于 appcode 鉴权方式，包括如下配置，

    - appcode


### 配置文件示例

```yaml
global:
    data_source: "prometheus"
    data_agent: "gala_gopher"

prometheus:
    base_url: "http://localhost:9090/"
    instant_api: "/api/v1/query"
    range_api: "/api/v1/query_range"
    step: 1

spider:
    log_conf:
        log_path: "/var/log/gala-spider/spider.log"
        # log level: DEBUG/INFO/WARNING/ERROR/CRITICAL
        log_level: INFO
        # unit: MB
        max_size: 10
        backup_count: 10

storage:
    # unit: second
    period: 60
    database: arangodb
    db_conf:
        url: "http://localhost:8529"
        db_name: "spider"

kafka:
    server: "localhost:9092"
    metadata_topic: "gala_gopher_metadata"
    metadata_group_id: "metadata-spider"
```



## gala-inference配置

### 配置文件说明

gala-inference 配置文件 `/etc/gala-inference/gala-inference.yaml` 配置项说明如下。

- inference：根因定位算法的配置信息
  - tolerated_bias：异常时间点的拓扑图查询所容忍的时间偏移，单位为秒。
  - topo_depth：拓扑图查询的最大深度
  - root_topk：根因定位结果输出前 K 个根因指标
  - infer_policy：根因推导策略，包括 dfs 。
  - evt_valid_duration：根因定位时，系统异常指标事件的有效历史周期，单位为秒。
  - evt_future_duration：根因定位时，系统异常指标事件的有效未来周期，单位为秒。
  - evt_aging_duration：根因定位时，系统异常指标事件的老化周期，单位为秒。
- kafka：kafka配置信息
  - server：kafka服务器地址
  - metadata_topic：观测对象元数据消息的配置信息
    - topic_id：观测对象元数据消息的topic名称
    - group_id：观测对象元数据消息的消费者组ID
  - abnormal_kpi_topic：异常 KPI 事件消息的配置信息。
    - topic_id：异常 KPI 事件消息的topic名称
    - group_id：异常 KPI 事件消息的消费者组ID
    - consumer_to：消费异常 KPI 事件消息的超时时间，单位为秒。
  - abnormal_metric_topic：系统异常指标事件消息的配置信息
    - topic_id：系统异常指标事件消息的topic名称
    - group_id：系统异常指标事件消息的消费者组ID
    - consumer_to：消费系统异常指标事件消息的超时时间，单位为秒。
  - inference_topic：根因定位结果输出事件消息的配置信息
    - topic_id：根因定位结果输出事件消息的topic名称
- arangodb：arangodb图数据库的配置信息，用于查询根因定位所需要的拓扑子图。
  - url：图数据库的服务器地址
  - db_name：拓扑图存储的数据库名称
- log_conf：日志配置信息
  - log_path：日志文件路径
  - log_level：日志打印级别，值包括 DEBUG/INFO/WARNING/ERROR/CRITICAL 。
  - max_size：日志文件大小，单位为兆字节（MB）。
  - backup_count：日志备份文件数量
- prometheus：prometheus数据库配置信息，用于获取指标的历史时序数据。
  - base_url：prometheus服务器地址
  - range_api：区间采集API
  - sample_duration：指标的历史数据的采样周期，单位为秒。
  - step：采集时间步长，用于区间采集API。

### 配置文件示例

```yaml
inference:
  # 异常时间点的拓扑图查询所容忍的时间偏移，单位：秒
  tolerated_bias: 120
  topo_depth: 10
  root_topk: 3
  infer_policy: "dfs"
  # 根因定位时，有效的异常指标事件周期，单位：秒
  evt_valid_duration: 120
  # 异常指标事件的老化周期，单位：秒
  evt_aging_duration: 600

kafka:
  server: "localhost:9092"
  metadata_topic:
    topic_id: "gala_gopher_metadata"
    group_id: "metadata-inference"
  abnormal_kpi_topic:
    topic_id: "gala_anteater_hybrid_model"
    group_id: "abn-kpi-inference"
  abnormal_metric_topic:
    topic_id: "gala_anteater_metric"
    group_id: "abn-metric-inference"
    consumer_to: 1
  inference_topic:
    topic_id: "gala_cause_inference"

arangodb:
  url: "http://localhost:8529"
  db_name: "spider"

log:
  log_path: "/var/log/gala-inference/inference.log"
  # log level: DEBUG/INFO/WARNING/ERROR/CRITICAL
  log_level: INFO
  # unit: MB
  max_size: 10
  backup_count: 10

prometheus:
  base_url: "http://localhost:9090/"
  range_api: "/api/v1/query_range"
  # 单位： 秒
  sample_duration: 600
  step: 5
```