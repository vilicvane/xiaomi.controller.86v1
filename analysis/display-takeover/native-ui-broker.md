# 常驻计数器与原界面切换

该原型针对这台 `xiaomi.controller.86v1` 的 1.50.10 镜像。第三个物理键为
P3_1（GPIO input `0x40081050` 的 bit25，低电平按下）。三次完成的短按请求
切换显示和触摸所有权；每次短按最多 600 ms，相邻释放/按下不超过 500 ms，
去抖 40 ms。长按、组合键或超时取消这一组。该键当前没有米家动作绑定。

启动包装只调用一次原 `vapp`，再增加设备端 pthread。原 UI/JS 和面板服务继续
运行；自定义界面持有一个 480×320 RGB32 像素缓冲区及自己的触摸订阅。默认进入
白色 `vilicvane +0`；点击加一，长按和拖动只计一次。切换保留计数和原应用状态。
程序没有电脑绘图/按键循环，也没有主动设置背光或息屏策略。

## 交接与资源边界

- GUI 定时器代理在原 GUI 线程内一次安装两个触摸回调和 PAN/UPDATEAREA 两条
  显示提交代理。始终调用原定时器；原 UI 在后台仍处理计时器和绘图。
- 自定义模式照常排空原触摸订阅，覆盖 LVGL 输出的 state 字节 `+0x12` 为 release，
  保留 `+0x13` 的继续读取标志。它不通过关闭某个 FD 实现独占。
- 交接先等待原 GUI 与自有输入均释放及旧显示队列排空，再锁两个触摸 upper 的
  publisher mutex，核对三个订阅 ring 都为空。成功提交新画面后更改 owner，再
  解锁。此边界后发布的新触摸进入新的 owner。
- 原界面的 mmap 缓冲区是板级长期持有的 `0x50000000`，启动时验证格式、大小、
  stride 和单缓冲模式。返回时直接提交该缓冲区，不保存短命 GUI 绘图指针。
- PAN 的 `0xffffffff` 迁移请求在安装代理后拒绝；程序不释放最后呈现的画布。
  它不重进原 main、不发送停止信号、不调用原框架 destroy/recreate。
- 原应用自然退出时发布 alive=0、恢复静态显示回调并返回原状态；不再遍历输入
  节点，不释放仍可能被回调持有的 context/canvas。原框架既有退出缺陷没有修复。

LVGL list 数据节点大小为 `0x80`；prev 在 `+0x80`，next 在 **`+0x84`**。
不要把十六进制结构偏移抄成十进制；state/continue 实际是字节 18/19。
两个 GUI driver 完整建立后才安装，不能把非 NULL list head 当作就绪。

原按键 MCU 通知仍存在。这个 watcher 不过滤原单击/长按动作；以后给第三键
绑定米家动作之前，需要另行实现事件过滤，避免一次按键触发两种功能。

## 镜像与回退

最终 BIN 2652 字节，SHA-256
`8929b02509c2aeff438da8ae8cec41103c9dc7457e209627029de6f192e2f8cf`。
只有两个 4 KiB NOR 扇区：`0x92b000` 代码、`0xccd000` builtin 表。
运行容器是 `[0x3804b108,0x3804bc98)`；BIN 实际到 `0x3804bb64`。
NOR 文件偏移为运行地址转换后 **再加 4**，代码起点 `0x92b10c`。

| builtin | 新入口 | 作用 |
| --- | --- | --- |
| vapp | `0x3804b2f5` | 固定 4 字节 B.W → broker_main |
| faclvgl | `0x3804b111` | 返回成功，防止再次启动 broker |
| showlogo | `0x3804b111` | 省略启动 Logo；保留 board init 和后续 panel_fb_switch |
| ntpcstatus | `0x3804b109`（表值不变） | 返回 -38；NTP daemon 主体仍保留 |

工厂 demo、showlogo、ntpcstatus 诊断功能让出代码空间。原应用包、vapp 主体、
启动复制长度、BSS 边界和设备配置保持原值。安装先完整验证代码，再写入口表；
回退先恢复表，再恢复代码。公共流程只接受完整 original/original 或 broker/broker，
拒绝混合、未知和旧 counter 基线。旧 counter 的冻结 21 项全部保留。

```powershell
.\scripts\Set-PanelNativeUiBroker.ps1 -Mode install
.\scripts\Set-PanelNativeUiBroker.ps1 -Mode restore
```

运行这些命令会写设备并重启，必须满足工程经验中的 BOOT、供电和闭合条件。
已安装 broker 时不要运行旧 counter 安装/回退命令；先用 broker 精确回退。

构建、准备、mock、review、freeze、执行是不同阶段。安装器核对 36 项冻结输入，
包括第一方 header 和测试结果。新构建不可直接重用旧冻结列表。

## 验证状态

手势 host 测试及 ASan/UBSan 通过；实际编译 ELF 在 ARM 模拟器中的 9 项所有权、
触摸和入口检查通过；固定写入器 33 项 Jim 故障路径通过。模拟 API/IRQ/调度不能
证明实机正确。硬件安装、反复往返及完整断电自动启动均通过，断电后米家控制正常。
冷启动再次核对了两个完整扇区、入口和活跃运行状态。结果记录在
`analysis/persistence/native-ui-broker-hardware-result.json`，不以静态报告替代。

运行中只读状态可使用 `diagnostics/read-ui-broker-runtime.cfg`。context 字段从
`0x384fc864` 找到；计数/模式/请求分别在 `+0x34/+0x24/+0x28`，三个进度计数为
`worker_cycles +0x58`、`gui_cycles +0x5c`、`toggles +0x60`，最近呈现结果 `+0x64`。
raw capture、完整镜像、依赖工具和生成的扇区数组继续只保存在本地。
