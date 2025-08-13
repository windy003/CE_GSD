class GitHubStatsWidget {
  constructor() {
    this.serverUrl = null;
    this.currentRepo = null;
    this.widget = null;
    this.autoHideTimer = null;
    this.init();
  }

  async init() {
    await this.loadServerUrl();
    this.detectRepository();
    this.createWidget();
    this.setupMessageListener();
    
    // 监听URL变化
    this.observeUrlChanges();
  }

  async loadServerUrl() {
    return new Promise((resolve) => {
      chrome.storage.sync.get(['serverUrl'], (result) => {
        this.serverUrl = result.serverUrl || null;
        resolve();
      });
    });
  }

  detectRepository() {
    const pathParts = window.location.pathname.split('/').filter(part => part);
    console.log('GitHub Stats: Detecting repository...', { 
      hostname: window.location.hostname, 
      pathname: window.location.pathname,
      pathParts 
    });
    
    if (pathParts.length >= 2 && window.location.hostname === 'github.com') {
      const owner = pathParts[0];
      const repo = pathParts[1];
      
      // 确保是仓库页面，不是用户页面或其他页面
      const isValid = this.isValidRepoPage(pathParts);
      console.log('GitHub Stats: Page validation result:', { owner, repo, isValid, pathParts });
      
      if (!isValid) {
        this.currentRepo = null;
        return;
      }
      
      this.currentRepo = {
        owner,
        repo,
        fullName: `${owner}/${repo}`,
        url: `https://github.com/${owner}/${repo}`
      };
      
      console.log('GitHub Stats: Repository detected:', this.currentRepo);
    } else {
      this.currentRepo = null;
      console.log('GitHub Stats: Not a GitHub repository page');
    }
  }

  isValidRepoPage(pathParts) {
    // 排除用户页面、组织页面等
    const invalidPaths = ['settings', 'notifications', 'explore', 'marketplace'];
    
    if (invalidPaths.includes(pathParts[0])) {
      return false;
    }
    
    // 检查是否在仓库的子页面
    if (pathParts.length >= 2) {
      const validRepoPaths = ['tree', 'blob', 'commits', 'releases', 'issues', 'pull', 'actions', 'projects', 'wiki', 'security', 'insights', 'settings'];
      
      // 如果只有两个路径部分（owner/repo），肯定是仓库页面
      if (pathParts.length === 2) {
        return true;
      }
      
      // 如果有更多路径部分，检查第三个部分是否是有效的仓库子页面
      return validRepoPaths.includes(pathParts[2]) || pathParts.length === 2;
    }
    
    return false;
  }

  createWidget() {
    console.log('GitHub Stats: Creating widget...', { 
      currentRepo: this.currentRepo, 
      serverUrl: this.serverUrl 
    });
    
    // 移除已存在的widget
    if (this.widget) {
      this.widget.remove();
    }

    if (!this.currentRepo) {
      console.log('GitHub Stats: No repository detected, widget not created');
      return;
    }

    this.widget = document.createElement('div');
    this.widget.className = 'github-stats-float animate-in';
    
    this.updateWidgetContent('loading');
    document.body.appendChild(this.widget);
    
    console.log('GitHub Stats: Widget created and added to page');

    // 添加点击事件
    this.widget.addEventListener('click', () => this.openStatsPage());

    // 如果有服务器地址，开始获取统计数据
    if (this.serverUrl) {
      console.log('GitHub Stats: Starting to fetch stats...');
      this.fetchStats();
    } else {
      console.log('GitHub Stats: No server URL configured');
      this.updateWidgetContent('noServer');
    }
  }

  updateWidgetContent(state, data = null) {
    if (!this.widget) return;

    // 清除之前的自动隐藏定时器
    if (this.autoHideTimer) {
      clearTimeout(this.autoHideTimer);
      this.autoHideTimer = null;
    }

    const content = {
      loading: `
        <div class="title">
          <span class="icon"></span>
          代码统计
        </div>
        <div class="stats loading">正在统计中...</div>
        <div class="click-hint">点击查看详情</div>
      `,
      success: `
        <div class="title">
          <span class="icon"></span>
          代码统计
        </div>
        <div class="stats">
          <div class="lines-count">${data?.totalLines?.toLocaleString() || '0'}</div>
          <div>行代码</div>
        </div>
        <div class="click-hint">点击查看详情</div>
      `,
      error: `
        <div class="title">
          <span class="icon"></span>
          代码统计
        </div>
        <div class="stats error">
          ${data || '获取失败'}
        </div>
        <div class="click-hint">点击重试</div>
      `,
      noServer: `
        <div class="title">
          <span class="icon"></span>
          代码统计
        </div>
        <div class="stats error">请先配置服务器</div>
        <div class="click-hint">点击插件图标设置</div>
      `
    };

    this.widget.innerHTML = content[state] || content.error;

    // 如果是成功状态，设置5秒后自动隐藏
    if (state === 'success') {
      this.autoHideTimer = setTimeout(() => {
        this.hideWidget();
      }, 5000);
    }
  }

  hideWidget() {
    if (this.widget) {
      this.widget.classList.add('animate-out');
      setTimeout(() => {
        if (this.widget) {
          this.widget.remove();
          this.widget = null;
        }
      }, 300); // 等待动画完成
    }
    
    // 清除定时器
    if (this.autoHideTimer) {
      clearTimeout(this.autoHideTimer);
      this.autoHideTimer = null;
    }
  }

  async fetchStats() {
    if (!this.serverUrl || !this.currentRepo) {
      this.updateWidgetContent('noServer');
      return;
    }

    try {
      // 第一次请求
      const response = await fetch(`${this.serverUrl}/api/stats`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          repoUrl: this.currentRepo.url,
          owner: this.currentRepo.owner,
          repo: this.currentRepo.repo
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      
      // 检查是否正在处理中
      if (data.processing) {
        console.log('Data is processing, will poll for updates...');
        this.updateWidgetContent('loading');
        this.pollForStats();
      } else {
        this.updateWidgetContent('success', data);
      }
      
    } catch (error) {
      console.error('Failed to fetch stats:', error);
      this.updateWidgetContent('error', '连接服务器失败');
    }
  }

  async pollForStats() {
    if (!this.serverUrl || !this.currentRepo) {
      return;
    }

    const maxAttempts = 30; // 最多尝试30次 (约5分钟)
    let attempts = 0;

    const poll = async () => {
      attempts++;
      
      try {
        const response = await fetch(
          `${this.serverUrl}/api/stats/status/${this.currentRepo.owner}/${this.currentRepo.repo}`
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        
        if (data.ready) {
          console.log('Stats ready:', data);
          this.updateWidgetContent('success', data);
        } else if (attempts < maxAttempts) {
          // 继续轮询，间隔逐渐增加
          const delay = Math.min(2000 + attempts * 500, 10000); // 2-10秒间隔
          setTimeout(poll, delay);
        } else {
          // 超时
          this.updateWidgetContent('error', '统计超时，请稍后重试');
        }
        
      } catch (error) {
        console.error('Polling failed:', error);
        if (attempts < maxAttempts) {
          setTimeout(poll, 5000); // 5秒后重试
        } else {
          this.updateWidgetContent('error', '获取统计失败');
        }
      }
    };

    // 开始轮询
    setTimeout(poll, 2000); // 2秒后开始第一次轮询
  }

  openStatsPage() {
    if (!this.serverUrl) {
      // 如果没有配置服务器，提示用户配置
      alert('请先点击插件图标配置服务器地址');
      return;
    }

    if (!this.currentRepo) {
      return;
    }

    // 构建统计页面URL
    const statsUrl = `${this.serverUrl}/stats?owner=${this.currentRepo.owner}&repo=${this.currentRepo.repo}`;
    window.open(statsUrl, '_blank');
  }

  observeUrlChanges() {
    // 监听pushState和replaceState
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;

    history.pushState = function(...args) {
      originalPushState.apply(history, args);
      setTimeout(() => this.handleUrlChange(), 100);
    }.bind(this);

    history.replaceState = function(...args) {
      originalReplaceState.apply(history, args);
      setTimeout(() => this.handleUrlChange(), 100);
    }.bind(this);

    // 监听popstate事件
    window.addEventListener('popstate', () => {
      setTimeout(() => this.handleUrlChange(), 100);
    });

    // 监听DOM变化，GitHub使用AJAX加载
    const observer = new MutationObserver((mutations) => {
      let shouldCheck = false;
      mutations.forEach((mutation) => {
        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
          shouldCheck = true;
        }
      });
      
      if (shouldCheck) {
        setTimeout(() => this.handleUrlChange(), 500);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  handleUrlChange() {
    const prevRepo = this.currentRepo;
    this.detectRepository();
    
    // 如果仓库发生变化，重新创建widget
    if (!this.isSameRepo(prevRepo, this.currentRepo)) {
      this.createWidget();
    }
  }

  isSameRepo(repo1, repo2) {
    if (!repo1 && !repo2) return true;
    if (!repo1 || !repo2) return false;
    return repo1.fullName === repo2.fullName;
  }

  setupMessageListener() {
    // 监听来自popup的消息
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message.action === 'serverUpdated') {
        this.serverUrl = message.serverUrl;
        
        // 如果当前在仓库页面，重新获取统计数据
        if (this.currentRepo && this.widget) {
          this.updateWidgetContent('loading');
          this.fetchStats();
        }
      }
    });
  }
}

// 等待DOM加载完成后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    new GitHubStatsWidget();
  });
} else {
  new GitHubStatsWidget();
}