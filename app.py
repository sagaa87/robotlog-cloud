"""RobotLog Cloud在线展示入口：上传数据、分析质量并导出报告。"""

import io  # 直接读取上传文件二进制内容。
import pandas as pd  # 处理CSV输入及数据展示。
import plotly.express as px  # 提供可缩放和悬停查看的互动图表。
import streamlit as st  # 生成可部署的交互式网页。

from src.robotlog_core import make_demo, normalize_frame, analyze, report_json  # 使用独立测试的数据分析逻辑。

st.set_page_config(page_title="RobotLog Cloud", page_icon="🤖", layout="wide")  # 设置网页标题和宽屏排版。
st.title("RobotLog Cloud｜机器人数据质量检测")  # 显示项目名称。
st.caption("在线作品原型 · 移动机器人多传感日志分析 · 不连接真实机器人，不提供实时监控")  # 明确原型边界。

with st.sidebar:  # 将数据源和检测参数集中到侧栏。
    st.header("数据与检测配置")  # 展示配置区名称。
    source = st.radio("选择数据来源", ["演示：正常合成数据", "演示：注入故障的合成数据", "上传CSV或ROS1 .bag"], index=1)  # 选择数据来源。
    uploaded = st.file_uploader("上传文件", type=["csv", "bag"], disabled=not source.startswith("上传"))  # 支持CSV及ROS1日志文件。
    gap_ratio = st.slider("采样间隔异常倍率", 2.0, 8.0, 3.0, 0.5)  # 调整采样间隔异常检测灵敏度。
    max_speed = st.slider("里程计相邻速度阈值（m/s）", 0.5, 10.0, 2.5, 0.5)  # 调整位置跳跃检测阈值。
    st.info("演示数据为程序生成，故障为人工注入；真实数据需要用户上传。检测结果仅用于数据质量分析。")  # 避免混淆演示与实测。

try:  # 处理可能由文件格式引发的用户输入错误。
    if source == "演示：正常合成数据":  # 如果选择正常合成数据。
        frame = make_demo(False)  # 生成可复现的正常数据。
        source_label = "合成正常数据（非真机）"  # 明确数据属性。
    elif source == "演示：注入故障的合成数据":  # 如果选择故障演示。
        frame = make_demo(True)  # 生成包含可观察异常的合成数据。
        source_label = "合成故障数据（非真机，人工注入）"  # 明确异常并非真实故障。
    else:  # 如果用户选择上传个人文件。
        if uploaded is None:  # 用户还未选择文件。
            st.info("请先上传CSV或ROS1 .bag文件。CSV至少包含timestamp（秒）和topic列；可包含value、x、y。")  # 告知数据要求。
            st.stop()  # 停止本次渲染，等待用户上传。
        if uploaded.size > 100 * 1024 * 1024:  # 限制文件大小，保护公共演示环境。
            raise ValueError("文件大于100MB，请先抽取一段较短的日志")  # 提示裁剪日志。
        if uploaded.name.lower().endswith(".csv"):  # 判断是否为CSV文件。
            frame = pd.read_csv(io.BytesIO(uploaded.getvalue()))  # 将用户上传的CSV解析为表格。
            source_label = f"用户上传CSV：{uploaded.name}"  # 标记用户提供的数据来源。
        else:  # 其他允许的文件类型为ROS1 bag。
            from src.rosbag_import import read_ros1_bag  # 仅在需要时加载解析器。
            frame = read_ros1_bag(uploaded.getvalue())  # 从ROS1文件提取传感器消息。
            source_label = f"用户上传ROS1 bag：{uploaded.name}（限制前120000条消息）"  # 明确日志读取上限。
    data = normalize_frame(frame)  # 规范化输入字段。
    result = analyze(data, gap_ratio=gap_ratio, max_speed=max_speed)  # 执行质量分析。
except Exception as exc:  # 捕获输入或解析失败并给出提示。
    st.error(f"数据处理失败：{exc}")  # 显示具体错误信息。
    st.stop()  # 在失败时停止页面继续绘图。

