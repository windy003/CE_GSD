# GitHub Repository Statistics Extension

一个Chrome插件，用于统计GitHub仓库的代码行数，并提供详细的文件和文件夹分析。

## 功能特性

- 🔍 **自动检测**: 在GitHub仓库页面自动显示代码统计悬浮窗
- 📊 **详细分析**: 显示总代码行数、文件数量、语言分布
- 📁 **文件夹视图**: 可展开的文件夹结构，显示每个文本文件的行数和占比
- ⚙️ **自定义服务器**: 支持配置自定义统计服务器地址
- 🎨 **美观界面**: 现代化的UI设计，与GitHub风格保持一致

## 项目结构

```
├── github-stats-extension/    # Chrome插件文件
│   ├── manifest.json         # 插件配置文件
│   ├── popup.html           # 插件弹出页面
│   ├── popup.js             # 弹出页面逻辑
│   ├── content.js           # 内容脚本
│   ├── content.css          # 悬浮窗样式
│   └── background.js        # 后台脚本
├── github-stats-server/      # Flask后端服务器
│   ├── app.py              # 主应用文件
│   ├── requirements.txt    # Python依赖
│   └── run.py             # 启动脚本
└── README.md              # 说明文档
```

## 安装和使用

### 1. 安装后端服务器

首先需要启动Flask后端服务器：

```bash
cd github-stats-server
python run.py
```

服务器将在 `http://localhost:5000` 启动。

#### 依赖要求
- Python 3.7+
- Git (必须安装并添加到PATH)
- Flask 2.3.3
- Flask-CORS 4.0.0

### 2. 安装Chrome插件

1. 打开Chrome浏览器
2. 进入 `chrome://extensions/`
3. 开启"开发者模式"
4. 点击"加载已解压的扩展程序"
5. 选择 `github-stats-extension` 文件夹

### 3. 配置服务器地址

1. 点击浏览器工具栏中的插件图标
2. 在弹出的设置页面中输入服务器地址（默认: `http://localhost:5000`）
3. 点击"保存"按钮
4. 可选：点击"测试连接"验证服务器是否正常运行

### 4. 使用插件

1. 访问任意GitHub仓库页面（如: `https://github.com/user/repo`）
2. 页面右侧将自动显示代码统计悬浮窗
3. 点击悬浮窗打开详细统计页面

## API接口

### 健康检查
```
GET /health
```

### 获取仓库统计
```
POST /api/stats
Content-Type: application/json

{
  "repoUrl": "https://github.com/user/repo",
  "owner": "user",
  "repo": "repo"
}
```

### 检查统计状态
```
GET /api/stats/status/{owner}/{repo}
```

### 统计详情页面
```
GET /stats?owner={owner}&repo={repo}
```

## 技术实现

### 前端插件
- **Manifest V3**: 使用最新的Chrome插件API
- **Content Script**: 检测GitHub页面并注入悬浮窗
- **Popup**: 提供服务器配置界面
- **Background Service Worker**: 处理插件生命周期

### 后端服务器
- **Flask**: 轻量级Web框架
- **Git Clone**: 使用浅克隆减少下载时间
- **异步处理**: 后台线程处理代码统计
- **缓存机制**: 30分钟缓存避免重复分析
- **自动清理**: 定期清理临时文件
- **文本文件识别**: 智能识别文本文件，自动过滤二进制文件

### 文本文件统计逻辑
- **智能文本识别**: 通过文件魔数、扩展名和内容分析自动判断文本文件
- **二进制文件过滤**: 自动过滤图片、视频、执行文件等二进制文件
- **依赖目录过滤**: 跳过node_modules、__pycache__等依赖目录
- **文件夹组织**: 按文件夹组织统计结果，计算占比

## 文本文件识别机制

### 支持的文本文件（不限于）
- **编程语言**: .py, .js, .ts, .java, .c, .cpp, .go, .rs, .php, .rb 等
- **Web技术**: .html, .css, .jsx, .tsx, .vue, .svelte 等  
- **配置文件**: .json, .yaml, .xml, .toml, .ini 等
- **文档文件**: .md, .txt, .rst, .tex 等
- **脚本文件**: .sh, .bash, .bat, .ps1 等
- **数据文件**: .csv, .sql, .log 等
- **无扩展名**: Dockerfile, Makefile, README 等

### 过滤的二进制文件
- **执行文件**: .exe, .dll, .so, .dylib 等
- **图片文件**: .jpg, .png, .gif, .bmp, .webp 等
- **音视频**: .mp3, .mp4, .avi, .mkv 等
- **文档文件**: .pdf, .doc, .docx, .xls, .xlsx 等
- **压缩文件**: .zip, .tar, .gz, .rar, .7z 等
- **编译产物**: .pyc, .class, .o, .obj 等

### 识别方法
1. **文件大小检查**: 跳过空文件和超过10MB的大文件
2. **扩展名快速过滤**: 快速排除已知二进制文件扩展名
3. **魔数检查**: 检查文件头部是否包含二进制文件的特征签名
4. **NULL字节检测**: 检查文件中NULL字节的比例（二进制文件的明显特征）
5. **控制字符分析**: 统计不可打印控制字符的比例
6. **多编码尝试**: 使用UTF-8、GBK、GB2312、Latin-1等编码尝试解码
7. **文本质量评估**: 检查解码后文本中可打印字符的比例（需≥85%）

## 注意事项

1. **Git依赖**: 服务器需要安装Git命令行工具
2. **网络要求**: 需要能够访问GitHub进行代码克隆
3. **存储空间**: 临时下载的仓库会占用磁盘空间（自动清理）
4. **隐私**: 代码统计在本地进行，不会上传到第三方服务器
5. **性能**: 大型仓库首次分析可能需要较长时间
6. **文件过滤**: 自动过滤二进制文件，只统计有意义的文本内容

## 故障排除

### 插件无法显示悬浮窗
- 检查是否在GitHub仓库页面
- 确认插件已正确安装并启用
- 检查控制台是否有JavaScript错误

### 服务器连接失败
- 确认Flask服务器正在运行
- 检查防火墙设置
- 验证服务器地址配置是否正确

### 统计失败
- 确认Git已安装并可用
- 检查网络连接
- 验证仓库是否为公开仓库
- 查看服务器日志了解具体错误

### 文本文件识别问题
- 如果某些文本文件被误判为二进制文件，可能是编码问题
- 超大10MB的大文件会被自动跳过
- 隐藏文件和特殊文件会被跳过

## 开发计划

- [ ] 支持私有仓库（需要身份验证）
- [ ] 添加更多代码质量指标
- [ ] 支持代码复杂度分析
- [ ] 提供导出功能（Excel/CSV）
- [ ] 添加历史统计趋势图
- [ ] 支持多语言界面
- [ ] 优化文本文件识别算法
- [ ] 支持自定义过滤规则

## 许可证

MIT License