## 如何新增观测对象

为了方便用户拓展新的观测对象，我们通过配置文件的方式来配置需要新增的观测对象的元数据信息，从而支持对新观测对象的采集和拓扑绘制能力。

需要配置的观测对象的元数据信息包括：
- 观测对象的类型
- 全局唯一标识该观测对象的一个观测实例的字段集合
- 观测对象的标签字段集合
- 观测对象的观测指标集合
- 观测对象所在的拓扑分层

下面以观测对象 `proc` 的为例，详细讲解如何配置新增的观测对象的元数据信息。当前系统默认支持的扩展到观测对象配置文件在 `gala-spider` 工程下的 [config/ext-observe-meta.yaml](../../../config/ext-observe-meta.yaml) 文件中。

### 1. 新增一个观测对象类型

`proc` 观测对象对应 Linux 内核中的一个进程。在配置文件中，`observe_entities` 是一个对象的列表，所有新增的观测对象元数据信息都在 `observe_entities` 下。

为此，我们在 `observe_entities` 下新增一个对象，并指定 `type: proc` 代表这是一个观测类型为 `proc` 的观测对象的配置信息。 `type` 是一个必选的配置字段。

配置结果如下：
```yaml
observe_entities:
  -
    type: proc
```

### 2. 配置观测对象的标识字段

一台主机上的 `proc` 可以通过进程ID `tgid` 进行标识，这台主机可以通过一个全局的机器ID `machine_id` 进行唯一标识。

因此，`proc` 观测对象的一个观测实例可通过 `tgid` 和 `machine_id` 全局唯一标识。我们将它们配置到 `keys` 字段中。`keys` 是一个必须的配置字段。

此时，配置结果为：
```yaml
observe_entities:
  -
    type: task
    keys:
      - pid
      - machine_id
```

### 3. 配置观测对象的标签字段

`proc` 还有一些非标识类的标签信息。比如进程名 `comm` ，进程组ID `pgid` 等信息。如果 `proc` 运行在一个容器中，它还包括一个所在的容器ID `container_id` 信息。

这些标签信息可以配置到 `labels` 字段中。`labels` 是一个可选的配置字段。

此时，配置结果为：
```yaml
observe_entities:
  -
    type: proc
    keys:
      - tgid
      - machine_id
    labels:
      - comm
      - pgid
      - container_id
```

### 4. 配置观测对象的观测指标字段

`proc` 包含若干的观测指标：比如进程调用 fork 的次数 `fork_count`，进程每秒读/写IO的字节数 `rchar_bytes/wchar_bytes` 等。这些指标字段都在 `metrics` 中进行配置。如果 spider 的数据源是 Prometheus ，则 `metrics` 中至少需要配置一个指标字段，否则无法从 Prometheus 采集数据。

此时，配置结果为，
```yaml
observe_entities:
  -
    type: proc
    keys:
      - tgid
      - machine_id
    labels:
      - comm
      - pgid
      - container_id
    metrics:
      - fork_count
      - rchar_bytes
      - wchar_bytes
```

### 5. 配置观测对象所在的拓扑分层

该配置信息在绘制观测对象之间的3D拓扑关系图功能时会用到。拓扑分层通过 `level` 字段进行配置，是一个可选的配置字段。

`proc` 对应于拓扑分层的进程层 `PROCESS` ，所以添加一行配置内容：

```yaml
level: PROCESS
```

当前系统支持的拓扑分层有，
```
- HOST
- PROCESS
- RPC
```

### 一个完整的观测对象的配置结果

`proc` 最终的配置信息为：

```yaml
observe_entities:
  -
    type: proc
    keys:
      - tgid
      - machine_id
    labels:
      - comm
      - pgid
      - container_id
    metrics:
      - fork_count
      - rchar_bytes
      - wchar_bytes
    level: PROCESS
```

当我们需要给一个观测对象添加新的指标字段、标签字段等信息时，只需要在配置文件中添加相应的配置即可。这种方式提供了很好的可扩展性。



## 如何新增拓扑关系

### 关系类型定义

拓扑关系，或关联关系，定义了观测对象之间存在的物理上和逻辑上的关系。关联关系可分为两种：一种是直接的（direct）关联关系，是指物理上直观可见的关系；另一种是间接的（indirect）关联关系，是指在物理上不存在但逻辑上可建立的关系。

gala-spider 目前支持的直接关联关系有：

| 关系名称   | 关系描述                                                     |
| ---------- | ------------------------------------------------------------ |
| runs_on    | 运行关系。例如，进程运行在主机上，则有关系：进程 runs_on 主机。 |
| belongs_to | 从属关系。例如，通信端点是从属于某个进程，则有关系：通信端点 belongs_to 进程。 |
| is_server  | 服务端通信关系。例如，nginx记录了一条和服务端tcp的连接，则有关系：服务端tcp连接 is_server nginx连接。 |
| is_client  | 客户端通信关系。例如，nginx记录了一条和客户端tcp的连接，则有关系：客户端tcp连接 is_client nginx连接。 |
| is_peer    | 对端通信关系。例如，客户端与服务端建立了一条tcp连接，则有关系：客户端tcp连接 is_peer 服务端tcp连接。反之亦然。 |


