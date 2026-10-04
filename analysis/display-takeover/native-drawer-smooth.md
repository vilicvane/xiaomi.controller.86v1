# 松手动画的呈现节奏

这是独立的 native-drawer-smooth 版本；旧 drawer 和 ease 冻结材料保持原字节。
旧 ease 的只读采样见 drawer-ease-timing-review-1.50.10.json：松手后的首次计算
出现约119/129px的跳跃。上一GUI时间加上120ms cubic ease-out较快的前段，
会放大帧间隔差异。采样不是原子快照，也不是LCD录像，没有证明动画首帧前
已经耗尽120ms，或手指按住时自动执行了收起动画。

新方案从最后一次有效提交的位置开始，先提交起始画面，再读新时钟。
松手后的剩余行程使用150ms smoothstep，前后减速；一次成功提交最多推进
30ms的曲线进度。队列、合成或PAN迟到时保留中间位置，而不跳到旧绝对时间
对应的位置。因此实际总时长随设备性能调整，不保证150ms墙钟时长。
手指按住时继续直接跟随，不把松手缓动叠加到触摸位移上。

只有起始画面使用PAN返回后的新时钟作为零点。后续成功帧保留计算该位置的
时刻，让下一帧计入本帧的合成/PAN耗时，再执行30ms上限。若每次都在PAN
之后重新排除渲染耗时，低帧率时逻辑进度会过慢，所以不能混淆这两种锚点。

smoothstep整数式为 from + (target-from)*t*t*(450-2*t)/3375000，
t范围0..150；最大绝对中间乘积1,080,000,000，适合signed int32。
进度和起点必须在PAN/时钟错误时保持可恢复，量化成相同像素的位置也不能
让进度永久停住。最后仍通过原publisher/ring释放门交接显示和触摸所有权。

该版本继续复用原GUI和后台服务，只替换两个NOR页中的已有程序容器。
安装基线和回退目标都是精确已验证的 native-drawer-ease，不接受部分写入
或其他固件。安装入口：

```powershell
.\scripts\Set-PanelNativeDrawerSmooth.ps1 -Mode install
.\scripts\Set-PanelNativeDrawerSmooth.ps1 -Mode restore
```

restore先回ease，再用对应旧安装器依次回首版drawer、broker、stock。
源码/实际ELF模型/固定写入器mock及独立审查必须完成后才能冻结并操作设备。
模型验证与实机观察分开记录；实际结果见native-drawer-smooth-hardware-result.json。
