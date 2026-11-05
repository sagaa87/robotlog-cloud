# RobotLog Cloud

面向**移动机器人多传感日志**的在线质量检测与可视化MVP（简历展示原型）。

## 重要说明

- **项目状态**：可部署源码与本地核心单元测试；需要用户部署到Streamlit Community Cloud后才能获得实际在线链接。
- **数据真实性**：内置正常/异常样例均为明确标注的**程序合成数据**，不代表真实机器人实验。真实ROS1 bag/CSV需要用户主动上传。
- **实现范围**：日志导入、典型间隔估计、重复时间戳/倒退/长间隔检测、里程计位置跳跃分析、图表、JSON/CSV导出。
- **未实现**：ROS2 bag导入、PB级存储、登录鉴权、长期数据库、机器人实时采集、真机验证、具身大模型训练。
- **技术特点**：数据处理和网页分离、规则可配置、测试可重复、分析结果包含来源和局限声明。

## 0. 文件结构

```
app.py                     # Streamlit入口
src/robotlog_core.py       # 数据规范化、规则诊断、报告导出
src/rosbag_import.py       # 可选ROS1 bag日志解析
requirements.txt           # 在线部署依赖
tests/test_core.py         # 核心模块单元测试
```

## 1. 在浏览器里部署到公开链接

1. 进入 https://github.com/new ，建立一个**公开仓库**（例如 `robotlog-cloud`）。
2. 将此文件夹所有文件上传至仓库根目录，确保存在 `app.py`、`requirements.txt` 和 `src/`。
3. 打开 https://share.streamlit.io ，使用GitHub登录，选择 **Create app**。
4. 选择你的仓库、分支 `main`、入口文件 `app.py`；Python可选择官方支持的3.12版本。
5. 选择 Deploy；成功后获取属于你的 `*.streamlit.app` 网址。可以分享给招聘负责人。
6. 先选择**注入故障的合成数据**，验证是否识别3类典型异常，再上传你自己已有的真实CSV或ROS1 bag。

官方部署说明：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

> 上传的个人机器人日志可能含敏感数据。公开演示站点请只使用授权公开的数据，并考虑在线服务日志与访问权限。

## 2. 可选本地运行与测试

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

## 3. 上传CSV格式

至少提供两列：`timestamp`（浮点数，单位秒）和`topic`（ROS式通道名称）。可选 `value`、`x`、`y`。`x/y` 只应在里程计数据中出现，单位按米处理。

```csv
timestamp,topic,value,x,y
0.0,/scan,1.8,,
0.0,/imu,0.01,,
0.0,/odom,0.2,0.0,0.0
0.1,/odom,0.2,0.02,0.0
0.2,/odom,0.2,0.04,0.0
```

对于真实机器人数据，可从ROS日志提取这些字段；网页也支持上传ROS1 `.bag`（不超过100MB，最多分析前12万条支持的消息）。注意**ROS2 bag暂不支持**。

## 4. 公开真实机器人数据来源

TurtleBot3 Waffle Pi 多传感器数据集：https://github.com/guilhermelawless/turtlebot3_datasets

可选先下载该仓库提供的ROS1 bag样例（注意文件大小），保留来源说明，遵循其授权与使用条件。数据内容、可达性和页面部署状态需要用户在实际使用时再次确认。

## 5. 面试可讲述的技术设计

问题：不同传感器的采样率不同，如何在不误判正常数据为故障的情况下检测异常？

方案：每个话题独立估计典型时间间隔；使用中位数避免少量异常点破坏基准；超过配置倍率才报告长间隔；重复时间戳和乱序分别检测；对里程计使用位移除以时间差检查速度阈值。

边界：长间隔只能判定记录不连续，不足以证明掉包；位置跳跃需结合机器人运动能力调整阈值；样例故障检测成功不等于真实设备验证。

## 6. 下一步真实升级

- 上传真实机器人数据并记录文件哈希、样本数、来源、检测结果。
- 加入按任务ID关联和不同传感器时间轴对齐。
- 接入支持的ROS2 `.mcap` 或 `.db3`；完善上传错误与大文件处理。
- 加入数据库与查询接口，转化为更接近数据平台工程的作品。

**简历纪律**：只有完成在线部署、提供真实可用链接且完成对应功能验证，才写“已部署在线平台”。目前不能宣称真机采集、PB级处理或服务真实算法研究员。
