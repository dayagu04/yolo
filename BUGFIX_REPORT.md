# Bug 修复报告

**修复日期**: 2026-06-10  
**修复人**: Claude AI Assistant  
**修复版本**: V2.0.1

## 修复的严重 Bug

### 1. SQL 注入风险修复 🔒

**文件**: `scripts/init_database.py`  
**位置**: 第 48 行  
**严重等级**: CRITICAL

**问题描述**:
```python
# 不安全的代码
result = conn.execute(
    text(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{db_name}'")
)
```
使用 f-string 拼接 SQL 查询，存在 SQL 注入风险。

**修复方案**:
```python
# 安全的代码
result = conn.execute(
    text("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = :db_name"),
    {"db_name": db_name}
)

# CREATE DATABASE 语句添加输入验证
if not db_name.replace("_", "").isalnum():
    raise ValueError(f"数据库名称包含非法字符: {db_name}")
conn.execute(text(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
```

**影响范围**: 数据库初始化脚本，低风险（仅管理员使用）

---

### 2. Redis KEYS 命令性能问题 ⚡

**文件**: `backend/redis_stats.py`  
**位置**: 第 114 行、第 235 行  
**严重等级**: CRITICAL（生产环境）

**问题描述**:
```python
# 阻塞式命令
keys = self.client.keys("stats:today:cam:*")
```
`KEYS` 命令会阻塞 Redis 服务器，在生产环境中可能导致性能问题。

**修复方案**:
```python
# 使用 SCAN 游标迭代
result = {}
cursor = 0
while True:
    cursor, keys = self.client.scan(cursor, match="stats:today:cam:*", count=100)
    for key in keys:
        camera_id = key.decode('utf-8').split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
        count = self.client.get(key)
        result[camera_id] = int(count) if count else 0
    if cursor == 0:
        break
```

**影响范围**: 所有使用 Redis 的场景，显著提升并发性能

---

### 3. 布尔值比较规范修复 📝

**文件**: `backend/database.py`  
**位置**: 第 524 行、第 598 行  
**严重等级**: MAJOR（代码规范）

**问题描述**:
```python
# 违反 PEP8 规范
.filter(AlertEscalation.notified == False)
.filter(CameraROI.enabled == True)
```

**修复方案**:
```python
# 符合 SQLAlchemy 最佳实践
.filter(AlertEscalation.notified.is_(False))
.filter(CameraROI.enabled.is_(True))
```

**影响范围**: 数据库查询逻辑，无功能影响

---

### 4. 共享内存资源泄漏修复 💾

**文件**: `backend/capture_process.py`  
**位置**: 第 64-66 行  
**严重等级**: MAJOR

**问题描述**:
```python
# 如果 close() 失败，unlink() 不会执行
if self._shm:
    self._shm.close()
    self._shm.unlink()
```

**修复方案**:
```python
if self._shm:
    try:
        self._shm.close()
    except Exception:
        pass  # 忽略 close 失败
    finally:
        try:
            self._shm.unlink()
        except Exception:
            pass  # 忽略 unlink 失败，可能已被清理
        finally:
            self._shm = None
```

**影响范围**: 多摄像头采集场景，避免内存泄漏

---

### 5. 时区感知修复 🌍

**文件**: `backend/database.py`  
**位置**: 第 304 行  
**严重等级**: MAJOR

**问题描述**:
```python
# 使用本地时区，可能导致夏令时问题
cutoff = datetime.now() - timedelta(days=days)
```

**修复方案**:
```python
# 使用 UTC 时区
cutoff = datetime.now(timezone.utc) - timedelta(days=days)
```

**影响范围**: 告警记录清理功能，避免时区混乱

---

## 待修复问题

### 高优先级（推荐近期修复）

#### 1. 前端 XSS 风险
**文件**: 多个前端 JS 文件  
**问题**: 使用 `innerHTML` 拼接用户输入  
**建议**: 使用 `textContent` 或 HTML 转义函数

#### 2. 密码复杂度验证不足
**文件**: `backend/routers/auth.py:139`  
**问题**: 仅检查长度（≥6 位），未验证复杂度  
**建议**: 添加大小写字母、数字、特殊字符要求

#### 3. WebSocket Token 安全
**文件**: `frontend/static/js/websocket.js`  
**问题**: Token 通过 URL 传递，可能被日志记录  
**建议**: 使用 Cookie + CSRF 保护或自定义握手协议

### 中优先级

#### 4. 异常处理过于宽泛
**文件**: 多处使用 `except Exception`  
**建议**: 具体化异常类型，避免隐藏真实错误

#### 5. 线程同步问题
**文件**: `backend/camera.py:278-280`  
**问题**: `last_frame_ts` 读取时未加锁  
**建议**: 所有共享状态访问都加锁，或使用原子操作

#### 6. 配置文件写入安全
**文件**: `backend/routers/camera.py:158`  
**问题**: 直接覆盖文件，失败时可能损坏配置  
**建议**: 使用临时文件 + 原子性替换

### 低优先级

#### 7. 导入顺序混乱
**建议**: 使用 `isort` 工具自动排序

#### 8. 缺少类型注解和文档字符串
**建议**: 为公共 API 添加完整文档

#### 9. 魔法数字硬编码
**建议**: 将常量提取到配置文件或常量定义

---

## 测试验证

### 已修复功能测试
1. **SQL 注入防护**:
   ```bash
   # 测试特殊字符输入
   YOLO_DATABASE_NAME="test'; DROP TABLE users; --" python scripts/init_database.py
   # 预期: ValueError 异常
   ```

2. **Redis SCAN 性能**:
   ```python
   # 性能对比测试
   # KEYS: O(N) 阻塞
   # SCAN: O(1) 每次迭代，不阻塞
   ```

3. **时区一致性**:
   ```python
   # 验证所有 datetime 对象都包含时区信息
   from backend.database import Alert
   alert = Alert.query.first()
   assert alert.timestamp.tzinfo is not None
   ```

### 需要人工验证的场景
- 多摄像头长时间运行，检查共享内存是否正常释放
- 并发 Redis 操作，验证 SCAN 游标正确性
- 跨时区服务器部署，验证时间戳一致性

---

## 部署建议

### 立即应用（生产环境）
- SQL 注入修复
- Redis KEYS → SCAN 替换
- 共享内存泄漏修复

### 下一版本（V2.1）
- 前端 XSS 防护
- 密码复杂度验证
- WebSocket 安全改进

### 长期改进（V3.0）
- 代码规范统一（类型注解、文档字符串）
- 性能优化（帧缓冲压缩、数据库索引）
- 测试覆盖提升（集成测试、压力测试）

---

## 回归测试清单

- [ ] 数据库初始化成功
- [ ] 用户登录/登出正常
- [ ] 摄像头采集无内存泄漏
- [ ] Redis 统计数据准确
- [ ] 告警记录清理正常
- [ ] ROI 区域检测功能正常
- [ ] API 接口响应时间无异常

---

**修复分支**: `bugfix/security-and-performance-2026-06-10`  
**建议合并到**: `main`  
**预计影响**: 提升系统安全性和稳定性，无功能变更
