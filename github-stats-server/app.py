from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import subprocess
import os
import tempfile
import shutil
import threading
import time
from collections import defaultdict
import json
from pathlib import Path
import re

app = Flask(__name__)
CORS(app)

# 存储统计数据的缓存
stats_cache = {}
cache_lock = threading.Lock()

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

def clean_old_repos():
    """清理超过1小时的旧仓库"""
    if not os.path.exists(REPOS_DIR):
        return
    
    current_time = time.time()
    for item in os.listdir(REPOS_DIR):
        item_path = os.path.join(REPOS_DIR, item)
        if os.path.isdir(item_path):
            # 检查目录创建时间
            if current_time - os.path.getctime(item_path) > 3600:  # 1小时
                try:
                    shutil.rmtree(item_path)
                    print(f"Cleaned old repo: {item}")
                except Exception as e:
                    print(f"Failed to clean {item}: {e}")

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
            relative_path = os.path.relpath(file_path, repo_path)
            
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
                    
                    # 文件夹统计
                    folder = os.path.dirname(relative_path) or '.'
                    if folder not in stats['folder_stats']:
                        stats['folder_stats'][folder] = {'lines': 0, 'files': 0}
                    stats['folder_stats'][folder]['lines'] += lines
                    stats['folder_stats'][folder]['files'] += 1
    
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

@app.route('/api/stats', methods=['POST'])
def get_repository_stats():
    """获取仓库统计信息"""
    data = request.get_json()
    if not data or 'repoUrl' not in data:
        return jsonify({'error': '缺少仓库URL'}), 400
    
    repo_url = data['repoUrl']
    owner = data.get('owner', '')
    repo = data.get('repo', '')
    
    if not owner or not repo:
        return jsonify({'error': '缺少仓库信息'}), 400
    
    cache_key = f"{owner}/{repo}"
    
    # 检查缓存
    with cache_lock:
        if cache_key in stats_cache:
            cache_data = stats_cache[cache_key]
            # 如果缓存时间少于30分钟，直接返回
            if time.time() - cache_data['timestamp'] < 1800:
                return jsonify({
                    'totalLines': cache_data['stats']['total_lines'],
                    'totalFiles': cache_data['stats']['total_files'],
                    'cached': True
                })
    
    # 异步处理统计
    def process_stats():
        ensure_repos_dir()
        clean_old_repos()
        
        # 创建临时目录
        repo_dir = os.path.join(REPOS_DIR, f"{owner}_{repo}_{int(time.time())}")
        
        try:
            # 克隆仓库
            success, message = clone_repository(repo_url, repo_dir)
            if not success:
                with cache_lock:
                    stats_cache[cache_key] = {
                        'stats': {'error': message},
                        'timestamp': time.time()
                    }
                return
            
            # 分析代码
            stats = analyze_repository(repo_dir)
            
            # 缓存结果
            with cache_lock:
                stats_cache[cache_key] = {
                    'stats': stats,
                    'timestamp': time.time()
                }
            
        except Exception as e:
            with cache_lock:
                stats_cache[cache_key] = {
                    'stats': {'error': str(e)},
                    'timestamp': time.time()
                }
        finally:
            # 清理临时文件
            if os.path.exists(repo_dir):
                try:
                    shutil.rmtree(repo_dir)
                except:
                    pass
    
    # 启动后台线程处理
    thread = threading.Thread(target=process_stats)
    thread.daemon = True
    thread.start()
    
    # 立即返回处理中状态
    return jsonify({
        'totalLines': 0,
        'totalFiles': 0,
        'processing': True,
        'message': '正在分析仓库，请稍候...'
    })

@app.route('/api/stats/status/<owner>/<repo>')
def get_stats_status(owner, repo):
    """检查统计状态"""
    cache_key = f"{owner}/{repo}"
    
    with cache_lock:
        if cache_key in stats_cache:
            cache_data = stats_cache[cache_key]
            stats = cache_data['stats']
            
            if 'error' in stats:
                return jsonify({'error': stats['error']}), 500
            
            return jsonify({
                'totalLines': stats['total_lines'],
                'totalFiles': stats['total_files'],
                'ready': True
            })
    
    return jsonify({'ready': False, 'message': '统计正在进行中...'})

@app.route('/stats')
def stats_page():
    """统计详情页面"""
    owner = request.args.get('owner')
    repo = request.args.get('repo')
    
    if not owner or not repo:
        return "缺少仓库参数", 400
    
    cache_key = f"{owner}/{repo}"
    
    with cache_lock:
        if cache_key not in stats_cache:
            return render_template_string(LOADING_TEMPLATE, owner=owner, repo=repo)
        
        cache_data = stats_cache[cache_key]
        stats = cache_data['stats']
        
        if 'error' in stats:
            return render_template_string(ERROR_TEMPLATE, 
                                        owner=owner, repo=repo, error=stats['error'])
    
    return render_template_string(STATS_TEMPLATE, 
                                owner=owner, repo=repo, stats=stats)

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
        .collapsible-content { display: none; background: #f8f9fa; }
        .collapsible-content.show { display: block; }
        .nested-item { padding-left: 40px; }
        .toggle-icon { transition: transform 0.2s; }
        .toggle-icon.rotated { transform: rotate(90deg); }
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
                <h2>文件夹统计</h2>
            </div>
            <div class="section-content">
                {% for folder, info in stats.folder_stats.items() %}
                <div class="folder-item" onclick="toggleFolder('folder-{{ loop.index }}')">
                    <div class="item-name">
                        <span class="toggle-icon" id="toggle-folder-{{ loop.index }}">▶</span>
                        <span class="folder-icon"></span>
                        <span>{{ folder }}</span>
                    </div>
                    <div class="item-stats">
                        <span class="lines-count">{{ "{:,}".format(info.lines) }} 行</span>
                        <span class="percentage">{{ "%.1f"|format(info.percentage) }}%</span>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {{ info.percentage }}%"></div>
                        </div>
                    </div>
                </div>
                <div class="collapsible-content" id="folder-{{ loop.index }}">
                    {% for file_path, file_info in stats.file_stats.items() %}
                        {% if file_path.startswith(folder + '/') or (folder == '.' and '/' not in file_path) %}
                        <div class="file-item nested-item">
                            <div class="item-name">
                                <span class="file-icon"></span>
                                <span>{{ file_path.split('/')[-1] }}</span>
                            </div>
                            <div class="item-stats">
                                <span class="lines-count">{{ "{:,}".format(file_info.lines) }} 行</span>
                                <span class="percentage">{{ "%.1f"|format(file_info.percentage) }}%</span>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: {{ file_info.percentage }}%"></div>
                                </div>
                            </div>
                        </div>
                        {% endif %}
                    {% endfor %}
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <script>
        function toggleFolder(folderId) {
            const content = document.getElementById(folderId);
            const toggle = document.getElementById('toggle-' + folderId);
            
            if (content.classList.contains('show')) {
                content.classList.remove('show');
                toggle.classList.remove('rotated');
            } else {
                content.classList.add('show');
                toggle.classList.add('rotated');
            }
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("GitHub Stats Server starting...")
    print("Server will run on http://localhost:5000")
    print("Health check: http://localhost:5000/health")
    app.run(debug=True, host='0.0.0.0', port=5000)