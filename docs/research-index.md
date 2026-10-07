# 研究及历史版本索引

本页把保存的研究证据按问题和版本连接起来。当前已安装版为 **native-image-drawer**；
每个历史 result 的 `installed` 表示当轮曾安装，不表示现在仍运行那个版本。
当前验证见 [架构](architecture.md)，操作入口见 [开发流程](development.md)。

## 早期问题与已得到的结论

| 研究问题 | 结论与证据 |
| --- | --- |
| 配网失败是否为 Wi-Fi 残留 | 历史 1.48.5 已完成关联/IP，失败在云登录；RAM 身份缓存异常，限定身份验证后恢复，见 [恢复记录](../analysis/recovery-summary.md) |
| BES 引脚连到哪些设备 | [针脚映射](../analysis/pinout/panel-pinmap-1.50.10.json)与 [触摸输入路由](../analysis/pinout/a7-touch-input-route-1.50.10.json)，物理连线待确认项单列 |
| 能否只写显示寄存器接管 | LCDC/DSI 测试未见变化；实际像素源提交成功，后续 [native counter](../analysis/display-takeover/native-counter.md)证明设备端显示和触摸 |
| 原界面能否退出后反复重启 | 生命周期有悬挂与重复初始化边界，见 [生命周期审查](../analysis/display-takeover/vapp-lifecycle-switch-review-1.50.10.json)；采用只启动一次的 owner broker |
| 原显示与触摸如何交接 | [所有权审查](../analysis/display-takeover/ui-switch-ownership-review-1.50.10.json)与 [broker](../analysis/display-takeover/native-ui-broker.md)，两显示提交及两输入路径须共同处理 |
| Flash 的空白是否可直接使用 | [容量统计](../analysis/flash-capacity-summary-1.50.10.json)只是内容模式；加载长度、BSS、OTA 与保留范围约束另见 [工程约束](engineering-notes.md) |
| 原厂字体可否复用 | [字体可行性](../analysis/image-push/font-resource-feasibility-1.50.10.json)仅静态分析，未做实机字体/glyph API 调用 |

### 配网诊断的保留结论

其他 SSID 可以只是扫描记录，不能据此认定残留配置。1.48.5 的 `device.info` 创建失败
路径未继续读取出厂身份，却返回成功，RAM 保留编译预置值；底层文件失败原因未确认。
只修改 DID/key 各 32B RAM，每轮保存原值并读回，未清空 NOR。首次授权失败可能与 BLE
身份不同有关，仍是未证实假设。后续原程序自行加载真实身份，完全断电后云连接/控制
正常；这个历史验证不能替代后续每版 UI 的米家或冷启动结果。

## 原生 UI 演进

每一行对应独立源码、manifest、freeze、模型及硬件结果，集合保留原路径与字节。
“完整断电”只记录该版自己的证据，不继承前版结果。代码 byte 数来自保存的 manifest/result。

| 版本 | 代码规模 | 该轮进展及边界 | 完整断电 |
| --- | --- | --- | --- |
| [native counter](../analysis/display-takeover/native-counter.md) | 白色 966B | 常驻 A7 计数，替换旧 UI 入口；暖启动白色与粉色冷启动分开 | 粉色通过；白色独立观察未补做 |
| [broker v1](../analysis/display-takeover/native-ui-broker.md) | 2652B | 原 UI 只进入一次，第三键三击交接显示/触摸；往返及米家控制通过 | 通过 |
| [first drawer](../analysis/display-takeover/native-drawer.md) | 3224B | 顶边下拉、上滑、短拉回弹；用户功能通过但希望更自然 | 当轮 pending |
| [ease](../analysis/display-takeover/native-drawer-ease.md) | 3264B | 松手剩余行程 cubic ease-out；用户/米家通过，上滑仍偏突然 | 通过 |
| [smooth](../analysis/display-takeover/native-drawer-smooth.md) | 3368B | 新提交位置作锚、每帧进度限制；用户手感通过 | 用户跳过 |
| [GitHub card](../analysis/display-takeover/native-github-card.md) | 3432B | GitHub logo、用户名、项目名及 Star 提示；排版/手势通过 | 用户跳过 |
| [GitHub tap v1](../analysis/display-takeover/native-github-tap.md) | 主 3392B + aux 291B | 松手累加及自动恢复；用户报告间歇慢/漏点，原因未证实 | 用户跳过 |
| [GitHub tap-fast](../analysis/display-takeover/native-github-tap-fast.md) | 主 3336B + aux 431B | PAN 后计时与局部软件绘图；用户决定 Demo 不再改，不能说实际卡顿已解决 | 用户跳过 |
| [image drawer](../analysis/image-push/native-image-drawer.md) | 主 3416B + aux 424B | 当前版，TCP 接图/IP显示；两图、手势及米家控制通过，图片 RAM-only | 用户跳过 |

