# 自动视频下载分类系统

## 🚀 项目简介

本系统是一个高度集成的自动化工具，旨在通过多种来源（RSS/RSS/magnet/bittorrent）自动下载视频文件/字幕文件，并基于智能分类逻辑进行精准整理。结合AI文本分析与TMDB官方数据源，支持：
* 智能分类：通过用户自定义、AI解析或TMDB标准名称实现三级命名体系，减少用户设置的困难
* 硬链接管理：智能创建跨目录的高效存储结构
* 超分辨率增强：可选视频画质提升功能
* 多平台通知：Telegram等即时消息推送

在理想情况下，用户只需要粘贴一个链接进来就能自动完成下载分类。

提取正确名字的优先级如下：

1. 手动设置
2. AI提取

如果启动了TMDB API，则会自动校准名字。

提取正确剧集和季度的优先级如下：

1. 正则表达式提取剧集（只支持自动提取集，季度需要手动设置）
2. AI提取剧集（季度需要手动设置，这里如果启动了TMDB API会展示一个列表用户选择即可）

最后，使用我的另一个项目RealCUGAN-TensorRT进行超分辨率。

## 🔧 安装步骤（自动）

我们提供已经编译好的docker镜像，你只需要一行指令就能完成部署。

## 🔧 安装步骤（手动）

### 环境准备

``` python
# 推荐使用虚拟环境
python3 -m venv env
source env/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置文件示例 (`config/settings.yaml`)

``` yaml
general:
  listen: 12341
  system_lang: cn
  address:
  - 0.0.0.0
  http_proxy:
  - http://XXXX:1234

download:
  qbittorrent_port: 1234
  qbittorrent_url: 127.0.0.1

hardlink:
  enable: true
  output_base: "/mnt/media/videos"

notifications:
- telegram:
    type: telegram
    telegram_token: "YOUR_BOT_TOKEN"
    chat_id: "-100XXXXXXXXXX"
- telegram:
    type: telegram
    telegram_token: "YOUR_BOT_TOKEN"
    chat_id: "-100XXXXXXXXXX"

tmdb_api:
  enabled: true
  api_key: "TMDB_API_KEY"

llm:
  enable: true
  url: http://xxxx/v1/api
  token: XXXXXXXXX

enhancement:
  enable_sr: false
```

### 启动

``` python
python main.py
```

## 项目运行原理

数据库保存三种项目：
1. 来源项目
2. 种子项目
3. 文件项目

前端包括以下三个页面和用户交互：
1. 展示所有来源的页面、添加新的来源
    * 添加新的来源：
        * 来源类型：一个选项框，用户设置为RSS还是magent
        * 地址：一个输入框
        * 来源名：如果设置了AI，则默认为一个toggle box，使用AI自动识别，否则显示一个输入框让用户输入。在使用AI的情况下，添加时，后端要先根据地址获取文件列表，或者RSS内容，然后自动生成名字，失败则直接返回前端失败。在设置了TMDB API的情况下，将AI提取的或者用户设置的名字，通过API获得标准名字，失败则返回前端失败。
        * 来源视频类型：如果设置了AI，则默认为一个toggle box，使用AI自动识别，否则显示一个选项框让用户选择为movie还是tv。如果为AI，同理来源名。
        * 剧集：如果设置了AI，则默认为一个toggle box，使用AI自动识别，否则显示两个输入框让用户输入正则表达式。
        * 剧集偏移量：如果设置了AI并且启动了TMDB API，则默认为一个toggle box，使用AI自动识别，否则显示一个选项框让用户输入剧集是在识别的基础上的偏移量。
        * 季度：用户手动设置，如果启动了TMDB API那么会显示一个所有可能的季度列表。
        * 是否启用超分辨率：如果配置了超分辨率，则显示该选项，让用户选择是否开启。
    * 展示：
        * 来源名称
        * 来源类型
        * 来源视频类型
        * 季度（如果是tv）
        * 操作（删除、RSS重新开始监控）
        * 展开子项目：
            * 如果是单文件种子
                * 下载进度：每一个下载项目通过qBittorrent API后端定期获取下载进度
                * 超分辨率进度：每一个项目通过API获取超分辨率进度，同理下载进度
                * 添加时间
                * 开始时间
                * 完成时间
                * 剧集和季度（对应的文件项目的信息）
                * qBittorrent下载地址
                * Hash值
                * 操作（超分辨率/下载结束结束后显示，重新开始超分辨率）
            * 如果是多文件种子
                * 下载进度：每一个下载项目通过qBittorrent API后端定期获取下载进度
                * 添加时间
                * 开始时间
                * 完成时间
                * 展开子项目
                    * 文件名
                    * 超分辨率进度：同理下载进度
                    * 剧集和季度
                    * 操作（超分辨率/下载结束后显示，重新开始超分辨率）
2. 用户登陆，第一次打开则需要添加管理员
3. 网页设置，修改现有的设置

在添加magnet到qBittorrent之前，获取文件列表，添加“文件项目”，并和“种子项目”关联。
1. 如果是单文件（保留正片的视频和字幕文件）
    1. 如果来源类型是TV
        1. 根据设置提取剧集
        2. 根据设置
            1. 使用AI+TMDB API修正剧集
            2. 否则使用剧集偏移量修正剧集
        3. 季度已知
    2. 如果来源是Movie
        1. 根据设置提取剧集
        2. 根据设置
            1. 使用AI+TMDB API修正剧集
2. 如果是多文件则遍历文件夹对其中的每个文件执行单文件的操作

前端还用于捕获qBittorrent下载完成之后curl的回调，回调使用种子的Hash进行识别。
在下载完成后，遍历到种子中的每个文件：
1. 如果启动了超分辨率则先进行超分辨率，完成后（回调）跳到3
2. 没有则跳到3
3. 如果开启了硬链接，则根据数据库中的“文件项目”硬链接到对应的位置，完成后跳到5。
    * TV：Root/来源名/季度/来源名 SXXEXX
    * MOVIE：Root/来源名/来源名 EXX
4. 没有则跳到5
5. 通过通知设置，通知用户。
