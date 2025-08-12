document.addEventListener('DOMContentLoaded', function() {
  const serverUrlInput = document.getElementById('serverUrl');
  const saveBtn = document.getElementById('saveBtn');
  const testBtn = document.getElementById('testBtn');
  const statusDiv = document.getElementById('status');
  const currentServerDiv = document.getElementById('currentServer');

  // 加载已保存的服务器地址
  loadSavedServer();

  saveBtn.addEventListener('click', saveServerUrl);
  testBtn.addEventListener('click', testConnection);
  serverUrlInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      saveServerUrl();
    }
  });

  function loadSavedServer() {
    chrome.storage.sync.get(['serverUrl'], function(result) {
      if (result.serverUrl) {
        serverUrlInput.value = result.serverUrl;
        currentServerDiv.textContent = result.serverUrl;
      } else {
        currentServerDiv.textContent = '未设置';
        serverUrlInput.value = 'http://localhost:5000';
      }
    });
  }

  function saveServerUrl() {
    const url = serverUrlInput.value.trim();
    
    if (!url) {
      showStatus('请输入服务器地址', 'error');
      return;
    }

    // 验证URL格式
    try {
      new URL(url);
    } catch {
      showStatus('请输入有效的URL地址', 'error');
      return;
    }

    // 确保URL以斜杠结尾
    const normalizedUrl = url.endsWith('/') ? url.slice(0, -1) : url;

    chrome.storage.sync.set({ serverUrl: normalizedUrl }, function() {
      currentServerDiv.textContent = normalizedUrl;
      showStatus('服务器地址已保存', 'success');
      
      // 通知内容脚本服务器地址已更新
      chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
        if (tabs[0] && tabs[0].url.includes('github.com')) {
          chrome.tabs.sendMessage(tabs[0].id, {
            action: 'serverUpdated',
            serverUrl: normalizedUrl
          }).catch(() => {
            // 忽略错误，内容脚本可能还未加载
          });
        }
      });
    });
  }

  function testConnection() {
    const url = serverUrlInput.value.trim();
    
    if (!url) {
      showStatus('请先输入服务器地址', 'error');
      return;
    }

    testBtn.disabled = true;
    testBtn.textContent = '测试中...';
    showStatus('正在测试连接...', 'success');

    // 测试服务器连接
    fetch(`${url}/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    .then(response => {
      if (response.ok) {
        return response.json();
      }
      throw new Error(`HTTP ${response.status}`);
    })
    .then(data => {
      showStatus('连接成功！服务器正常运行', 'success');
    })
    .catch(error => {
      showStatus(`连接失败: ${error.message}`, 'error');
    })
    .finally(() => {
      testBtn.disabled = false;
      testBtn.textContent = '测试连接';
    });
  }

  function showStatus(message, type) {
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.style.display = 'block';
    
    setTimeout(() => {
      statusDiv.style.display = 'none';
    }, 3000);
  }
});