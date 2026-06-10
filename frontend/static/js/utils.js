/**
 * 工具函数模块
 * 提供通用的辅助函数，包括 HTML 转义、日期格式化等
 */

/**
 * 校验密码强度（需与后端 backend/auth.py::validate_password_strength 保持一致）
 * 要求：至少 8 位，包含大小写字母和数字
 * @param {string} password - 待校验的密码
 * @returns {string} - 错误信息；通过校验时返回空字符串
 */
export function validatePassword(password) {
  if (!password) return '密码不能为空';
  if (password.length < 8) return '密码至少需要 8 位';
  if (!/[a-z]/.test(password)) return '密码必须包含至少一个小写字母';
  if (!/[A-Z]/.test(password)) return '密码必须包含至少一个大写字母';
  if (!/[0-9]/.test(password)) return '密码必须包含至少一个数字';
  return '';
}

/**
 * HTML 转义函数 - 防止 XSS 攻击
 * @param {string} text - 需要转义的文本
 * @returns {string} - 转义后的安全文本
 */
export function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

/**
 * 格式化日期时间
 * @param {string|Date} date - 日期对象或字符串
 * @param {boolean} includeTime - 是否包含时间
 * @returns {string} - 格式化后的日期字符串
 */
export function formatDate(date, includeTime = true) {
  if (!date) return '';
  const d = new Date(date);
  if (isNaN(d.getTime())) return String(date);

  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');

  if (!includeTime) {
    return `${year}-${month}-${day}`;
  }

  const hour = String(d.getHours()).padStart(2, '0');
  const minute = String(d.getMinutes()).padStart(2, '0');
  const second = String(d.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

/**
 * 创建安全的 DOM 元素（避免 innerHTML）
 * @param {string} tag - 标签名
 * @param {Object} attrs - 属性对象
 * @param {string|Node|Array} children - 子元素（文本或 DOM 节点）
 * @returns {HTMLElement} - 创建的 DOM 元素
 */
export function createElement(tag, attrs = {}, children = null) {
  const el = document.createElement(tag);

  // 设置属性
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'className') {
      el.className = value;
    } else if (key === 'style' && typeof value === 'object') {
      Object.assign(el.style, value);
    } else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      el.setAttribute(key, value);
    }
  }

  // 添加子元素
  if (children != null) {
    if (Array.isArray(children)) {
      children.forEach(child => {
        if (typeof child === 'string') {
          el.appendChild(document.createTextNode(child));
        } else if (child instanceof Node) {
          el.appendChild(child);
        }
      });
    } else if (typeof children === 'string') {
      el.textContent = children;
    } else if (children instanceof Node) {
      el.appendChild(children);
    }
  }

  return el;
}

/**
 * 安全地设置元素的 HTML 内容（仅允许已知安全的标签）
 * @param {HTMLElement} element - 目标元素
 * @param {string} html - HTML 字符串
 * @param {Array<string>} allowedTags - 允许的标签列表
 */
export function setSafeHtml(element, html, allowedTags = ['b', 'i', 'u', 'br', 'span']) {
  // 简单的标签白名单实现（生产环境建议使用 DOMPurify 库）
  const div = document.createElement('div');
  div.innerHTML = html;

  // 递归清理不安全的标签
  const cleanNode = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.cloneNode();
    }
    if (node.nodeType === Node.ELEMENT_NODE) {
      const tagName = node.tagName.toLowerCase();
      if (!allowedTags.includes(tagName)) {
        // 不允许的标签，只保留其文本内容
        return document.createTextNode(node.textContent);
      }
      const cleaned = document.createElement(tagName);
      // 只复制 class 和 style 属性
      if (node.className) cleaned.className = node.className;
      Array.from(node.childNodes).forEach(child => {
        const cleanedChild = cleanNode(child);
        if (cleanedChild) cleaned.appendChild(cleanedChild);
      });
      return cleaned;
    }
    return null;
  };

  element.innerHTML = '';
  Array.from(div.childNodes).forEach(child => {
    const cleaned = cleanNode(child);
    if (cleaned) element.appendChild(cleaned);
  });
}

/**
 * 防抖函数
 * @param {Function} func - 需要防抖的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function} - 防抖后的函数
 */
export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * 节流函数
 * @param {Function} func - 需要节流的函数
 * @param {number} limit - 时间限制（毫秒）
 * @returns {Function} - 节流后的函数
 */
export function throttle(func, limit) {
  let inThrottle;
  return function executedFunction(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}
