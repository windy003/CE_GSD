from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import subprocess
import os
import tempfile
import shutil
import time
from collections import defaultdict
import json
from pathlib import Path
import re

app = Flask(__name__)
CORS(app)

# 移除缓存机制，每次都重新统计

# 配置
TEMP_DIR = tempfile.gettempdir()
REPOS_DIR = os.path.join(TEMP_DIR, 'github_stats_repos')

# 二进制文件扩展名和魔数标识
BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.dylib', '.a', '.lib', '.obj', '.o',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.ico', '.webp',
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.mp4', '.avi', '.mkv', '.mov',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.bin', '.dat', '.db', '.sqlite', '.sqlite3',
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    '.pyc', '.pyo', '.class', '.jar', '.war'
}

# 常见的二进制文件魔数
BINARY_SIGNATURES = [
    b'\x89PNG',  # PNG
    b'\xff\xd8\xff',  # JPEG
    b'GIF8',  # GIF
    b'\x00\x00\x01\x00',  # ICO
    b'BM',  # BMP
    b'PK\x03\x04',  # ZIP
    b'\x1f\x8b',  # GZIP
    b'\x7fELF',  # ELF
    b'MZ',  # Windows executable
    b'\xca\xfe\xba\xbe',  # Java class
    b'%PDF',  # PDF
]

def ensure_repos_dir():
    """确保仓库目录存在"""
    if not os.path.exists(REPOS_DIR):
        os.makedirs(REPOS_DIR)

def clean_all_repos():
    """清理所有旧仓库，确保每次都是全新的clone"""
    if not os.path.exists(REPOS_DIR):
        return
    
    try:
        # 删除整个仓库目录
        shutil.rmtree(REPOS_DIR)
        print("Cleaned all old repos")
    except Exception as e:
        print(f"Failed to clean repos directory: {e}")