st.caption(f"当前来源：{source_label}")  # 在主界面显示真实数据来源。
a, b, c, d = st.columns(4)  # 创建四个横向指标卡片。
a.metric("消息数量", f"{result['record_count']:,}")  # 显示日志总消息数。
b.metric("数据通道", result["topic_count"])  # 显示传感器通道数。
c.metric("观测时长", f"{result['time_span_s']:.1f} 秒")  # 显示覆盖时间范围。
d.metric("检测到的异常事件", result["event_count"])  # 显示诊断事件数，不等于故障数。

left, right = st.columns([1.2, 1.0])  # 设置左右内容区宽度。
with left:  # 左侧主要展示质量指标。
    st.subheader("各通道质量概览")  # 展示数据质量模块。
    st.dataframe(pd.DataFrame(result["topics"]), use_container_width=True, hide_index=True)  # 展示逐通道的频率、重复及间隔统计。
    if result["events"]:  # 如果存在异常事件。
        st.subheader("可定位的异常事件")  # 展示异常时间表。
        st.dataframe(pd.DataFrame(result["events"]), use_container_width=True, hide_index=True, height=320)  # 展示异常种类与描述。
    else:  # 如果未检测到异常。
        st.success("当前规则下未发现异常事件；这不代表已经完成全部数据质量验证。")  # 避免绝对化判断。
with right:  # 右侧主要展示曲线和轨迹。
    st.subheader("数据记录时间分布")  # 显示传感器记录的时间范围。
    sampled = pd.concat([g.iloc[::max(1, len(g)//400)] for _, g in data.groupby("topic")], ignore_index=True)  # 为页面性能按通道取样，仅影响可视化。
    scatter = px.scatter(sampled, x="timestamp", y="topic", color="topic", title="通道消息采样分布")  # 生成可互动的时间散点图。
    scatter.update_layout(showlegend=False, xaxis_title="日志时间（秒）", yaxis_title="消息通道", height=270)  # 为图表设置中文坐标轴。
    st.plotly_chart(scatter, use_container_width=True)  # 渲染传感器时间图。
    trajectory = data[data["topic"].str.contains("odom", case=False, regex=False)].dropna(subset=["x", "y"]).sort_values("timestamp")  # 提取可用的轨迹点。
    if len(trajectory):  # 存在里程计位置数据才绘图。
        st.subheader("机器人二维位置轨迹")  # 展示轨迹模块。
        fig = px.line(trajectory, x="x", y="y", markers=False, title="里程计位置轨迹（若有）")  # 用二维线图展示路径。
        fig.update_yaxes(scaleanchor="x", scaleratio=1)  # 保持x、y坐标比例一致。
        fig.update_layout(height=330)  # 设置适合网页的高度。
        st.plotly_chart(fig, use_container_width=True)  # 渲染互动轨迹图。
    else:  # 没有位置数据时不展示虚构轨迹。
        st.info("当前数据不包含可用的odom二维位置，无法展示轨迹。")  # 提示实际数据缺失。

st.subheader("导出可验证的分析结果")  # 展示报告下载区。
report = report_json(result, source_label)  # 生成包含数据来源和规则参数的JSON报告。
first, second = st.columns(2)  # 并排显示两个下载入口。
first.download_button("下载JSON质量报告", report.encode("utf-8"), "robotlog_quality_report.json", "application/json")  # 下载结果报告。
second.download_button("下载标准化日志CSV", data.to_csv(index=False).encode("utf-8-sig"), "robotlog_normalized.csv", "text/csv")  # 下载清洗后的日志。
with st.expander("项目边界与数据使用说明"):  # 提供可展开的透明说明。
    st.write("本项目当前为单机逻辑部署的在线MVP，不具备持久化数据库、用户鉴权或PB级分布式处理能力。")  # 声明未实现的大型系统功能。
    st.write("合成演示数据仅用于验证规则；真实机器人数据需要上传ROS1 bag或已转换的CSV。")  # 区分数据真伪。
    st.write("时间戳间隔异常可能由正常频率变化、录制中断或传输问题引起，需要结合实际设备和任务判断。")  # 解释异常输出限制。
