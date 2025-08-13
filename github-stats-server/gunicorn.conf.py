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

# Process naming
proc_name = 'github_stats'

# Server mechanics
daemon = False
pidfile = None
user = 1000
group = 1000
tmp_upload_dir = None

# SSL - 移除SSL配置，使用HTTP
# keyfile = None
# certfile = None