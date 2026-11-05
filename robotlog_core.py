"""RobotLog Cloud：机器人日志质量检查核心逻辑。"""

import json  # 将检查结果导出为 JSON。
from datetime import datetime, timezone  # 为报告附上生成时间。

import numpy as np  # 处理时间间隔和轨迹数值。
import pandas as pd  # 整理多传感器日志表格。


COLUMNS = ("timestamp", "topic", "value", "x", "y")  # 定义统一的日志字段。


def make_demo(inject_faults: bool = False) -> pd.DataFrame:
    """生成可复现的合成数据；不冒充真机采集。"""
    rng = np.random.default_rng(20261105)  # 固定随机种子，确保演示可重复。
    parts = []  # 每种传感器单独构建后拼接。
    configs = [  # 定义演示用的四类数据通道及采样率。
        ("/scan", 5.0),
        ("/imu", 20.0),
        ("/odom", 10.0),
        ("/camera", 2.0),
    ]
    for topic, hz in configs:  # 逐个生成传感器消息。
        times = np.arange(0.0, 60.0, 1.0 / hz)  # 生成60秒的时间序列。
        values = rng.normal(0.0, 0.06, len(times))  # 生成供演示的观测值。
        x = np.full(len(times), np.nan)  # 非里程计通道不填写位置。
        y = np.full(len(times), np.nan)  # 非里程计通道不填写位置。
        if topic == "/odom":  # 仅里程计展示机器人二维轨迹。
            x = 0.15 * times  # 采用平稳的示例前进轨迹。
            y = np.sin(times / 10.0)  # 采用平缓转弯轨迹。
            values = np.full(len(times), 0.15)  # 用示例线速度作为观测值。
        frame = pd.DataFrame({"timestamp": times, "topic": topic, "value": values, "x": x, "y": y})  # 汇总当前通道。
        if inject_faults and topic == "/scan":  # 在激光雷达通道注入可检查的缺失区间。
            frame = frame.loc[~frame["timestamp"].between(20.0, 22.0)].copy()  # 删去部分消息制造间断。
        if inject_faults and topic == "/imu":  # 在 IMU 通道注入重复时间戳。
            frame = pd.concat([frame, frame.iloc[[20]]], ignore_index=True)  # 复制一条时间戳相同的消息。
        if inject_faults and topic == "/odom":  # 在里程计通道注入不合理位置跳跃。
            frame.loc[np.isclose(frame["timestamp"], 33.0), "x"] += 10.0  # 制造明显速度异常。
        parts.append(frame)  # 保存当前传感器的日志。
    return pd.concat(parts, ignore_index=True)  # 将所有通道组合为统一数据表。


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """检查上传数据并标准化字段类型；保留原始消息顺序。"""
    if not {"timestamp", "topic"}.issubset(frame.columns):  # 上传表格必须至少包含时间和通道。
        raise ValueError("CSV必须包含timestamp和topic两列")  # 给出可直接纠正的错误提示。
    result = frame.copy()  # 避免直接修改输入数据。
    for name in COLUMNS:  # 为可选字段补齐空值列。
        if name not in result.columns:  # 判断列是否缺失。
            result[name] = np.nan  # 用缺失值明确表示没有该数据。
    result = result.loc[:, COLUMNS]  # 按固定顺序保留需要的字段。
    result["timestamp"] = pd.to_numeric(result["timestamp"], errors="coerce")  # 统一秒级数值时间戳。
    for name in ("value", "x", "y"):  # 将观测值和轨迹坐标转为数值。
        result[name] = pd.to_numeric(result[name], errors="coerce")  # 无法解析的可选值保留为空。
    result["topic"] = result["topic"].astype("string").str.strip()  # 清理通道名称空白。
    result = result.loc[result["timestamp"].notna() & result["topic"].notna() & (result["topic"] != "")].copy()  # 丢弃无效关键字段。
    if result.empty:  # 不允许检查空表。
        raise ValueError("没有可分析的有效timestamp/topic记录")  # 提示用户更换数据。
    if not np.isfinite(result["timestamp"].to_numpy(dtype=float)).all():  # 排除无穷大时间戳。
        raise ValueError("timestamp包含无穷值，请先清洗数据")  # 避免异常值污染诊断。
    return result.reset_index(drop=True)  # 返回标准化且保留事件顺序的表格。


