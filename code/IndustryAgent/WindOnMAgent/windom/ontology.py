"""风电运维本体与领域知识定义（文档 3.3.1）：实体/关系类型、传感器目录、故障-原因-措施因果知识、术语词表。

此处的故障因果知识会在 seed 时写入知识图谱(PostgreSQL)，诊断模型(services/diagnosis_model.py)
从知识图谱而不是此文件读取原因先验与特征签名，保证“知识图谱是可信知识底座”。
"""
from __future__ import annotations

ENTITY_TYPES = [
    "WindFarm", "Turbine", "Substation", "Cable", "Mast", "SubSystem", "Component", "Sensor",
    "Fault", "Cause", "CheckItem", "Action", "SparePart", "Document", "WorkOrder",
    "WarningLevel", "Person", "Env", "ComponentClass", "Case",
]

RELATION_TYPES = {
    "contains": ("包含", {"WindFarm", "Turbine", "Substation", "Cable", "Mast", "SubSystem", "Component"}),
    "installed_on": ("安装于", {"Component"}),
    "monitors": ("监测", {"Sensor"}),
    "has_fault": ("可能发生", {"Component", "Cable", "Substation"}),
    "possible_cause": ("可能原因", {"Fault"}),
    "check": ("建议检查", {"Cause"}),
    "remedy": ("对应措施", {"Cause"}),
    "needs_part": ("所需备件", {"Action"}),
    "cites": ("引用依据", {"Action", "Fault", "Cause"}),
    "handles": ("处理", {"WorkOrder"}),
    "adopted": ("采用措施", {"WorkOrder"}),
    "root_cause": ("根因", {"WorkOrder"}),
    "result": ("处理结果", {"WorkOrder"}),
    "on_component": ("发生于部件", {"Case"}),
    "instance_of": ("属于类型", {"Component"}),
    "warning_level": ("预警等级", {"Fault"}),
    "constrains": ("约束", {"Env"}),
}

# 受 SCADA/规程约束的传感器目录: (type, name, unit, comp_type, kind, nominal, lo, hi)
SENSORS = [
    ("gearbox_oil_temp", "齿轮箱油温", "℃", "gearbox", "turbine", 62, 30, 130),
    ("gearbox_vibration", "齿轮箱振动", "mm/s", "gearbox", "turbine", 2.4, 0, 20),
    ("gearbox_oil_pressure", "齿轮箱油压", "bar", "gearbox", "turbine", 3.2, 0, 8),
    ("cooling_airflow", "冷却风量", "%", "gearbox", "turbine", 100, 0, 130),
    ("generator_winding_temp", "发电机绕组温度", "℃", "generator", "turbine", 82, 20, 170),
    ("generator_bearing_temp", "发电机轴承温度", "℃", "generator", "turbine", 62, 20, 120),
    ("converter_igbt_temp", "变流器IGBT温度", "℃", "converter", "turbine", 58, 20, 130),
    ("hydraulic_pressure", "液压系统压力", "bar", "hydraulic", "turbine", 180, 0, 250),
    ("hydraulic_oil_level", "液压油位", "%", "hydraulic", "turbine", 92, 0, 100),
    ("main_bearing_temp", "主轴承温度", "℃", "main_shaft", "turbine", 48, 10, 110),
    ("tower_vibration", "塔筒振动", "mm/s", "tower", "turbine", 3.0, 0, 20),
    ("wind_speed", "风速", "m/s", None, "turbine", 8.5, 0, 60),
    ("rotor_speed", "叶轮转速", "rpm", "blade", "turbine", 11, 0, 25),
    ("active_power", "有功功率", "kW", None, "turbine", 3000, -100, 7000),
    ("transformer_oil_temp", "主变油温", "℃", "transformer", "substation", 58, 10, 130),
    ("cable_conductor_temp", "海缆导体温度", "℃", "cable_body", "cable", 52, 5, 130),
    ("mast_wind_speed", "测风塔风速", "m/s", "anemometer", "mast", 8.5, 0, 60),
]
TURBINE_SENSORS = [s[0] for s in SENSORS if s[4] == "turbine"]
SENSOR_NAME = {s[0]: s[1] for s in SENSORS}
SENSOR_UNIT = {s[0]: s[2] for s in SENSORS}

