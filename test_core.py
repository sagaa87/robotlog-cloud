"""RobotLog核心逻辑测试：验证合成正常样本与故障注入。"""

import pandas as pd  # 用于构造边界测试样本。
import pytest  # 使用断言测试输入校验。

from src.robotlog_core import make_demo, normalize_frame, analyze, report_json  # 导入待验证函数。


def test_clean_data_has_no_events():  # 检查正常合成数据不会触发明显误报。
    report = analyze(make_demo(False))  # 对正常合成数据运行检查。
    assert report["topic_count"] == 4  # 确认包含四种演示传感器。
    assert report["event_count"] == 0  # 确认没有注入的故障事件。


def test_fault_injection_detected():  # 检查注入的三类异常可被发现。
    report = analyze(make_demo(True))  # 对故障合成数据进行分析。
    kinds = {event["kind"] for event in report["events"]}  # 收集异常类型。
    assert "异常采样间隔" in kinds  # 必须识别时间间隔异常。
    assert "重复时间戳" in kinds  # 必须识别重复时间戳。
    assert "位置变化过快" in kinds  # 必须识别不合理位置跳跃。
    assert "合成" in report_json(report, "合成故障数据")  # 报告中必须保留数据来源。


def test_required_columns_are_enforced():  # 检查上传CSV的必要字段。
    with pytest.raises(ValueError):  # 缺少topic应引发格式错误。
        normalize_frame(pd.DataFrame({"timestamp": [1, 2]}))  # 构造不完整表格。


def test_optional_columns_are_generated():  # 检查缺少可选字段不阻止分析。
    frame = normalize_frame(pd.DataFrame({"timestamp": [1.0, 2.0], "topic": ["/imu", "/imu"]}))  # 只提供必要列。
    assert {"value", "x", "y"}.issubset(frame.columns)  # 确认系统已补齐可选列。