def clone_repository(repo_url, target_dir):
    """克隆仓库到指定目录"""
    try:
        # 使用浅克隆减少下载时间
        cmd = ['git', 'clone', '--depth', '1', repo_url, target_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            return True, "克隆成功"
        else:
            return False, f"克隆失败: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "克隆超时"
    except Exception as e:
        return False, f"克隆异常: {str(e)}"

def is_text_file(file_path):
    """
    使用多种方法智能判断文件是否为文本文件
    包括扩展名、魔数、字符编码等检测方法
    """
    try:
        print(f"[DEBUG] Checking file: {file_path}")
        # 快速检查：文件大小限制
        file_size = os.path.getsize(file_path)
        if file_size == 0:  # 空文件
            print(f"[DEBUG] {file_path}: Skipped - empty file")
            return False
        if file_size > 10 * 1024 * 1024:  # 超过10MB跳过
            print(f"[DEBUG] {file_path}: Skipped - too large ({file_size} bytes)")
            return False
            
        # 快速检查：扩展名黑名单
        _, ext = os.path.splitext(file_path)
        if ext.lower() in BINARY_EXTENSIONS:
            print(f"[DEBUG] {file_path}: Skipped - binary extension ({ext})")
            return False
        
        # 读取文件内容进行深度检测
        sample_size = min(8192, file_size)  # 读取8KB或整个文件
        with open(file_path, 'rb') as f:
            chunk = f.read(sample_size)
            
            # 1. 检查二进制文件魔数标识
            for signature in BINARY_SIGNATURES:
                if chunk.startswith(signature):
                    return False
            
            # 2. 检查NULL字节（二进制文件的明显特征）
            null_count = chunk.count(b'\x00')
            if null_count > 0:
                # 允许少量NULL字节（有些文本文件可能包含）
                null_ratio = null_count / len(chunk)
                if null_ratio > 0.01:  # 超过1%的NULL字节就认为是二进制
                    return False
            
            # 3. 检查不可打印控制字符（除了常见的换行符等）
            control_chars = 0
            printable_controls = {0x09, 0x0A, 0x0D}  # Tab, LF, CR
            for byte in chunk:
                if byte < 32 and byte not in printable_controls:
                    control_chars += 1
            
            if len(chunk) > 0 and control_chars / len(chunk) > 0.02:  # 超过2%控制字符
                return False
            
            # 4. 尝试使用常见编码解码文件
            text_encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']
            decoded_successfully = False
            
            for encoding in text_encodings:
                try:
                    decoded_text = chunk.decode(encoding)
                    
                    # 检查解码后的文本质量
                    if _is_reasonable_text(decoded_text):
                        decoded_successfully = True
                        break
                        
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            result = decoded_successfully
            print(f"[DEBUG] {file_path}: Final result = {result}")
            return result
            
    except Exception as e:
        print(f"[DEBUG] {file_path}: Exception occurred - {e}")
        return False

def _is_reasonable_text(text):
    """
    检查解码后的文本是否合理
    """
    if not text:
        return False
    
    # 检查文本中可打印字符的比例
    printable_chars = 0
    for char in text:
        # 字母、数字、标点、空格、换行符等
        if char.isprintable() or char in '\t\n\r\f\v':
            printable_chars += 1
    
    printable_ratio = printable_chars / len(text)
    
    # 要求至少85%的字符是可打印的
    return printable_ratio >= 0.85

def count_lines_in_file(file_path):
    """统计单个文件的行数"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return len(f.readlines())
    except:
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                return len(f.readlines())
        except:
            try:
                with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                    return len(f.readlines())
            except:
                return 0

def analyze_repository(repo_path):
    """分析仓库结构和代码行数"""
    stats = {
        'total_lines': 0,
        'total_files': 0,
        'file_stats': {},
        'folder_stats': {},
        'file_type_stats': defaultdict(int)
    }
    
    for root, dirs, files in os.walk(repo_path):
        # 跳过 .git 目录
        if '.git' in dirs:
            dirs.remove('.git')
        
        # 跳过常见的非代码目录
        dirs[:] = [d for d in dirs if not d.startswith('.') and 
                  d not in ['node_modules', '__pycache__', 'build', 'dist', 'target']]
        
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, repo_path).replace('\\', '/')
            
            # 跳过隐藏文件，但保留重要文件
            if file.startswith('.'):
                continue
            
            # 只统计文本文件
            if is_text_file(file_path):
                lines = count_lines_in_file(file_path)
                if lines > 0:  # 只统计非空文件
                    stats['total_lines'] += lines
                    stats['total_files'] += 1
                    
                    # 获取文件扩展名用于分类显示
                    _, ext = os.path.splitext(file)
                    file_type = ext if ext else '无扩展名'
                    
                    # 记录文件统计
                    stats['file_stats'][relative_path] = {
                        'lines': lines,
                        'file_type': file_type,
                        'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    }
                    
                    # 文件类型统计（用于显示分布）
                    stats['file_type_stats'][file_type] += lines
                    
                    # 文件夹统计 - 累加到所有父级文件夹
                    folder = os.path.dirname(relative_path) or '.'
                    
                    # 创建所有父级文件夹的路径列表
                    folder_paths = []
                    current_path = folder
                    while current_path and current_path != '.':
                        folder_paths.append(current_path)
                        parent = os.path.dirname(current_path)
                        if parent == current_path:  # 到达根目录
                            break
                        current_path = parent
                    
                    # 添加根目录
                    folder_paths.append('.')
                    
                    # 将文件统计累加到所有父级文件夹
                    for folder_path in folder_paths:
                        if folder_path not in stats['folder_stats']:
                            stats['folder_stats'][folder_path] = {'lines': 0, 'files': 0}
                        stats['folder_stats'][folder_path]['lines'] += lines
                        stats['folder_stats'][folder_path]['files'] += 1
    
    # 计算百分比
    if stats['total_lines'] > 0:
        for file_path, file_info in stats['file_stats'].items():
            file_info['percentage'] = (file_info['lines'] / stats['total_lines']) * 100
        
        for folder_path, folder_info in stats['folder_stats'].items():
            folder_info['percentage'] = (folder_info['lines'] / stats['total_lines']) * 100
    
    return stats

@app.route('/health')
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'ok', 'message': 'GitHub Stats Server is running'})

@app.route('/test.html')
def test_page():
    """测试页面"""
    import os
    with open(os.path.join(os.path.dirname(__file__), 'test.html'), 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/stats', methods=['POST'])
def get_repository_stats():
    """获取仓库统计信息 - 每次都重新统计"""
    data = request.get_json()
    if not data or 'repoUrl' not in data:
        return jsonify({'error': '缺少仓库URL'}), 400
    
    repo_url = data['repoUrl']
    owner = data.get('owner', '')
    repo = data.get('repo', '')
    
    if not owner or not repo:
        return jsonify({'error': '缺少仓库信息'}), 400
    
    try:
        # 每次都清理所有旧仓库
        clean_all_repos()
        ensure_repos_dir()
        
        # 创建临时目录
        repo_dir = os.path.join(REPOS_DIR, f"{owner}_{repo}_{int(time.time())}")
        
        # 克隆仓库
        success, message = clone_repository(repo_url, repo_dir)
        if not success:
            return jsonify({'error': f'克隆失败: {message}'}), 500
        
        # 分析代码
        stats = analyze_repository(repo_dir)
        
        # 立即清理临时文件
        if os.path.exists(repo_dir):
            try:
                shutil.rmtree(repo_dir)
            except:
                pass
        
        # 返回统计结果
        return jsonify({
            'totalLines': stats['total_lines'],
            'totalFiles': stats['total_files'],
            'processing': False,
            'cached': False
        })
        
    except Exception as e:
        return jsonify({'error': f'统计失败: {str(e)}'}), 500

@app.route('/api/stats/status/<owner>/<repo>')
def get_stats_status(owner, repo):
    """检查统计状态 - 不再使用缓存"""
    return jsonify({'ready': False, 'message': '请直接调用 /api/stats 接口获取最新统计'})

@app.route('/stats')
def stats_page():
    """统计详情页面 - 实时重新统计"""
    owner = request.args.get('owner')
    repo = request.args.get('repo')
    repo_url = request.args.get('repo_url')
    
    if not owner or not repo:
        return "缺少仓库参数", 400
    
    if not repo_url:
        repo_url = f"https://github.com/{owner}/{repo}.git"
    
    try:
        # 每次都重新统计
        clean_all_repos()
        ensure_repos_dir()
        
        # 创建临时目录
        repo_dir = os.path.join(REPOS_DIR, f"{owner}_{repo}_{int(time.time())}")
        
        # 克隆仓库
        success, message = clone_repository(repo_url, repo_dir)
        if not success:
            return render_template_string(ERROR_TEMPLATE, 
                                        owner=owner, repo=repo, error=message)
        
        # 分析代码
        stats = analyze_repository(repo_dir)
        
        # 立即清理临时文件
        if os.path.exists(repo_dir):
            try:
                shutil.rmtree(repo_dir)
            except:
                pass
        
        # 将stats转换为Base64编码的JSON，避免转义问题
        import json
        import base64
        stats_json = json.dumps(stats, ensure_ascii=True, separators=(',', ':'))
        stats_b64 = base64.b64encode(stats_json.encode('utf-8')).decode('ascii')
        
        return render_template_string(STATS_TEMPLATE, 
                                    owner=owner, repo=repo, stats=stats, stats_b64=stats_b64)
                                    
    except Exception as e:
        return render_template_string(ERROR_TEMPLATE, 
                                    owner=owner, repo=repo, error=str(e))

# HTML模板
LOADING_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ owner }}/{{ repo }} - 代码统计</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; margin: 40px; background: #f6f8fa; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 40px; }
        .loading { text-align: center; padding: 60px; color: #666; }
        .spinner { display: inline-block; width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #0969da; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 20px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    <script>
        setTimeout(() => { location.reload(); }, 5000);
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ owner }}/{{ repo }}</h1>
            <p>代码统计分析</p>
        </div>
        <div class="loading">
            <div class="spinner"></div>
            <p>正在分析仓库代码，请稍候...</p>
            <p>页面将自动刷新</p>
        </div>
    </div>
</body>
</html>
'''

ERROR_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ owner }}/{{ repo }} - 统计失败</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; margin: 40px; background: #f6f8fa; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .error { text-align: center; padding: 60px; color: #d73a49; }
    </style>
</head>
<body>
    <div class="container">
        <div class="error">
            <h1>统计失败</h1>
            <p>{{ error }}</p>
            <button onclick="location.reload()">重试</button>
        </div>
    </div>
</body>
</html>
'''

STATS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ owner }}/{{ repo }} - 代码统计</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; margin: 0; background: #f6f8fa; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .header h1 { margin: 0 0 10px 0; color: #24292f; }
        .header .subtitle { color: #656d76; margin: 0; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }
        .stat-card .number { font-size: 36px; font-weight: bold; color: #0969da; margin-bottom: 5px; }
        .stat-card .label { color: #656d76; font-size: 14px; }
        .section { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; overflow: hidden; }
        .section-header { padding: 20px; border-bottom: 1px solid #e1e4e8; background: #f6f8fa; }
        .section-header h2 { margin: 0; color: #24292f; font-size: 18px; }
        .section-content { padding: 0; }
        .folder-item, .file-item { padding: 15px 20px; border-bottom: 1px solid #e1e4e8; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: background 0.2s; }
        .folder-item:hover, .file-item:hover { background: #f6f8fa; }
        .folder-item:last-child, .file-item:last-child { border-bottom: none; }
        .item-name { flex-grow: 1; display: flex; align-items: center; gap: 8px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }
        .item-stats { display: flex; gap: 20px; align-items: center; font-size: 14px; }
        .lines-count { font-weight: 600; color: #0969da; }
        .percentage { color: #656d76; }
        .folder-icon, .file-icon { width: 16px; height: 16px; }
        .folder-icon::before { content: "📁"; }
        .file-icon::before { content: "📄"; }
        .breadcrumb { padding: 15px 20px; background: #f6f8fa; border-bottom: 1px solid #e1e4e8; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }
        .breadcrumb a { color: #0969da; text-decoration: none; cursor: pointer; }
        .breadcrumb a:hover { text-decoration: underline; }
        .breadcrumb span { color: #656d76; margin: 0 5px; }
        .file-list { min-height: 400px; }
        .back-button { padding: 15px 20px; border-bottom: 1px solid #e1e4e8; background: #f6f8fa; cursor: pointer; transition: background 0.2s; }
        .back-button:hover { background: #e1e4e8; }
        .back-button .item-name { color: #0969da; font-weight: 500; }
        .progress-bar { width: 100px; height: 6px; background: #e1e4e8; border-radius: 3px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #0969da, #54aeff); border-radius: 3px; transition: width 0.3s; }
        .language-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; padding: 20px; }
        .language-item { display: flex; justify-content: space-between; align-items: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ owner }}/{{ repo }}</h1>
            <p class="subtitle">代码统计分析结果</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{{ "{:,}".format(stats.total_lines) }}</div>
                <div class="label">总代码行数</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ "{:,}".format(stats.total_files) }}</div>
                <div class="label">代码文件数</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.file_type_stats|length }}</div>
                <div class="label">文件类型</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.folder_stats|length }}</div>
                <div class="label">目录数量</div>
            </div>
        </div>

        {% if stats.file_type_stats %}
        <div class="section">
            <div class="section-header">
                <h2>文件类型分布</h2>
            </div>
            <div class="language-stats">
                {% for file_type, lines in stats.file_type_stats.items() %}
                <div class="language-item">
                    <span>{{ file_type }}</span>
                    <span class="lines-count">{{ "{:,}".format(lines) }} 行</span>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        <div class="section">
            <div class="section-header">
                <h2>文件浏览器</h2>
            </div>
            <div class="section-content">
                <div class="breadcrumb" id="breadcrumb">
                    <a onclick="navigateToFolder('')">根目录</a>
                </div>
                <div class="file-list" id="fileList">
                    <!-- 文件列表将通过JavaScript动态生成 -->
                </div>
            </div>
        </div>
    </div>
    
    <!-- 数据传递 - 使用Base64编码避免转义问题 -->
    <script type="text/plain" id="stats-data">{{ stats_b64 }}</script>

    <script>
        // 全局变量
        let currentFolder = '';
        let fileData = {};
        let folderData = {};
        
        // 初始化数据 - 从Base64解码
        let stats;
        try {
            const statsElement = document.getElementById('stats-data');
            if (!statsElement) {
                throw new Error('找不到stats-data元素');
            }
            const statsB64 = statsElement.textContent.trim();
            if (!statsB64) {
                throw new Error('stats-data为空');
            }
            // Base64解码
            const statsJson = atob(statsB64);
            stats = JSON.parse(statsJson);
            console.log('Base64数据解析成功:', stats);
        } catch (error) {
            console.error('数据解析失败:', error);
            // 设置默认空数据
            stats = { file_stats: {}, folder_stats: {}, file_type_stats: {} };
        }
        
        // 组织文件和文件夹数据
        function initializeData() {
            console.log('初始化数据', stats);
            
            // 处理文件数据
            for (const [filePath, fileInfo] of Object.entries(stats.file_stats || {})) {
                const pathParts = filePath.split('/');
                const fileName = pathParts[pathParts.length - 1];
                const dirPath = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : '';
                
                if (!fileData[dirPath]) {
                    fileData[dirPath] = [];
                }
                
                fileData[dirPath].push({
                    name: fileName,
                    path: filePath,
                    lines: fileInfo.lines,
                    percentage: fileInfo.percentage,
                    type: 'file'
                });
            }
            
            // 处理文件夹数据 - 创建层级结构
            const allFolders = new Set();
            
            // 先收集所有可能的文件夹路径
            for (const [filePath, fileInfo] of Object.entries(stats.file_stats || {})) {
                const pathParts = filePath.split('/');
                if (pathParts.length > 1) {
                    // 为文件路径创建所有父级目录
                    for (let i = 1; i < pathParts.length; i++) {
                        const folderPath = pathParts.slice(0, i).join('/');
                        allFolders.add(folderPath);
                    }
                }
            }
            
            // 处理已有的文件夹统计数据
            for (const [folderPath, folderInfo] of Object.entries(stats.folder_stats || {})) {
                if (folderPath === '.') {
                    // 处理根目录的文件
                    continue;
                }
                allFolders.add(folderPath);
            }
            
            // 为每个文件夹创建条目
            for (const folderPath of allFolders) {
                const pathParts = folderPath.split('/');
                const folderName = pathParts[pathParts.length - 1];
                const parentPath = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : '';
                
                if (!folderData[parentPath]) {
                    folderData[parentPath] = [];
                }
                
                // 使用统计数据或默认值
                const folderInfo = stats.folder_stats[folderPath] || { lines: 0, files: 0, percentage: 0 };
                
                folderData[parentPath].push({
                    name: folderName,
                    path: folderPath,
                    lines: folderInfo.lines || 0,
                    percentage: folderInfo.percentage || 0,
                    files: folderInfo.files || 0,
                    type: 'folder'
                });
            }
            
            // 对所有数据按名称排序，文件夹在前
            for (const path in folderData) {
                folderData[path].sort((a, b) => a.name.localeCompare(b.name));
            }
            for (const path in fileData) {
                fileData[path].sort((a, b) => a.name.localeCompare(b.name));
            }
            
            console.log('文件数据:', fileData);
            console.log('文件夹数据:', folderData);
        }
        
        // 导航到指定文件夹
        function navigateToFolder(folderPath) {
            currentFolder = folderPath;
            updateBreadcrumb();
            renderFileList();
        }
        
        // 更新面包屑导航
        function updateBreadcrumb() {
            const breadcrumb = document.getElementById('breadcrumb');
            let html = '<a onclick="navigateToFolder(\\'\\')">根目录</a>';
            
            if (currentFolder) {
                const pathParts = currentFolder.split('/');
                let currentPath = '';
                
                for (let i = 0; i < pathParts.length; i++) {
                    currentPath += (i > 0 ? '/' : '') + pathParts[i];
                    html += ' <span>/</span> ';
                    html += '<a onclick="navigateToFolder(\\'' + currentPath + '\\')">' + pathParts[i] + '</a>';
                }
            }
            
            breadcrumb.innerHTML = html;
        }
        
        // 渲染文件列表
        function renderFileList() {
            const fileList = document.getElementById('fileList');
            let html = '';
            
            // 添加返回上级目录按钮（如果不在根目录）
            if (currentFolder) {
                const parentFolder = currentFolder.includes('/') 
                    ? currentFolder.substring(0, currentFolder.lastIndexOf('/'))
                    : '';
                    
                html += '<div class="back-button" onclick="navigateToFolder(\\'' + parentFolder + '\\')"><div class="item-name"><span>🔙</span><span>返回上级目录</span></div></div>';
            }
            
            // 显示当前目录下的文件夹
            const currentFolders = folderData[currentFolder] || [];
            for (const folder of currentFolders) {
                html += '<div class="folder-item" onclick="navigateToFolder(\\'' + folder.path + '\\')"><div class="item-name"><span class="folder-icon"></span><span>' + folder.name + '</span></div><div class="item-stats"><span class="lines-count">' + folder.lines.toLocaleString() + ' 行</span><span class="percentage">' + folder.percentage.toFixed(1) + '%</span><div class="progress-bar"><div class="progress-fill" style="width: ' + folder.percentage + '%"></div></div></div></div>';
            }
            
            // 显示当前目录下的文件
            const currentFiles = fileData[currentFolder] || [];
            for (const file of currentFiles) {
                html += '<div class="file-item"><div class="item-name"><span class="file-icon"></span><span>' + file.name + '</span></div><div class="item-stats"><span class="lines-count">' + file.lines.toLocaleString() + ' 行</span><span class="percentage">' + file.percentage.toFixed(1) + '%</span><div class="progress-bar"><div class="progress-fill" style="width: ' + file.percentage + '%"></div></div></div></div>';
            }
            
            // 如果目录为空
            if (currentFolders.length === 0 && currentFiles.length === 0) {
                html += '<div class="file-item"><div class="item-name" style="color: #656d76; font-style: italic;"><span>📭</span><span>此目录为空</span></div></div>';
            }
            
            fileList.innerHTML = html;
        }
        
        // 页面加载完成后初始化
        function initializePage() {
            console.log('开始初始化页面...');
            try {
                initializeData();
                navigateToFolder('');
                console.log('页面初始化完成');
            } catch (error) {
                console.error('初始化出错:', error);
            }
        }
        
        // 确保在页面加载完成后执行
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializePage);
        } else {
            // DOM已经加载完成，立即执行
            initializePage();
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("GitHub Stats Server starting...")
    print("Server will run on http://localhost:5001")
    print("Health check: http://localhost:5001/health")
    app.run(debug=True, host='0.0.0.0', port=5001)