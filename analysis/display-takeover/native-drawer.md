# 顶边下拉覆盖层

这是本机官方 1.50.10 上的设备端常驻 UI 新版本，保留原应用和米家服务。
代码和安装材料独立于已经验证的 native-ui-broker，不覆盖它的冻结输入。

从原界面逻辑顶边 20 像素内按下并下拉，深灰计数器随手指向下覆盖原画面。
下拉至少 80 像素后松手自动展开，否则收回。在自定义界面上滑至少 80 像素
后松手收起；未移动超过 12 像素的接触在松手时只加一，长按不重复计数。
横向手势取消后仍消费完整触摸。第三键三击仍可往返，不需要重启。
沿用默认启动自定义界面；先上滑或三击第三键可返回原界面，再测试顶边下拉。

## 输入与显示

小 bootstrap pthread 等待 GUI 初始化并安装定时器代理，随后退出。计数、按键、
识别和合成均由 GUI 线程处理，不再增加第三个触摸订阅。通过 GUI FD 的 upper
与物理驱动 upper 匹配来识别实体触摸，不依赖 LVGL 列表顺序，不重复计算虚拟输入。

原始 read callback 输出 x/y 为 int32 @+0/+4，state/continue 为 byte +0x12/+0x13。
顶边触摸在第一帧 DOWN 起拦截，取消也消费到 UP；另一输入已经按下时不截取新的
顶边手势，保留它的完整事件。动画期间新接触一直消费到释放，最终交接仍等两次
GUI 扫描、原始按下状态清零、两个 GUI ring 和显示队列清空，并锁 publisher。

同时代理 PAN 和 UPDATEAREA。覆盖层拖动/动画及展开后禁止原提交；原应用继续
后台绘图。在 GUI TIMER 返回且显示队列为空时拍摄原缓冲区快照，合成到独立
画布。两个画布共 1228800 字节；仅队列为空时改写提交源，不释放仍可能被使用的
分配。动画按照 monotonic 时间推进，最长单次时间步长 50 ms。
这个快照点不证明所有其他线程的直接 mmap 写入均串行，背景是否撕裂和帧率需实测。
背光和息屏策略仍由原系统管理。

## 代码空间与回退

仍只操作 NOR 92b000/ccd000 两个 4 KiB 扇区。除原来让出的工厂/诊断容器，
新借用 wifi_recorder 的 472 字节 worker，范围 3804bc98..3804be70。
该诊断命令入口 NOR ccdd2c 改为返回 -38，防止运行被替换的 worker。
这不是 Wi-Fi 驱动；启动流程不使用该命令。be70 起的共享消息 helper 保留原字节。
新的独立审查记录来路扫描、边界和输入 hash。

安装仅接受精确的旧 broker 两页，回退恢复精确 broker 两页，保留三击切换。
原 stock 与旧计数器不得直接调用本安装器；需要按其各自已审核流程转换。

```powershell
.\scripts\Set-PanelNativeDrawer.ps1 -Mode install
.\scripts\Set-PanelNativeDrawer.ps1 -Mode restore
```

两项均写入设备并重启一次。没有 --execute 的 Python wrapper 只核对冻结材料。
GUI 状态仅只读检查可使用 diagnostics/read-native-drawer-runtime.cfg。
context 从 384fc864 读取；mode/wanted/ready @+24/+28/+2c，count @+34，
overlay/cover/target/shown @+50/+54/+58/+5c，GUI 进度 @+64，最近 PAN @+6c，
最后物理 x/y @+70/+74。上述偏移均为十六进制。

源码、ARM 模型和写入器 mock 是离线证据。新版本实际观察、NOR 读回和断电启动
单独记录在 native-drawer-hardware-result.json，不用旧 broker 的结果替代。
