#!/usr/bin/env python3
"""
GitHub Statistics Server
运行服务器的启动脚本
"""

import sys
import subprocess
import os

def install_requirements():
    """安装依赖包"""
    print("正在安装依赖包...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("依赖包安装完成!")
    except subprocess.CalledProcessError as e:
        print(f"安装依赖包失败: {e}")
        return False
    return True

def check_git():
    """检查Git是否可用"""
    try:
        subprocess.check_output(['git', '--version'], stderr=subprocess.STDOUT)
        print("Git检查通过")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到Git命令，请确保已安装Git并添加到PATH环境变量")
        return False

def main():
    print("=== GitHub统计服务器启动 ===")
    
    # 检查Git
    if not check_git():
        sys.exit(1)
    
    # 安装依赖
    if not install_requirements():
        sys.exit(1)
    
    print("\n服务器配置:")
    print("- 地址: http://localhost:5000")
    print("- 健康检查: http://localhost:5000/health")
    print("- 支持的代码文件类型: Python, JavaScript, TypeScript, Java, C/C++, Go, Rust等")
    print("\n正在启动服务器...")
    
    # 导入并运行Flask应用
    try:
        from app import app
        app.run(debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()