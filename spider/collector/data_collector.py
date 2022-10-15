from typing import List
from typing import Any
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from dataclasses import field


@dataclass
class Label:
    name: str
    value: Any


@dataclass
class DataRecord:
    metric_id: str
    timestamp: float
    metric_value: Any
    labels: List[Label] = field(default_factory=list)


class DataCollector(metaclass=ABCMeta):
    @abstractmethod
    def get_instant_data(self, metric_id: str, timestamp: float = None, **kwargs) -> List[DataRecord]:
        """
        获取指定时间戳的指标数据。
        例：
        输入：metric_id = "gala_gopher_task_fork_count", timestamp = 0
        输出：res = [
                 DataRecord(metric_id="gala_gopher_task_fork_count", timestamp=0, metric_value=1,
                            labels=[Label(name="machine_id", value="machine1")]),
                 DataRecord(metric_id="gala_gopher_task_fork_count", timestamp=0, metric_value=2,
                            labels=[Label(name="machine_id", value="machine2")]),
             ]
        @param metric_id: 指标的ID
        @param timestamp: 查询指定时间戳的数据
        @param kwargs: 查询条件可选项
        @return: 指定时间戳的指标数据的 DataRecord 列表。
        """
        pass

    @abstractmethod
    def get_range_data(self, metric_id: str, start: float, end: float, **kwargs) -> List[DataRecord]:
        """
        获取指定时间范围 [start, end] 的指标数据。
        例：
        输入：metric_id = "gala_gopher_task_fork_count", start = 0, end = 1
        输出：res = [
                 DataRecord(metric_id="gala_gopher_task_fork_count", timestamp=0, metric_value=1,
                            labels=[Label(name="machine_id", value="machine1")]),
                 DataRecord(metric_id="gala_gopher_task_fork_count", timestamp=1, metric_value=2,
                            labels=[Label(name="machine_id", value="machine1")]),
                 DataRecord(metric_id="gala_gopher_task_fork_count", timestamp=0, metric_value=1,
                            labels=[Label(name="machine_id", value="machine2")]),
                 DataRecord(metric_id="gala_gopher_task_fork_count", timestamp=1, metric_value=2,
                            labels=[Label(name="machine_id", value="machine2")]),
             ]
        @param metric_id: 指标的ID
        @param start: 起始时间戳（包含）
        @param end: 结束时间戳（包含）
        @param kwargs: 查询条件可选项
        @return: 指定时间范围 [start, end] 的指标数据
        """
        pass
