"""Combine saved pinmux, static-code evidence and qualified peripheral roles."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "pinout"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


live = read("live-iomux-1.50.10.json")
mcu = read("mcu-pinout-1.50.10.json")
a7 = read("a7-peripherals-1.50.10.json")
sd = read("a7-sdmmc-evidence.json")
roles = {
    0: ("SWD 调试数据 / TMS", "已确认", "专用调试复用；现有 SWD 读通"),
    1: ("SWD 调试时钟 / TCK", "已确认", "专用调试复用；现有 SWD 读通"),
    4: ("Wi-Fi FEM / 射频开关信号", "接口已确认；外部器件待定", "专用 mux13；具体板级接法未确认"),
    6: ("TLSC6x 触控中断", "驱动角色已确认", "A7 触控描述符与 IRQ attach 均指定 pin6；下降沿"),
    7: ("TLSC6x 触控复位", "驱动角色已确认", "A7 触控描述符指定 pin7；输出低20ms/高20ms"),
    14: ("UART0 接收", "已确认", "MCU 启动代码；启动参数 921600 / 8N1 / 无硬件流控"),
    15: ("UART0 发送", "已确认", "MCU 启动代码；启动参数 921600 / 8N1 / 无硬件流控"),
    16: ("TLSC6x 触控：I2C0 时钟", "驱动角色已确认", "实际 I2C 对象 pinconfig 与实时 mux3 一致；原始传输地址字段0x2e，400kHz配置"),
    17: ("TLSC6x 触控：I2C0 数据", "驱动角色已确认", "实际 I2C 对象 pinconfig 与实时 mux3 一致；原始传输地址字段0x2e，400kHz配置"),
    18: ("I2C1 时钟", "接口已确认；具体外设待定", "运行中 mux3"),
    19: ("I2C1 数据", "接口已确认；具体外设待定", "运行中 mux3"),
    22: ("屏幕背光 PWM6", "驱动角色已确认", "ST7797 初始化中配置 pin22 / PWM6；duty字段100，频率字段1000为布局推断"),
    23: ("ST7797 屏幕复位", "已确认", "A7 屏幕驱动；高10ms/低20ms/高120ms"),
    24: ("PDM0 数字音频数据", "接口已确认；具体外设待定", "运行中 mux10；未据此确认麦克风型号"),
    25: ("GPIO 按键候选；key mask 8", "候选", "固件按键配置表与实时 GPIO 上拉一致；实体按键对应未确定"),
    26: ("GPIO 按键候选；key mask 2", "候选", "固件按键配置表与实时 GPIO 上拉一致；实体按键对应未确定"),
    27: ("GPIO 按键候选；key mask 4", "候选", "固件按键配置表与实时 GPIO 上拉一致；实体按键对应未确定"),
    28: ("PDM0 数字音频时钟", "接口已确认；具体外设待定", "运行中 mux10"),
    31: ("PA 控制", "固件角色已确认；器件待定", "MCU 板级初始化为输出低；具体功放及接法未确认"),
}
for entry in sd["pin_array"]["entries"]:
    n = entry["pin_enum"]
    roles[n] = ("MMC 存储：" + entry["function"].removeprefix("SDMMC_"),
                "已确认", "A7 控制器0实际初始化路径；6项数组与实时 mux9 一致")

pins = []
for pin in live["pins"]:
    role, confidence, note = roles.get(pin["gpio_number"], ("GPIO 用途待定", "用途未知", "当前 GPIO 复用不能确定板上连接的器件"))
    pins.append({**pin, "device_role": role, "role_confidence": confidence, "role_note": note})

report = {
    "firmware_version": "1.50.10",
    "backup_sha256": mcu["backup_sha256"],
    "scope": "Target access was read-only NOR and IOMUX capture; remaining work uses saved files. No CPU halt/reset, code execution, RAM write or Flash write.",
    "evidence_files": ["live-iomux-1.50.10.json", "mcu-pinout-1.50.10.json",
                       "a7-peripherals-1.50.10.json", "a7-sdmmc-evidence.json",
                       "reference/source-manifest.json"],
    "pins": pins,
    "display": {"driver": "ST7797", "width": 320, "height": 480,
                "interface": "DSI", "reset_pin": "P2_7",
                "backlight_pin": "P2_6", "backlight_pwm_channel": 6,
                "limits": "Dedicated DSI data/clock package pins are not identified by the ordinary 32-GPIO IOMUX map. See A7 evidence for reset and driver code."},
    "sdmmc": {"configuration_frequency_hz": 48000000, "configuration_bus_width": 4,
               "pins": sd["pin_array"]["entries"],
               "limits": "48MHz is a configured request, not an oscilloscope measurement; package pad and trace locations remain unknown."},
    "limits": live["limits"] + [
        "TLSC6x names the compiled touch driver family; exact physical controller model is not confirmed by a chip-ID read.",
        "Compiled MCU I2C helper defaults are not the live panel routes and are excluded from the active pin table.",
        "Old A7 tail bytes beyond the current length-delimited payload are excluded as evidence of active new firmware.",
        "An 85-pin module connector map cannot be substituted for this bare-chip BGA ball map."],
    "a7_evidence": a7,
}
(OUT / "panel-pinmap-1.50.10.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with (OUT / "panel-pinmap-1.50.10.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["逻辑引脚", "GPIO编号", "实时功能", "硬件mux值", "内部上下拉", "外设或用途", "确定程度", "证据与限制"])
    for p in pins:
        w.writerow([p["pin"], p["gpio_number"], p["function"], p["hardware_mux"], p["pull"],
                    p["device_role"], p["role_confidence"], p["role_note"]])
print("Saved the 32-pin panel map and qualified peripheral evidence.")
