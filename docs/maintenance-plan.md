# 从研究原型进入维护阶段

记录日期：2026-10-07。研究整理已在 `432cf9b` 阶段性提交。随后建立独立 `firmware/`
维护源码及当前四页发布 `maintained-http-four-page-20261007-d`；四页安装、暖启动、真实
303 跳转与图片上传通过。用户已确认默认 GitHub 卡片显示和手机 LAN 跳转打开网页；
d 的其他界面及米家验收待记录。历史 `native-image-drawer` 及所有
更早的源码、输入和结果保持冻结。
[当前发布结果](../firmware/releases/maintained-http-20261007-d.json)分别记录已完成与待验收项。
c 的双击及息屏用户确认保留在 [旧结果](../firmware/releases/maintained-http-20261007.json)，不继承为 d 验收。

## 用户需求

| 需求 | 维护版实现及验证边界 |
| --- | --- |
| 取消第三键三击切换 | 维护源码已移除自有检测，模型通过；用户实机验收待记录。历史三击源码、记录、结果及回退版原样保留 |
| 自定义画面双击显示 IP 和端口 | 双击切换图片/地址，保留最新 RAM 图片；模型通过，d 用户验收待记录，c 的确认独立保留 |
| 浏览器访问 `IP:port` 到前端页面 | d 的真实 303 到临时 LAN 电脑 5173 前端，Chrome 自动填写地址并上传通过，手机打开页面用户确认通过；手机上传和云 HTTPS 未实测 |
| 锁屏后自动打开自定义界面 | 观察原系统 off 后请求 custom owner，不改变背光；模型通过，d 息屏唤醒用户验收待记录 |

顶边下拉/上滑仍承担原界面往返，原米家应用、系统调度及网络服务继续复用。取消三击
不等于拦截原 MCU 的物理按键动作；保留此前样本与历史行为的完整记录。

## 已实现的维护边界

具体 API 见 [HTTP 图片 API](http-image-api.md)，程序与原系统关系见
[架构](architecture.md)。源码实现与硬件结果分别记录：

- 端口 18086 使用 HTTP，没有 raw TCP 兼容分支。`POST /api/image` 接收固定 VIMG header
  + RGB565 的 307216B body；不要求 Content-Type，校验和与 GUI 安全发布保留，HTTP 202 只确认发布接受。
- 当前 `GET /` 用 HTTP 303 跳转到 `http://PC_LAN_IPV4:5173/`，设备地址通过 fragment
  传入前端；真实 Location 和 Chrome 跟随已检查。电脑地址和开发服务器是临时依赖，
  后续改 hostname 需新冻结发布。Cloudflare 部署尚未完成。
- CORS 为 `*`，OPTIONS 已实现；本轮没有单独重做 OPTIONS。HTTPS 云网页访问局域网的权限、
  mixed content 和浏览器网络条件须单独实测，CORS header 不代表端到端已经可用。
- 双击只接受完整物理轻触序列，手势和虚拟输入不参与；首次唤醒接触从 DOWN 到 UP
  都排除双击，但仍可使用抽屉手势。上传不强制退出地址页。
- 息屏状态来自原 `panel_apps`；代理先执行原 timer，再观察 off 并在安全 GUI 边界交接。
  不强行点亮，不重初始化原字体/GUI。两次采样之间完成的 off/on 无法观察，原厂
  调度路径未穷尽；此前用户确认只属于 c，d 尚未做用户唤醒验收。

## 容量与独立发布

旧 image drawer 在主/辅助容器只余 16B/20B，完整 HTTP 和新交互不能放入原三页布局。
维护版经独立 ownership 审查借用 `uorb_unit_test` 内部的 4080B 网络容器，保留页头 4B、
页尾 12B，以及其他容器末端和相邻 helper。主/辅助既有边界没有扩大。

当前主 2946B、辅助 236B、网络 2948B，四页候选 manifest SHA 为
`aba4a3e5021af175a3d6cd9dc90eac4559154d34711b647bbc8a48043ce5d9fe`。
380 项输入 freeze 的 SHA 为
`3af60edcb71636fbe227237f7c7f8b23d4135571b2e45651583665d4466a2632`。
源码、构建实际 compiler headers、完整原厂页、工具及五类审查证据全部复制到私有
不可覆盖的 release 快照。新版本 canonical 源码可维护，旧快照及历史输入不可修改。

直接恢复目标是精确 image drawer 三页加 stock 网络页，使用该 release 冻结的四页
执行器；再进入历史回退链。恢复命令见 [开发流程](development.md)，不能直接把旧
三页 writer 用于已安装维护版。

本轮用 c 的冻结执行器恢复精确基线后才安装 d；c 恢复和 d 安装均完整闭合且暖启动
读回通过。d 的硬件恢复仍未执行，不能继承 c 的恢复结论。

## 完成标准

阶段一已整理入口、稳定知识、历史索引和维护流程，保留历史材料原字节后提交。
维护版 d 的 24 组 ARM UI、23 组已配置 HTTP、261 项 host parser、93 项 writer mock、
12 项 release 测试及独立 review/freeze 完成；本轮四页读回、native 闭包及暖启动通过。
真实 GET/303、无 Content-Type 的网页完整 POST/202、未指定 `-H` 的 cURL POST/202、
无 type 错误 FNV/422、任意 type 错误 VIMG/400 和拒绝后 GET/303 均通过。

2026-10-07 用户确认 c 的双击地址和息屏唤醒正常，并要求制作支持裁切、缩放的前端。
前端编辑/导出/布局检查独立保留；当前 d 已实测 Chrome 跟随跳转自动填写地址、完整
VIMG/FNV 上传和按钮成功状态，无页面错误。两次有效上传被 GUI 消费，generation/
displayed_generation=2、pending=0、server=1；它们不证明 LCD 可见。用户随后独立确认
默认卡片显示正常和手机访问面板地址能打开前端，范围仅这两项；d 的其他交互和米家
控制仍待记录，手机上传与云 HTTPS 未测试。
开发及验证说明见 [图片编辑前端](frontend.md)。图片持久化和完整独立
固件仍未实现。此前完整断电测试的用户跳过决定有效，不重复要求，也不借用旧版结果。