# 部件类型 -> (中文名, 子系统)
COMPONENT_TYPES = {
    "blade": ("叶片", "风轮系统"),
    "main_shaft": ("主轴", "传动系统"),
    "gearbox": ("齿轮箱", "传动系统"),
    "generator": ("发电机", "电气系统"),
    "converter": ("变流器", "电气系统"),
    "hydraulic": ("液压系统", "液压系统"),
    "tower": ("塔筒", "支撑结构"),
}
TURBINE_COMPONENT_ORDER = ["blade", "main_shaft", "gearbox", "generator", "converter", "hydraulic", "tower"]
COMP_NAME = {k: v[0] for k, v in COMPONENT_TYPES.items()}
COMP_NAME.update({"transformer": "主变压器", "cable_body": "海缆本体", "anemometer": "测风仪"})

# 预警级别定义(规范多级预警): 数字越大越严重
WARNING_LEVELS = {
    1: ("一级预警", "关注", "纳入出海计划合并处理"),
    2: ("二级预警", "告警", "自动触发紧急工单，30 分钟内响应"),
    3: ("三级预警", "严重", "立即上报，紧急工单并通知值班长"),
}

# 备件库: code, name, comp_type, stock, location, lead_days
SPARE_PARTS = [
    ("SP-008", "齿轮箱冷却器滤网", "gearbox", 2, "升压站备件库", 3),
    ("SP-011", "齿轮油(20L)", "gearbox", 14, "陆上码头仓库", 2),
    ("SP-012", "齿轮箱油位/油压传感器", "gearbox", 3, "陆上码头仓库", 5),
    ("SP-021", "齿轮箱轴承套件", "gearbox", 0, "总部备件中心", 30),
    ("SP-031", "发电机冷却风扇", "generator", 3, "陆上码头仓库", 4),
    ("SP-032", "发电机轴承", "generator", 1, "总部备件中心", 21),
    ("SP-033", "轴承润滑脂(桶)", "generator", 20, "陆上码头仓库", 1),
    ("SP-041", "变流器冷却水泵", "converter", 2, "升压站备件库", 5),
    ("SP-042", "IGBT功率模块", "converter", 1, "总部备件中心", 28),
    ("SP-043", "变流器散热器滤网", "converter", 6, "陆上码头仓库", 2),
    ("SP-051", "液压密封件套件", "hydraulic", 5, "陆上码头仓库", 3),
    ("SP-052", "液压泵总成", "hydraulic", 1, "总部备件中心", 20),
    ("SP-053", "蓄能器", "hydraulic", 2, "陆上码头仓库", 10),
    ("SP-061", "主轴承润滑脂泵", "main_shaft", 2, "陆上码头仓库", 6),
    ("SP-071", "塔筒连接螺栓套件", "tower", 4, "陆上码头仓库", 7),
    ("SP-072", "叶片配重块", "blade", 2, "陆上码头仓库", 10),
    ("SP-081", "海缆修复套件", "cable_body", 1, "总部备件中心", 45),
    ("SP-091", "变压器油(桶)", "transformer", 6, "升压站备件库", 3),
    ("SP-092", "主变冷却风机", "transformer", 2, "升压站备件库", 7),
]

