# 设备端 GitHub 信息卡

在1.50.10的smooth抽屉基础上替换内容绘制：深色背景、居中的白色GitHub标志，
下面是白色用户名 `vilicvane`、灰色项目名 `xiaomi.controller.86v1`，底部用金色
五角星和 `Star on GitHub` 提示支持项目。逻辑画布480×320；用户名与项目分别
使用3倍、2倍的5×7像素字体。

GitHub标志取自[官方品牌资源](https://brand.github.com/foundations/logo)的白色PNG，
下载包为 https://brand.github.com/GitHub_Logos.zip 。原PNG与下载ZIP保留在被忽略的
reference目录。固件只保存24×24的一位图并等比绘制为48×48；头文件记录原资产SHA。
星形与字体为紧凑列位图，文本索引固定，显示过程中不用电脑绘图。

参考像素图由render_github_card_reference.py独立生成，不能单独证明设备绘制。
必须将真实ARM程序的画布与参考像素比对，包括全部cover0..320、整块画布和前后
内存保护区；私有图形内核还要校验寄存器、SP恢复及栈对齐。截图是逻辑RGB32，
实屏颜色和旋转仍以用户观察为准。

手指跟随、150ms逻辑缓入缓出、每个成功帧最多推进30ms、顶边下拉和第三键三击
继续使用上一版流程。原UI/JS和后台服务继续运行。显示与触摸仍在最终publisher
锁和ring释放门交接；新图形代码不得扩展3432B容器或接入新的原生API。

程序为独立native-github-card版本，安装基线和回退目标是精确的smooth两页：

```powershell
.\scripts\Set-PanelNativeGitHubCard.ps1 -Mode install
.\scripts\Set-PanelNativeGitHubCard.ps1 -Mode restore
```

旧源码、二进制和冻结材料保留原字节。新安装仍只通过固定BOOT写入器更新两个
已审核的NOR页，再重启一次；warm读回、用户观察与旧版结果分别记录。
用户已确认smooth手感良好，并明确跳过完整断电测试；不把跳过记录成通过。

当前BIN3432B（ELF allocated3428B加4B空隙），恰好占满3804b108..3804be70容器，
不能再往后增加代码。源码/容量和安装器审查通过；51项冻结绑定当前模型、绘图
资源及四套旧材料。27组实际ARM检查和43项Jim写入器路径通过，模拟不访问设备。
实机安装、完整两页读回及正常重启后的custom owner/GUI活跃检查已通过，
实际排版、颜色和手势观察见native-github-card-hardware-result.json。
