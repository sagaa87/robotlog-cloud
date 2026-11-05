"""可选功能：无需完整ROS环境读取ROS1 .bag的常见消息类型。"""

from pathlib import Path  # 管理临时文件路径。
import tempfile  # 上传文件临时存储在服务器会话内。

import numpy as np  # 计算激光距离统计量。
import pandas as pd  # 汇总成统一的事件表格。


def read_ros1_bag(uploaded_bytes: bytes, max_messages: int = 120_000) -> pd.DataFrame:
    """只提取常用ROS消息的关键字段，不对大文件做长期存储。"""
    from rosbags.highlevel import AnyReader  # 延迟导入ROS日志解析库。

    if len(uploaded_bytes) > 100 * 1024 * 1024:  # 控制在线演示最大上传大小。
        raise ValueError("在线演示仅允许不超过100MB的ROS1 .bag文件")  # 超出限制时明确提示。
    rows = []  # 临时保存解析后的事件记录。
    with tempfile.TemporaryDirectory(prefix="robotlog_") as folder:  # 创建用完即删除的工作目录。
        bag = Path(folder) / "session.bag"  # 建立与解析器兼容的文件名。
        bag.write_bytes(uploaded_bytes)  # 保存上传内容到临时文件。
        with AnyReader([bag]) as reader:  # 打开ROS1日志，无需安装ROS系统。
            allowed = [c for c in reader.connections if any(t in c.topic.lower() for t in ("scan", "imu", "odom", "camera", "image"))]  # 筛选最相关的通道。
            if not allowed:  # 如果数据里没有支持的通道。
                raise ValueError("该ROS bag中没有scan/imu/odom/camera/image通道")  # 避免显示空结果。
            first_t = None  # 记录首条消息时间作为相对时间原点。
            for connection, time_ns, rawdata in reader.messages(connections=allowed):  # 逐条读取消息。
                if len(rows) >= max_messages:  # 避免云端内存和计算资源超额。
                    break  # 仅保留可交互展示的前若干消息。
                if first_t is None:  # 如果尚未建立时间基准。
                    first_t = time_ns  # 将首条消息设为零秒。
                t = (time_ns - first_t) / 1_000_000_000.0  # 纳秒转换为相对秒。
                msg = reader.deserialize(rawdata, connection.msgtype)  # 按ROS类型解析消息。
                topic = connection.topic  # 保留真实ROS话题名称。
                value, x, y = np.nan, np.nan, np.nan  # 默认不存在数值观测和位置坐标。
                if "odom" in topic.lower() and hasattr(msg, "pose"):  # 提取里程计位置数据。
                    x = float(msg.pose.pose.position.x)  # 获取机器人x坐标。
                    y = float(msg.pose.pose.position.y)  # 获取机器人y坐标。
                    value = float(msg.twist.twist.linear.x)  # 获取消息中记录的线速度。
                elif "imu" in topic.lower() and hasattr(msg, "angular_velocity"):  # 提取IMU角速度。
                    value = float(msg.angular_velocity.z)  # 选择z轴角速度作为示例观测。
                elif "scan" in topic.lower() and hasattr(msg, "ranges"):  # 提取雷达距离读数。
                    ranges = np.asarray(msg.ranges, dtype=float)  # 将扫描数组转为数值。
                    valid = ranges[np.isfinite(ranges)]  # 排除无穷值和NaN。
                    value = float(np.median(valid)) if len(valid) else np.nan  # 以有效距离的中位数作概览。
                elif hasattr(msg, "height") and hasattr(msg, "width"):  # 识别携带图像尺寸的消息。
                    value = float(msg.width * msg.height)  # 记录像素数量，不解码图片内容。
                rows.append({"timestamp": t, "topic": topic, "value": value, "x": x, "y": y})  # 统一写入日志结构。
    if not rows:  # 校验解析结果。
        raise ValueError("ROS bag未解析出支持的消息")  # 给出友好的失败原因。
    return pd.DataFrame(rows)  # 将真实机器人消息转换为统一分析表。