支持的间接关联关系有：

| 关系名称 | 关系描述                                                     |
| -------- | ------------------------------------------------------------ |
| connect  | 连接关系。例如，主机A和主机B上有tcp连接进行通信，则有关系：主机A connect 主机B 。 |

例如，观测对象 `proc` 与其他观测对象有多种关联关系。比如：`proc runs_on host` 表示进程运行在某个主机上，`proc runs_on container` 表示进程运行在某个容器上，`proc connect proc` 表示进程与另一个进程具有间接的连接关系。

### 新增拓扑关系

关系类型定义好后，我们可以通过配置文件的方式新增拓扑关系，下面结合一个例子讲解如何新增拓扑关系。当前系统默认支持的拓扑关系在 `gala-spider` 工程下的 [config/topo-relation.yaml](../../../config/topo-relation.yaml) 配置文件中。

对于 `proc` 的一个拓扑关系 `proc runs_on host` ，对应的配置内容如下。

```yaml
topo_relations:
  -
    type: proc
    dependingitems:
      -
        id: runs_on
        layer: direct
        toTypes:
          -
            type: host
            matches:
              -
                from: machine_id
                to: machine_id
```

其中，`matches` 配置表明：当 `task.machine_id == host.machine_id` 成立时，关联关系 `task runs_on host` 成立。下面详细介绍相关的配置项。

首先，所有的关联关系都在 `topo_relations` 下定义，它是一个列表，列表中的每一项配置了一个观测对象类型（通过 `type` 字段标识，必选字段）包含的所有关联关系。 `proc` 的多个关联关系可通过 `dependingitems` 字段进行配置。`dependingitems` 是一个关联关系的列表，列表中的每一项配置对应一种关联关系，其中 `proc` 作为该关联关系的关系主体。
例如，对于一条关联关系 `proc runs_on host` ，我们把 `proc` 称作关联关系 `runs_on` 的关系主体，`host` 称作关联关系 `runs_on` 的关系客体。

每一条关联关系的配置信息包括如下字段：

- `id` ：关系名称。
- `layer` ：关系类型。值的范围为：`direct` 和 `indirect` ，分别表示直接关系和间接关系。
- `toTypes` ：关系客体的配置信息。它是一个列表，列表中的每一项对应一个关系客体的配置信息，内容为，
  - `type` : 关系客体对应的观测对象类型。
  - `matches` ：直接的关联关系可以通过观测对象的标识字段、标签字段等进行匹配。
    `matches` 字段配置了这种字段匹配的信息，它是一个列表，列表中的每一项表示一条匹配，
    具体内容为，
    - `from` ：关系主体的字段名称。
    - `to` ：关系客体的字段名称。
  - `requires` ：有一些关联关系成立的条件是要求关系主体或关系客体的某些字段的值为特定的值。
    `requires` 字段配置了这种约束条件。它是一个列表，列表中的每一项表示一个约束条件，具体内容为，
    - `side` ：约束的对象是关系主体还是关系客体。取值为：`from` 和 `to` ，分别表示关系主体和关系客体。
    - `label` ：约束的字段名称。
    - `value` ：约束的字段值。

### 支持的拓扑关系

当前系统默认支持的拓扑关系包括：

| 关系主体    | 关系类型   | 关系客体    | 关系描述                         |
| ----------- | ---------- | ----------- | -------------------------------- |
| host        | connect    | host        | 一台主机与另一台主机的连接关系。 |
| container   | connect    | container   | 一个容器与另一个容器的连接关系。 |
| proc        | connect    | proc        | 一个进程与另一个进程的连接关系。 |
| container   | runs_on    | host        | 一个容器运行在一台主机上。       |
| proc        | runs_on    | host        | 一个进程运行在一台主机上。       |
| proc        | belongs_to | appinstance | 一个进程归属于一个应用实例。     |
| proc        | belongs_to | container   | 一个进程归属于一个容器。         |
| thread      | belongs_to | proc        | 一个线程归属于一个进程。         |
| endpoint    | belongs_to | proc        | 一个通信端口归属于一个进程。     |
| tcp_link    | belongs_to | proc        | 一个 tcp 连接归属于一个进程。    |
| sli         | belongs_to | proc        | 一个 sli 归属于一个进程。        |
| cpu         | belongs_to | host        | 一个 cpu 归属于一台主机。        |
| nic         | belongs_to | host        | 一个网卡归属于一台主机。         |
| qdisc       | belongs_to | nic         | 一个 qdisc 归属于一个网卡。      |
| disk        | belongs_to | host        | 一个磁盘归属于一台主机。         |
| block       | belongs_to | disk        | 一个块设备归属于一个磁盘。       |
| file_system | belongs_to | host        | 一个文件系统归属于一台主机。     |
| tcp_link    | is_peer    | tcp_link    | 一个 tcp 连接的对端 tcp 连接。   |