# 故障因果知识库。signature: 辅助传感器相对风场同类机组中位数的偏离方向 (+1 偏高 / -1 偏低 / 0 正常)
FAULTS: dict[str, dict] = {
    "GearboxOilTempHigh": {
        "name": "齿轮箱油温过高", "comp": "gearbox", "sensor": "gearbox_oil_temp", "doc": ("WI-GB-001", "4.2"),
        "synonyms": ["齿轮箱温高", "齿轮油温超限", "GB油温异常", "齿轮箱油温高", "齿轮箱油温过高", "齿轮箱油温持续升高", "油温高"],
        "causes": [
            {"key": "CoolerClogged", "name": "冷却器堵塞/积尘", "prior": 0.45, "scenario": "gearbox_cooler_clog",
             "signature": {"cooling_airflow": -1, "gearbox_vibration": 0, "gearbox_oil_pressure": 0},
             "checks": ["冷却器滤网与进风口积尘", "冷却风扇运转状态"],
             "actions": [{"key": "CleanFilter", "name": "清理冷却器滤网", "parts": ["SP-008"], "hours": 3, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "4.2")}]},
            {"key": "OilShortage", "name": "润滑油不足/泄漏", "prior": 0.25, "scenario": "gearbox_low_oil",
             "signature": {"gearbox_oil_pressure": -1, "cooling_airflow": 0, "gearbox_vibration": 0},
             "checks": ["油位与油压", "管路及密封泄漏点"],
             "actions": [{"key": "RefillOil", "name": "补充润滑油并排查泄漏", "parts": ["SP-011", "SP-012"], "hours": 4, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "4.4")}]},
            {"key": "BearingWear", "name": "齿轮/轴承磨损", "prior": 0.20, "scenario": "gearbox_bearing_wear",
             "signature": {"gearbox_vibration": 1, "cooling_airflow": 0, "gearbox_oil_pressure": 0},
             "checks": ["振动频谱分析", "油液铁谱/颗粒度检测", "孔探检查齿面"],
             "actions": [{"key": "InspectGearbox", "name": "孔探检查并评估更换轴承", "parts": ["SP-021"], "hours": 12, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "5.1")}]},
            {"key": "OilDegraded", "name": "润滑油老化变质", "prior": 0.10, "scenario": "gearbox_oil_degraded",
             "signature": {"gearbox_oil_pressure": 0, "cooling_airflow": 0, "gearbox_vibration": 0},
             "checks": ["油品理化分析(粘度/酸值)"],
             "actions": [{"key": "ChangeOil", "name": "更换齿轮油并换滤芯", "parts": ["SP-011"], "hours": 6, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "4.5")}]},
        ]},
    "GearboxVibrationHigh": {
        "name": "齿轮箱振动超限", "comp": "gearbox", "sensor": "gearbox_vibration", "doc": ("WI-GB-001", "5.1"),
        "synonyms": ["齿轮箱振动大", "齿轮箱振动异常", "GB振动超限", "齿轮箱振动高"],
        "causes": [
            {"key": "GearTeethWear", "name": "齿面磨损/点蚀", "prior": 0.45, "scenario": "gearbox_gear_wear",
             "signature": {"gearbox_oil_temp": 1, "gearbox_oil_pressure": 0, "tower_vibration": 0},
             "checks": ["振动频谱分析", "油液铁谱检测", "孔探检查"],
             "actions": [{"key": "InspectGearTeeth", "name": "孔探检查并评估更换", "parts": ["SP-021"], "hours": 12, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "5.1")}]},
            {"key": "Misalignment", "name": "对中不良/联轴器松动", "prior": 0.30, "scenario": "gearbox_misalign",
             "signature": {"gearbox_oil_temp": 0, "tower_vibration": 1, "gearbox_oil_pressure": 0},
             "checks": ["联轴器紧固与对中检查"],
             "actions": [{"key": "Realign", "name": "重新对中并紧固联轴器", "parts": [], "hours": 8, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "5.3")}]},
            {"key": "SensorFault", "name": "传感器漂移/误报", "prior": 0.25, "scenario": "gearbox_vib_sensor",
             "signature": {"gearbox_oil_temp": 0, "tower_vibration": 0, "gearbox_oil_pressure": 0},
             "checks": ["传感器标定与线路检查"],
             "actions": [{"key": "CalibrateSensor", "name": "校验并标定振动传感器", "parts": ["SP-012"], "hours": 2, "needs": ["climb", "offshore"], "doc": ("WI-GB-001", "6.1")}]},
        ]},
    "GeneratorWindingTempHigh": {
        "name": "发电机绕组温度过高", "comp": "generator", "sensor": "generator_winding_temp", "doc": ("WI-GN-001", "3.2"),
        "synonyms": ["发电机绕组温高", "发电机温度高", "发电机绕组过热", "定子温度高"],
        "causes": [
            {"key": "FanFailure", "name": "冷却风扇故障", "prior": 0.50, "scenario": "gen_fan_fault",
             "signature": {"cooling_airflow": -1, "generator_bearing_temp": 0, "gearbox_vibration": 0},
             "checks": ["风扇电机与接触器", "风道堵塞情况"],
             "actions": [{"key": "ReplaceFan", "name": "更换发电机冷却风扇", "parts": ["SP-031"], "hours": 5, "needs": ["climb", "offshore"], "doc": ("WI-GN-001", "3.2")}]},
            {"key": "Overload", "name": "长期过载运行", "prior": 0.25, "scenario": "gen_overload",
             "signature": {"cooling_airflow": 0, "generator_bearing_temp": 1, "gearbox_vibration": 0},
             "checks": ["功率曲线与限功率策略", "三相电流平衡"],
             "actions": [{"key": "ReviewLoad", "name": "复核限功率策略(需授权人员决定)", "parts": [], "hours": 1, "needs": [], "doc": ("WI-GN-001", "3.5")}]},
            {"key": "InsulationAging", "name": "绝缘老化", "prior": 0.25, "scenario": "gen_insulation",
             "signature": {"cooling_airflow": 0, "generator_bearing_temp": 0, "gearbox_vibration": 0},
             "checks": ["绝缘电阻/极化指数测试"],
             "actions": [{"key": "InsulationTest", "name": "绝缘电阻测试并评估大修", "parts": [], "hours": 8, "needs": ["climb", "offshore", "hv"], "doc": ("WI-GN-001", "4.1")}]},
        ]},
    "GeneratorBearingTempHigh": {
        "name": "发电机轴承温度过高", "comp": "generator", "sensor": "generator_bearing_temp", "doc": ("WI-GN-001", "3.4"),
        "synonyms": ["发电机轴承温高", "发电机轴承过热", "发电机轴承温度异常"],
        "causes": [
            {"key": "LubeShortage", "name": "润滑脂不足/失效", "prior": 0.55, "scenario": "gen_lube",
             "signature": {"generator_winding_temp": 0, "gearbox_vibration": 0},
             "checks": ["润滑脂注入量与油脂状态"],
             "actions": [{"key": "Regrease", "name": "补充/更换轴承润滑脂", "parts": ["SP-033"], "hours": 3, "needs": ["climb", "offshore"], "doc": ("WI-GN-001", "3.4")}]},
            {"key": "BearingDamage", "name": "轴承磨损/损伤", "prior": 0.45, "scenario": "gen_bearing_damage",
             "signature": {"generator_winding_temp": 0, "gearbox_vibration": 1},
             "checks": ["轴承振动与噪声检测", "轴承间隙测量"],
             "actions": [{"key": "ReplaceBearing", "name": "评估并更换发电机轴承", "parts": ["SP-032"], "hours": 24, "needs": ["climb", "offshore"], "doc": ("WI-GN-001", "4.3")}]},
        ]},
    "ConverterIGBTTempHigh": {
        "name": "变流器IGBT温度过高", "comp": "converter", "sensor": "converter_igbt_temp", "doc": ("WI-CV-001", "2.3"),
        "synonyms": ["变流器温高", "IGBT过温", "变流器过热", "变流器IGBT温度高", "变流器温度异常"],
        "causes": [
            {"key": "CoolantPumpFault", "name": "冷却水泵故障/流量不足", "prior": 0.40, "scenario": "cvt_pump",
             "signature": {"cooling_airflow": 0, "generator_winding_temp": 0},
             "checks": ["冷却水泵电流与出口压力", "冷却液液位"],
             "actions": [{"key": "ReplaceCoolantPump", "name": "检修或更换变流器冷却水泵", "parts": ["SP-041"], "hours": 6, "needs": ["climb", "offshore"], "doc": ("WI-CV-001", "2.3")}]},
            {"key": "HeatsinkDust", "name": "散热器积尘/滤网堵塞", "prior": 0.35, "scenario": "cvt_dust",
             "signature": {"cooling_airflow": -1, "generator_winding_temp": 0},
             "checks": ["散热器与滤网清洁度"],
             "actions": [{"key": "CleanHeatsink", "name": "清理散热器并更换滤网", "parts": ["SP-043"], "hours": 3, "needs": ["climb", "offshore"], "doc": ("WI-CV-001", "2.4")}]},
            {"key": "IGBTAging", "name": "IGBT模块老化", "prior": 0.25, "scenario": "cvt_igbt",
             "signature": {"cooling_airflow": 0, "generator_winding_temp": 1},
             "checks": ["IGBT导通压降测试", "谐波与开关损耗评估"],
             "actions": [{"key": "ReplaceIGBT", "name": "评估并更换IGBT模块", "parts": ["SP-042"], "hours": 10, "needs": ["climb", "offshore", "hv"], "doc": ("WI-CV-001", "3.1")}]},
        ]},
    "HydraulicPressureLow": {
        "name": "液压系统压力低", "comp": "hydraulic", "sensor": "hydraulic_pressure", "doc": ("WI-HY-001", "3.1"),
        "synonyms": ["液压压力低", "液压系统欠压", "液压站压力不足", "液压压力异常"],
        "causes": [
            {"key": "OilLeak", "name": "管路/密封泄漏", "prior": 0.45, "scenario": "hyd_leak",
             "signature": {"hydraulic_oil_level": -1},
             "checks": ["管路接头与密封件渗漏", "液压油位"],
             "actions": [{"key": "FixLeak", "name": "更换密封件并补油", "parts": ["SP-051"], "hours": 5, "needs": ["climb", "offshore"], "doc": ("WI-HY-001", "3.1")}]},
            {"key": "PumpFault", "name": "液压泵故障", "prior": 0.30, "scenario": "hyd_pump",
             "signature": {"hydraulic_oil_level": 0},
             "checks": ["液压泵出口压力与电机电流"],
             "actions": [{"key": "ReplaceHydPump", "name": "更换液压泵总成", "parts": ["SP-052"], "hours": 8, "needs": ["climb", "offshore"], "doc": ("WI-HY-001", "3.3")}]},
            {"key": "AccumulatorFault", "name": "蓄能器失效", "prior": 0.25, "scenario": "hyd_accum",
             "signature": {"hydraulic_oil_level": 0},
             "checks": ["蓄能器充氮压力"],
             "actions": [{"key": "ReplaceAccumulator", "name": "补氮或更换蓄能器", "parts": ["SP-053"], "hours": 4, "needs": ["climb", "offshore"], "doc": ("WI-HY-001", "3.5")}]},
        ]},
    "MainBearingTempHigh": {
        "name": "主轴承温度过高", "comp": "main_shaft", "sensor": "main_bearing_temp", "doc": ("WI-MS-001", "2.2"),
        "synonyms": ["主轴温高", "主轴承过热", "主轴承温度异常", "主轴承温度高"],
        "causes": [
            {"key": "LubeFailure", "name": "润滑系统故障", "prior": 0.60, "scenario": "ms_lube",
             "signature": {"gearbox_vibration": 0, "tower_vibration": 0},
             "checks": ["自动润滑泵工作状态", "油脂管路"],
             "actions": [{"key": "FixLube", "name": "检修润滑泵并补脂", "parts": ["SP-061", "SP-033"], "hours": 4, "needs": ["climb", "offshore"], "doc": ("WI-MS-001", "2.2")}]},
            {"key": "MainBearingWear", "name": "主轴承磨损", "prior": 0.40, "scenario": "ms_wear",
             "signature": {"gearbox_vibration": 1, "tower_vibration": 0},
             "checks": ["主轴承振动与间隙检测"],
             "actions": [{"key": "InspectMainBearing", "name": "主轴承状态检测与评估", "parts": [], "hours": 10, "needs": ["climb", "offshore"], "doc": ("WI-MS-001", "3.2")}]},
        ]},
    "TowerVibrationHigh": {
        "name": "塔筒振动超限", "comp": "tower", "sensor": "tower_vibration", "doc": ("WI-TW-001", "2.1"),
        "synonyms": ["塔筒振动大", "塔筒抖动", "塔筒振动异常", "塔筒振动高"],
        "causes": [
            {"key": "BoltLoose", "name": "塔筒连接螺栓松动", "prior": 0.35, "scenario": "tw_bolt",
             "signature": {"gearbox_vibration": 0, "rotor_speed": 0},
             "checks": ["法兰螺栓预紧力复检"],
             "actions": [{"key": "TightenBolts", "name": "复紧/更换塔筒螺栓", "parts": ["SP-071"], "hours": 10, "needs": ["climb", "offshore"], "doc": ("WI-TW-001", "2.1")}]},
            {"key": "BladeImbalance", "name": "叶片质量/气动不平衡", "prior": 0.35, "scenario": "tw_blade",
             "signature": {"gearbox_vibration": 1, "rotor_speed": 0},
             "checks": ["叶片桨距角一致性", "叶片覆冰/损伤检查"],
             "actions": [{"key": "BalanceBlade", "name": "叶片检查与配重调整", "parts": ["SP-072"], "hours": 12, "needs": ["climb", "offshore"], "doc": ("WI-TW-001", "2.3")}]},
            {"key": "FoundationScour", "name": "基础冲刷/刚度下降", "prior": 0.30, "scenario": "tw_scour",
             "signature": {"gearbox_vibration": 0, "rotor_speed": -1},
             "checks": ["基础冲刷水下检测", "固有频率监测"],
             "actions": [{"key": "ScourSurvey", "name": "基础水下检测评估", "parts": [], "hours": 16, "needs": ["offshore"], "doc": ("WI-TW-001", "4.2")}]},
        ]},
    "CableConductorTempHigh": {
        "name": "海缆导体温度过高", "comp": "cable_body", "sensor": "cable_conductor_temp", "doc": ("WI-CB-001", "3.1"),
        "synonyms": ["海缆温高", "海缆过热", "海缆导体温度异常", "海缆温度高"],
        "causes": [
            {"key": "CableOverload", "name": "载流过大/散热条件变化", "prior": 0.60, "scenario": "cable_overload",
             "signature": {},
             "checks": ["海缆载流量与负荷曲线", "埋深与海床热阻变化"],
             "actions": [{"key": "ReviewCableLoad", "name": "复核送出负荷(需授权人员决定)", "parts": [], "hours": 1, "needs": [], "doc": ("WI-CB-001", "3.1")}]},
            {"key": "CableDamage", "name": "外力破坏/绝缘劣化", "prior": 0.40, "scenario": "cable_damage",
             "signature": {},
             "checks": ["海缆路由巡检与AIS船舶扰动核查", "局放监测"],
             "actions": [{"key": "CableSurvey", "name": "海缆路由探测与修复评估", "parts": ["SP-081"], "hours": 24, "needs": ["offshore"], "doc": ("WI-CB-001", "4.1")}]},
        ]},
    "TransformerOilTempHigh": {
        "name": "主变油温过高", "comp": "transformer", "sensor": "transformer_oil_temp", "doc": ("WI-OS-001", "2.2"),
        "synonyms": ["主变温高", "主变油温异常", "变压器油温高", "升压站主变过热"],
        "causes": [
            {"key": "CoolingFanFault", "name": "主变冷却风机故障", "prior": 0.55, "scenario": "tr_fan",
             "signature": {},
             "checks": ["冷却风机启停与电机电流"],
             "actions": [{"key": "ReplaceTrFan", "name": "检修/更换主变冷却风机", "parts": ["SP-092"], "hours": 5, "needs": ["offshore", "hv"], "doc": ("WI-OS-001", "2.2")}]},
            {"key": "OilShortage", "name": "变压器油位偏低", "prior": 0.45, "scenario": "tr_oil",
             "signature": {},
             "checks": ["油位计与呼吸器"],
             "actions": [{"key": "RefillTrOil", "name": "补充变压器油", "parts": ["SP-091"], "hours": 4, "needs": ["offshore", "hv"], "doc": ("WI-OS-001", "2.4")}]},
        ]},
}
FAULT_BY_SENSOR = {f["sensor"]: k for k, f in FAULTS.items()}
CAUSE_SCENARIO = {(fk, c["key"]): c["scenario"] for fk, f in FAULTS.items() for c in f["causes"]}