def analyze(frame: pd.DataFrame, gap_ratio: float = 3.0, max_speed: float = 2.5) -> dict:
    """基于时间间隔和轨迹判断可观察到的异常，不将间隔直接等同硬件丢包。"""
    data = normalize_frame(frame)  # 对所有来源执行一致的输入检查。
    if gap_ratio <= 1 or max_speed <= 0:  # 检查规则参数是否合法。
        raise ValueError("间隔倍率需大于1，速度阈值需大于0")  # 拒绝无效设置。
    events = []  # 存储可定位的异常事件。
    summary = []  # 存储每个传感器的整体统计。
    for topic, group in data.groupby("topic", sort=True):  # 分别检查每一种传感器。
        original_times = group["timestamp"].to_numpy(dtype=float)  # 保留上传时的通道内部顺序。
        disorder = np.where(np.diff(original_times) < 0)[0]  # 查找时间倒退的位置。
        ordered = group.sort_values("timestamp", kind="stable")  # 按时间排序用于分析相邻间隔。
        times = ordered["timestamp"].to_numpy(dtype=float)  # 提取已排序的时间戳。
        diffs = np.diff(times)  # 计算连续消息的时间差。
        positive = diffs[diffs > 0]  # 排除重复时间戳后推断常见频率。
        med_dt = float(np.median(positive)) if len(positive) else np.nan  # 得到正常间隔的稳健估计。
        hz = float(1.0 / med_dt) if np.isfinite(med_dt) and med_dt > 0 else np.nan  # 由中位间隔推算频率。
        cutoff = max(med_dt * gap_ratio, 0.05) if np.isfinite(med_dt) else np.inf  # 设置异常间隔阈值。
        duplicates = np.where(diffs == 0)[0]  # 找出重复时间戳。
        gaps = np.where(diffs > cutoff)[0]  # 查找显著超出典型间隔的区间。
        for idx in disorder[:200]:  # 限制单个通道的事件输出数量。
            events.append({"topic": str(topic), "time_s": float(original_times[idx + 1]), "kind": "时间戳倒退", "detail": "同通道记录顺序出现倒退"})  # 记录顺序异常。
        for idx in duplicates[:200]:  # 遍历重复位置。
            events.append({"topic": str(topic), "time_s": float(times[idx + 1]), "kind": "重复时间戳", "detail": "同通道两条消息的时间戳相同"})  # 记录重复事件。
        for idx in gaps[:200]:  # 遍历异常间隔。
            events.append({"topic": str(topic), "time_s": float(times[idx + 1]), "kind": "异常采样间隔", "detail": f"相邻间隔 {diffs[idx]:.3f}s，典型间隔 {med_dt:.3f}s"})  # 记录实际可观察的间隔。
        summary.append({  # 将当前传感器的指标追加到总表。
            "topic": str(topic), "messages": int(len(group)),
            "start_s": float(times[0]), "end_s": float(times[-1]),
            "median_hz": round(hz, 2) if np.isfinite(hz) else None,
            "duplicate_timestamps": int(len(duplicates)),
            "out_of_order": int(len(disorder)),
            "long_gaps": int(len(gaps)),
        })
    odom = data[data["topic"].str.contains("odom", case=False, regex=False)].copy()  # 仅从名称含odom的通道寻找轨迹。
    odom = odom.dropna(subset=["x", "y"]).sort_values("timestamp")  # 排除没有坐标的消息并按时间排序。
    if len(odom) >= 2:  # 至少两点才能计算速度。
        array = odom[["timestamp", "x", "y"]].to_numpy(dtype=float)  # 提取秒、x、y。
        dt = np.diff(array[:, 0])  # 计算相邻里程计时间差。
        distance = np.hypot(np.diff(array[:, 1]), np.diff(array[:, 2]))  # 计算相邻位移长度。
        speed = np.divide(distance, dt, out=np.full_like(distance, np.nan), where=dt > 0)  # 避免除以零。
        spikes = np.where(np.isfinite(speed) & (speed > max_speed))[0]  # 查找超过展示阈值的位置变化。
        for idx in spikes[:200]:  # 限制异常事件条数。
            events.append({"topic": "/odom", "time_s": float(array[idx + 1, 0]), "kind": "位置变化过快", "detail": f"相邻点推算速度 {speed[idx]:.2f}m/s，阈值 {max_speed:.2f}m/s"})  # 记录速度异常。
    return {  # 返回可序列化的分析报告。
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": int(len(data)), "topic_count": int(len(summary)),
        "time_span_s": float(data["timestamp"].max() - data["timestamp"].min()),
        "event_count": int(len(events)), "topics": summary,
        "events": sorted(events, key=lambda x: (x["time_s"], x["kind"])),
        "rules": {"gap_ratio": gap_ratio, "max_speed_m_s": max_speed},
        "limitations": "采样间隔异常不直接证明丢包；检测结果不等于硬件故障诊断。",
    }  # 完成结果整理。


def report_json(result: dict, source_label: str) -> str:
    """导出包含来源声明的完整报告。"""
    payload = {"source": source_label, **result}  # 记录数据来源，避免把合成数据误称真机数据。
    return json.dumps(payload, ensure_ascii=False, indent=2)  # 输出可读的中文JSON。
