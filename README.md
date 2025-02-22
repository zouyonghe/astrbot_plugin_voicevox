# VOICEVOX 插件

基于 VOICEVOX Engine 的日语文本转语音插件。

## 功能概述

- 支持日语文本的语音生成。
- 支持列出音声及风格信息。
- 可设置默认音声和风格。
- 提供启用和禁用 VOICEVOX 功能的命令。

## 使用说明

### 安装

对于Linux系统，可以使用 docker-compose 部署 VOICEVOX engine。

首先下载项目附带的 `docker-compose.yml` 文件。

1. **安装 NVIDIA Container Toolkit**  
   根据发行版安装自行安装如下软件：
   ```bash
   nvidia-container-toolkit
   ```

2. **配置 NVIDIA Runtime**  
   配置 Docker 使用 NVIDIA 运行时并重启 Docker 服务：
   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

3. **启动容器**  
   在项目目录下，使用以下命令启动带有 VOICEVOX Engine 的 Docker 容器：
   ```bash
   docker-compose up -d
   ```

### 配置

在插件初始化时提供以下配置：

- `enable_voicevox`：
    - 类型：`bool`
    - 描述：启用 VOICEVOX 文本转语音。
    - 默认值：`true`
    - 提示：默认启用，可使用 `/voicevox enable` 启用，或 `/voicevox disable` 禁用。
- `voicevox_url`：
    - 类型：`string`
    - 描述：VOICEVOX Engine 的 API 地址。
    - 默认值：`http://127.0.0.1:50021`
    - 提示：格式：协议 + IP 或域名 + 端口号，例如：http://127.0.0.1:50021 或 http://example.com:50021。
- `default_voice`：
    - 类型：`string`
    - 描述：当前音声名称。
    - 默认值：空
    - 提示：使用 `/voicevox voice list` 获得所有可用音声。
- `default_style`：
    - 类型：`string`
    - 描述：当前风格名称。
    - 默认值：空
    - 提示：使用 `/voicevox style list` 获得所有可用风格。

### 使用命令

#### VOICEVOX 功能开关

- `/voicevox enable`：启用 VOICEVOX。
- `/voicevox disable`：禁用 VOICEVOX。

#### 生成语音

- `/voicevox gen <文本>`：生成日语文本语音。

#### 音声管理

- `/voicevox voice list`：列出所有可用音声。
- `/voicevox voice set <音声索引>`：设置默认音声。

#### 风格管理

- `/voicevox style list`：列出当前默认音声的所有风格。
- `/voicevox style set <风格索引>`：设置当前音声的默认风格。

## 注意事项

- 本插件仅支持日语文本转语音，请确保输入内容为日语。
- 请先设置音声（voice）再设置风格（style）

