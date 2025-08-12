// Background service worker for GitHub Stats Extension

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    // 首次安装时设置默认服务器地址
    chrome.storage.sync.set({
      serverUrl: 'http://localhost:5000'
    });
    
    // 打开欢迎页面或设置页面
    chrome.tabs.create({
      url: chrome.runtime.getURL('popup.html')
    });
  }
});

// 处理来自content script的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getServerUrl') {
    chrome.storage.sync.get(['serverUrl'], (result) => {
      sendResponse({ serverUrl: result.serverUrl || null });
    });
    return true; // 保持消息通道开放
  }
});

// 监听存储变化
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'sync' && changes.serverUrl) {
    // 通知所有GitHub标签页服务器地址已更新
    chrome.tabs.query({ url: 'https://github.com/*/*' }, (tabs) => {
      tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, {
          action: 'serverUpdated',
          serverUrl: changes.serverUrl.newValue
        }).catch(() => {
          // 忽略错误，某些标签页可能还未加载content script
        });
      });
    });
  }
});