# 阈值规则: (code, sensor, comp, fault_key, direction, l1, l2, l3, window_s)
# 其中 low 方向规则仅作为预警触发(冷却风量等辅助量不独立产生工单, 见 RULE_SECONDARY)
RULES = [
    ("R-GB-OILT", "gearbox_oil_temp", "gearbox", "GearboxOilTempHigh", "high", 75, 85, 95, 300),
    ("R-GB-VIB", "gearbox_vibration", "gearbox", "GearboxVibrationHigh", "high", 5, 7, 9, 300),
    ("R-GN-WIND", "generator_winding_temp", "generator", "GeneratorWindingTempHigh", "high", 115, 125, 135, 300),
    ("R-GN-BEAR", "generator_bearing_temp", "generator", "GeneratorBearingTempHigh", "high", 78, 88, 98, 300),
    ("R-CV-IGBT", "converter_igbt_temp", "converter", "ConverterIGBTTempHigh", "high", 75, 85, 95, 300),
    ("R-HY-PRES", "hydraulic_pressure", "hydraulic", "HydraulicPressureLow", "low", 165, 150, 130, 180),
    ("R-MS-TEMP", "main_bearing_temp", "main_shaft", "MainBearingTempHigh", "high", 62, 72, 82, 300),
    ("R-TW-VIB", "tower_vibration", "tower", "TowerVibrationHigh", "high", 6, 8, 10, 300),
    ("R-CB-TEMP", "cable_conductor_temp", "cable_body", "CableConductorTempHigh", "high", 75, 85, 92, 300),
    ("R-OS-TR", "transformer_oil_temp", "transformer", "TransformerOilTempHigh", "high", 75, 85, 95, 300),
]

