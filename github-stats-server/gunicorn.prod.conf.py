#!/usr/bin/env python3

import os

# Server socket
bind = "0.0.0.0:5002"
backlog = 2048

# Worker processes
workers = 4
worker_class = "sync" 
worker_connections = 1000
timeout = 120
keepalive = 5

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
loglevel = 'info'
accesslog = '-'
errorlog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'github_stats'

# Server mechanics
daemon = False
pidfile = None
user = 1000
group = 1000
tmp_upload_dir = None

# SSL configuration - 只在证书文件存在时启用
cert_file = '/etc/ssl/certs/fullchain.pem'
key_file = '/etc/ssl/certs/privkey.pem'

if os.path.exists(cert_file) and os.path.exists(key_file):
    certfile = cert_file
    keyfile = key_file
    # SSL版本和安全设置
    ssl_version = 2  # TLSv1_2
    ciphers = 'ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS'
else:
    # 如果证书文件不存在，使用HTTP
    certfile = None
    keyfile = None