tap-fast 减少软件画布写量 93.45%，原 PAN 仍整帧处理，触摸 ring 仍为 8 个样本。
离线故意丢 UP 可复现合并点击/移动等行为，但实际间歇问题没有证据归因为 ring 溢出；
两轮非原子采样没记录到 count 变化，也不构成实机延迟证明。

ease 旧动画首帧跳跃的只读采样中，第一次计算的 shown 从 233/220 跳至 114/91，起点
已过 25/30ms；不能写成已证明整段 120ms 在首帧前耗尽。smooth 修正了时间锚和逻辑
推进，不改写已经冻结的 ease 证据。所有历史三击逻辑均保留；移除只属于下一维护版。

### 实机结果与冻结入口

结果都在 `analysis/persistence/`，每版 `<variant>-hardware-result.json` 单列离线、安装、
暖启动和用户观察，`<variant>-frozen-inputs.json` 绑定精确输入。常用入口如下：

- [counter 结果](../analysis/persistence/native-counter-hardware-result.json)
- [broker 结果](../analysis/persistence/native-ui-broker-hardware-result.json)
- [first drawer 结果](../analysis/persistence/native-drawer-hardware-result.json)
- [ease 结果](../analysis/persistence/native-drawer-ease-hardware-result.json)
- [smooth 结果](../analysis/persistence/native-drawer-smooth-hardware-result.json)
- [card 结果](../analysis/persistence/native-github-card-hardware-result.json)
- [tap v1 结果](../analysis/persistence/native-github-tap-hardware-result.json)
- [tap-fast 结果](../analysis/persistence/native-github-tap-fast-hardware-result.json)
- [image drawer 结果](../analysis/persistence/native-image-drawer-hardware-result.json)与
  [93 项 freeze](../analysis/persistence/native-image-drawer-frozen-inputs.json)

历史三击样本、源码和结论不能因下一版取消入口而删掉；它们也是精确回退的一部分。

## NOR 执行器研究

| 文档 | 内容 |
| --- | --- |
| [NOR 编程审查](../analysis/persistence/nor-programming-review.md) | 控制器、保护状态及写入条件 |
| [BOOT 独立初始化闭包](../analysis/persistence/boot-independent-init-nor-closure.md) | 与应用上下文隔离的恢复范围 |
| [BOOT 读取 runner](../analysis/persistence/boot-nor-read-runner.md) | 只读调用与状态闭合 |
| [BOOT hook runner](../analysis/persistence/boot-nor-hook-runner.md) | 停点和受控调用路线 |
| [固定原生应用 writer](../analysis/persistence/boot-nor-native-app-runner.md) | 固定扇区写入及 safe-to-resume gate |
| [padding 测试计划](../analysis/persistence/boot-nor-padding-test-plan.md) | 当轮监督下的写入边界研究 |

这些研究不授权照抄其中旧命令到当前 triple。`0x40140000` 访问曾锁总线，当前逻辑
controller 0 为 `0x40148000` 且要先验证 live pointer table。任何不确定 native 调用后
保留停止状态，不能回放旧 CPU/SRAM 或自动推进。逐级恢复表见 [开发流程](development.md)。

## 原始记录归档

- [整理前工程原文](research/engineering-log-through-image-drawer.md)：逐轮发现、失败和修正完整保留。
- [整理前开发原文](research/legacy-development-log.md)：工具、旧版本命令及冻结流程完整保留。

归档正文里的“当前”指对应实验轮次。维护时先看现阶段入口，再用这些原文追溯具体
结论；不从历史段落推断现在的安装版本或未经记录的新功能。
