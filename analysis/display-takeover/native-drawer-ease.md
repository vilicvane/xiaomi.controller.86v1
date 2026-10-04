# 下拉覆盖层的回弹曲线

本版本仅调整设备端覆盖层的松手动画。此前 native drawer 的下拉、收起、点击和
三击往返已由用户实测通过，但用户反馈动画稍慢、缺少 easing。旧版本46项冻结
材料保持原字节。新版本使用独立的 native-drawer-ease 源码、构建与安装器。

手指按住时仍按真实位移直接绘制。松手后改为名义120ms的 cubic ease-out：
前段移动较快，接近终点时减速；完整展开或收起不靠每帧固定步长累计。
时间来自原系统 monotonic clock，队列阻塞后按当前经过时间追上曲线。
UP使用上一GUI扫描的clock记录起点，实际时长有一帧的量化误差。

整数公式为 target - (target-from)*(120-elapsed)^3/120^3；elapsed>=120 时
直接到终点。delta 和 remaining 都为 signed int，最大绝对乘积552960000，
在int32范围内。elapsed以uint32差值处理单次clock回绕。不使用浮点运算。

输入、快照、最终 publisher/ring 交接及保留第三键均沿用前一版本。
同一3432B代码容器；Wi-Fi录制诊断入口已由前版本停用，本版不再改入口内容。
仍保留审核的两个完整扇区事务，新安装基线为精确 native drawer 第一版两页。

```powershell
.\scripts\Set-PanelNativeDrawerEase.ps1 -Mode install
.\scripts\Set-PanelNativeDrawerEase.ps1 -Mode restore
```

restore 返回第一版 drawer；之后可用 Set-PanelNativeDrawer.ps1 回 broker，
再用 Set-PanelNativeUiBroker.ps1 回 stock。不要跨版本直接运行另一安装器。

新模型检查真实ARM整数计算、开合方向、端点、部分位移和clock回绕；原16组
输入/显示所有权模型也继续绑定。模型不是实机帧率证明，用户反馈独立记录在
native-drawer-ease-hardware-result.json。背光策略继续沿用原系统。
