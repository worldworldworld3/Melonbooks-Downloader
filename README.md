# Melonbooks Downloader

Windows 已购漫画下载与独立转换工具。当前版本：**1.0.0**。

## 下载与运行

从本仓库的 **Releases → v1.0.0** 下载 `Melonbooks.Downloader-1.0.0-windows-x64.zip`，解压后运行 `Melonbooks Downloader.exe`。也可单独下载 EXE。

- Windows 10/11 x64。
- 需要 Microsoft Edge WebView2 Runtime；EXE 已包含 Python 及应用依赖，无需安装 Python 或蜜瓜阅读器。
- 使用自己的 Melonbooks 账号登录。首次运行默认输出到用户的 `Downloads/Melonbooks Downloader`，可在底部更换目录。

## 界面预览

<img width="592" height="420" alt="Snipaste_2026-09-17_09-19-03" src="https://github.com/user-attachments/assets/4f638c7d-3a6a-4439-864e-d00764b7c351" /> <img width="592" height="420" alt="Snipaste_2026-09-17_09-20-03" src="https://github.com/user-attachments/assets/6844df14-a6a7-4c72-ad31-62baf703b1c3" />


## 功能

- 官方网页登录、同步已购书架、切换账号。
- 批量选择、顺序分段下载。
- 每本下载后自动独立解码，支持的结果输出为 ZIP 或 PDF。
- 登录后批量添加或拖入本地 `.melon` / `.ebg` 文件，逐个校验当前账号授权与作品密钥，并转换通过校验的文件。

## 文件与缓存

输出目录只保存转换结果。源文件和下载 JSON 保存在 `%LOCALAPPDATA%/Melonbooks Downloader/source-cache`，设置与随机设备编号保存在该应用目录。源码运行时，设置及缓存位于 `downloader/`。

缓存不会自动删除。“清除缓存”清除所有输出位置对应的应用下载缓存。

本地文件只在本机读取。账号会话及作品授权仅存于运行内存。

## 支持范围

独立解码支持 RIFF/BeBG、KEY v1、AES-128-CBC 的 ZIP/PDF。输出文件系统需支持硬链接，例如 NTFS。

本工具为独立项目，不是 Melonbooks 官方软件。

## 致谢

本项目在开发过程中使用了 OpenAI Codex 辅助编程。

## 许可证

项目自有代码采用 [MIT License](LICENSE)。第三方组件、版权归属和许可原文见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [licenses/](licenses/)。