# 规程文档元数据在 seed_docs.py 中。安全作业约束:
SAFETY_LIMITS = {
    "climb": {"max_wave": 1.5, "max_wind": 12.0, "min_visibility_km": 2.0, "quals": ["offshore", "climb"], "permit": "climb"},
    "offshore": {"max_wave": 1.5, "max_wind": 12.0, "min_visibility_km": 2.0, "quals": ["offshore"], "permit": "offshore"},
    "hv": {"max_wave": 2.0, "max_wind": 15.0, "min_visibility_km": 1.0, "quals": ["hv_electric"], "permit": "hv"},
}
# 属于“禁止 Agent 执行 / 仅提示”的高风险关键词(L3)
L3_KEYWORDS = ["停机", "降负荷", "限功率", "修改定值", "参数修改", "修改参数", "带电作业", "复位", "远程控制", "解列", "合闸", "分闸"]

# 术语词表: category -> [(std_key, std_name, [synonyms])]
TERMS: dict[str, list[tuple[str, str, list[str]]]] = {
    "fault": [(k, f["name"], f["synonyms"]) for k, f in FAULTS.items()],
    "component": [
        ("gearbox", "齿轮箱", ["GB", "增速箱", "齿轮箱体", "增速齿轮箱"]),
        ("generator", "发电机", ["GEN", "发电机组", "电机"]),
        ("converter", "变流器", ["CVT", "变频器", "逆变器", "换流器"]),
        ("hydraulic", "液压系统", ["液压站", "液压", "HYD"]),
        ("main_shaft", "主轴", ["主轴承", "主轴系统", "传动轴"]),
        ("blade", "叶片", ["桨叶", "风轮叶片"]),
        ("tower", "塔筒", ["塔架", "塔体"]),
        ("transformer", "主变压器", ["主变", "升压变", "变压器"]),
        ("cable_body", "海缆", ["海底电缆", "集电线路海缆", "电缆"]),
    ],
    "symptom": [
        ("TempHigh", "温度升高", ["温高", "超温", "过热", "温度持续升高", "油温升高", "温度异常升高"]),
        ("VibHigh", "振动增大", ["振动大", "振动超限", "抖动", "振动异常"]),
        ("PressLow", "压力降低", ["欠压", "压力低", "压力不足", "压力下降"]),
        ("Leak", "泄漏", ["渗漏", "漏油", "漏液"]),
        ("Noise", "异响", ["噪声", "声音异常", "啸叫"]),
    ],
    "cause": [(f"{fk}.{c['key']}", c["name"], [c["name"].split("/")[0]]) for fk, f in FAULTS.items() for c in f["causes"]],
    "action": [],
}
_act: dict[str, tuple[str, list[str]]] = {}
for _f in FAULTS.values():
    for _c in _f["causes"]:
        for _a in _c["actions"]:
            _act.setdefault(_a["key"], (_a["name"], [_a["name"].replace("更换", "替换"), _a["name"].split("并")[0]]))
_act["CleanFilter"][1].extend(["清理滤网", "清洁滤网", "滤网清理", "清理进风口积尘", "清理冷却器积尘"])
_act["RefillOil"][1].extend(["补充润滑油", "补油", "添加润滑油", "补充齿轮油"])
TERMS["action"] = [(k, v[0], list(dict.fromkeys(v[1]))) for k, v in _act.items()]


def fault_for_sensor(sensor: str) -> str | None:
    return FAULT_BY_SENSOR.get(sensor)


def cause_def(fault_key: str, cause_key: str) -> dict | None:
    f = FAULTS.get(fault_key)
    if not f:
        return None
    for c in f["causes"]:
        if c["key"] == cause_key:
            return c
    return None
