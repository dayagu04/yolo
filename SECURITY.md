# 安全规范与最佳实践

## 1. 认证与授权

### JWT 认证
- Access Token 有效期：60 分钟（可配置）
- Refresh Token 用于延长会话
- Token 存储：仅存于 `localStorage`，不使用 Cookie（避免 CSRF）
- WebSocket 认证：通过查询参数传递 token（注意：可能被日志记录，生产环境建议使用 Cookie + CSRF 保护或自定义握手）

### 登录保护
- 失败锁定：5 次失败后锁定账户 15 分钟
- 速率限制：API 请求频率限制（通过 `slowapi` 实现）
- 密码要求：
  - 最小长度：6 位（建议提升到 8 位）
  - **待改进**：当前未验证复杂度（数字、大小写、特殊字符）

## 2. 数据库安全

### SQL 注入防护
- ✅ 使用 SQLAlchemy ORM 参数化查询
- ✅ 已修复 `scripts/init_database.py` 中的 SQL 拼接问题
- ⚠️ 动态表名/列名场景需额外验证

### 数据库凭证
- 密码通过环境变量注入：`YOLO_DATABASE_PASSWORD`
- 配置文件 `config.yaml` 不存储明文密码
- 敏感配置使用 `config.secrets.yaml`（已添加到 `.gitignore`）

## 3. 前端安全

### XSS 防护
- ⚠️ **当前风险**：多处使用 `innerHTML` 拼接用户输入
- **建议修复方案**：
  ```javascript
  // 不安全：
  element.innerHTML = `<span>${userInput}</span>`;
  
  // 安全：
  function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
  }
  element.innerHTML = `<span>${escapeHtml(userInput)}</span>`;
  
  // 或更简洁：
  const span = document.createElement('span');
  span.textContent = userInput;
  element.appendChild(span);
  ```

### CSRF 防护
- 当前使用 JWT + CORS 配置
- WebSocket 场景：Token 通过 URL 传递（可能被日志记录）
- **建议**：敏感操作添加二次确认或使用 CSRF Token

## 4. 文件操作安全

### 上传文件验证
- 截图路径：通过配置文件指定 `alert.screenshot.save_dir`
- **当前限制**：
  - 仅保存系统生成的截图，不接受用户上传
  - 文件名使用 UUID 避免路径遍历

### 配置文件写入
- ✅ 已改进：使用临时文件 + 原子性替换（`os.replace`）
- 避免写入失败导致配置损坏

## 5. Redis 安全

### 命令安全
- ✅ 已修复：将 `KEYS` 命令替换为 `SCAN`（避免生产环境阻塞）
- Redis 密码：通过 `YOLO_REDIS_PASSWORD` 环境变量配置
- 网络隔离：默认绑定 `localhost`，生产环境建议使用 Docker 内部网络

## 6. 敏感信息管理

### 密钥存储
- ✅ JWT 密钥验证：启动时检查 `YOLO_AUTH_SECRET_KEY` 是否为默认值
- **建议改进**：添加密钥强度检查（最小熵要求）

### 日志脱敏
- ✅ 健康检查接口已脱敏数据库密码
- ⚠️ 其他日志点需人工审查，避免记录敏感信息

### 配置文件层级
```
config.yaml            # 基础配置，可提交到 Git
config.secrets.yaml    # 敏感配置（API Key、Webhook URL），已忽略
.env                   # 环境变量（密码、密钥），已忽略
```

## 7. 依赖安全

### 漏洞扫描
- CI 集成：`pip-audit` 检查依赖漏洞
- 定期更新：每季度审查 `requirements.txt`
- 版本锁定：使用精确版本号（如 `fastapi==0.115.6`）

### 第三方通知渠道
- 飞书/企微/钉钉 Webhook：需验证 URL 合法性
- **建议**：添加 URL 白名单机制，避免内网探测

## 8. 生产环境加固

### 部署清单
- [ ] 修改默认管理员密码
- [ ] 生成强随机 JWT 密钥（32 字节 hex）
- [ ] 配置 HTTPS（Nginx SSL 证书）
- [ ] 限制 MySQL/Redis 仅内网访问
- [ ] 启用防火墙，仅开放必要端口（80/443）
- [ ] 禁用 Swagger UI（`/docs` 和 `/redoc`）或添加认证
- [ ] 配置日志审计（审计日志保留 90 天）

### 运行时加固
```yaml
# docker-compose.yml 建议配置
services:
  backend:
    read_only: true  # 只读文件系统
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    security_opt:
      - no-new-privileges:true
```

## 9. 安全测试

### 渗透测试检查点
- [ ] SQL 注入（已修复，需验证）
- [ ] XSS（待修复前端 `innerHTML`）
- [ ] 未授权访问（测试各 API 端点）
- [ ] 暴力破解（登录锁定机制）
- [ ] 敏感信息泄露（错误消息、日志）
- [ ] SSRF（Webhook 通知）

### 自动化安全测试
```bash
# 依赖漏洞扫描
pip-audit

# 代码静态分析（可选）
bandit -r backend/

# API 安全测试（推荐工具）
# - OWASP ZAP
# - Burp Suite
```

## 10. 事件响应

### 安全事件类型
- 登录失败超限（已有日志）
- 数据库连接失败
- 异常 API 调用模式
- 未授权访问尝试

### 审计日志
- 表：`audit_logs`
- 记录内容：用户、操作、IP、时间戳
- 保留策略：默认永久，生产环境建议 90 天

### 应急响应
1. **账号泄露**：立即重置受影响用户密码，撤销所有 Token
2. **数据库入侵**：断开网络，备份当前状态，分析攻击路径
3. **依赖漏洞**：评估影响范围，更新依赖，重新部署

## 11. 已知问题与改进计划

### Critical（严重）
- ✅ 已修复：SQL 注入风险（`init_database.py`）
- ✅ 已修复：Redis KEYS 命令性能问题

### Major（重要）
- ⚠️ 待修复：前端 XSS 风险（`innerHTML` 使用）
- ⚠️ 待改进：密码复杂度验证不足
- ⚠️ 待改进：WebSocket Token 通过 URL 传递

### Minor（次要）
- ⚠️ 待改进：JWT 密钥强度检查
- ⚠️ 待改进：Webhook URL 白名单机制

## 12. 联系方式

如发现安全漏洞，请通过以下方式报告：
- 邮件：[security@example.com](mailto:security@example.com)（请配置实际邮箱）
- 私有安全通道：不公开披露漏洞细节
- 响应时间：7 个工作日内回复

---

**最后更新**：2026-06-10  
**责任人**：项目维护者
