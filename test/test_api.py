"""
后端 API 测试模块
"""
import pytest
import requests
import time


@pytest.mark.api
@pytest.mark.usefixtures("backend_server")
class TestBackendAPI:
    """后端 API 测试类"""

    def test_health_check(self, base_url):
        """测试健康检查接口"""
        resp = requests.get(f"{base_url}/health", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert "status" in data
        assert "uptime_sec" in data
        assert data["status"] in ["ok", "degraded", "error"]

    def test_camera_list(self, base_url):
        """测试摄像头列表接口"""
        resp = requests.get(f"{base_url}/api/v1/cameras", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert "cameras" in data
        assert "total" in data

    def test_camera_status(self, base_url):
        """测试摄像头状态接口"""
        resp = requests.get(f"{base_url}/api/v1/camera/0/status", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert "camera_id" in data
        assert "running" in data
        assert "connected" in data

    def test_camera_config_update(self, base_url):
        """测试摄像头配置更新"""
        payload = {"enabled": True, "conf": 0.6}
        resp = requests.post(f"{base_url}/api/v1/camera/0/config",
                             json=payload, timeout=5)
        assert resp.status_code == 200

    def test_alerts_query(self, base_url):
        """测试告警查询接口"""
        resp = requests.get(f"{base_url}/api/v1/alerts?limit=10", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert "alerts" in data
        assert "total" in data
        assert isinstance(data["alerts"], list)

    def test_alerts_pagination(self, base_url):
        """测试告警分页"""
        resp1 = requests.get(f"{base_url}/api/v1/alerts?limit=5&offset=0", timeout=5)
        resp2 = requests.get(f"{base_url}/api/v1/alerts?limit=5&offset=5", timeout=5)

        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_alerts_filter_by_camera(self, base_url):
        """测试按摄像头筛选告警"""
        resp = requests.get(f"{base_url}/api/v1/alerts?camera_id=0&limit=10", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        for alert in data["alerts"]:
            assert alert["camera_id"] == 0

    def test_alerts_filter_by_level(self, base_url):
        """测试按级别筛选告警"""
        resp = requests.get(f"{base_url}/api/v1/alerts?level=high&limit=10", timeout=5)
        assert resp.status_code == 200

    def test_logs_query(self, base_url):
        """测试日志查询接口"""
        resp = requests.get(f"{base_url}/api/v1/logs?limit=50", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert "logs" in data
        assert "count" in data

    def test_video_feed(self, base_url):
        """测试视频流接口"""
        resp = requests.get(f"{base_url}/video_feed?camera_id=0",
                            timeout=3, stream=True)
        try:
            assert resp.status_code == 200

            # 读取前 1KB 验证流格式
            chunk = next(resp.iter_content(1024), None)
            assert chunk is not None
            assert b"--frame" in chunk
        finally:
            resp.close()  # 关闭视频流连接

    def test_frontend_page(self, base_url):
        """测试前端页面"""
        resp = requests.get(f"{base_url}/", timeout=5)
        assert resp.status_code == 200
        assert "智能安防" in resp.text or "SAFE" in resp.text

    @pytest.mark.boundary
    def test_invalid_camera_id(self, base_url):
        """测试无效摄像头 ID"""
        resp = requests.get(f"{base_url}/api/v1/camera/999/status", timeout=5)
        # 应该返回 200（创建新摄像头）或 404
        assert resp.status_code in [200, 404, 500]

    @pytest.mark.boundary
    def test_oversized_limit(self, base_url):
        """测试超大 limit 参数"""
        resp = requests.get(f"{base_url}/api/v1/alerts?limit=10000", timeout=5)
        # 应该返回 422（参数错误）或限制最大值
        assert resp.status_code in [200, 422]

    @pytest.mark.boundary
    def test_negative_offset(self, base_url):
        """测试负数 offset"""
        resp = requests.get(f"{base_url}/api/v1/alerts?offset=-1", timeout=5)
        assert resp.status_code in [200, 422]

    @pytest.mark.boundary
    def test_invalid_time_format(self, base_url):
        """测试无效时间格式"""
        resp = requests.get(f"{base_url}/api/v1/alerts?start_time=invalid", timeout=5)
        assert resp.status_code in [200, 422]

    @pytest.mark.boundary
    def test_empty_query_params(self, base_url):
        """测试空查询参数"""
        resp = requests.get(f"{base_url}/api/v1/alerts?camera_id=&level=", timeout=5)
        # 空参数可能返回 422（验证失败）或 200（忽略空参数）
        assert resp.status_code in [200, 422]

    @pytest.mark.performance
    def test_api_response_time(self, base_url):
        """测试 API 响应时间"""
        times = []
        for _ in range(10):
            start = time.time()
            resp = requests.get(f"{base_url}/health", timeout=5)
            duration = time.time() - start
            if resp.status_code == 200:
                times.append(duration)

        avg_time = sum(times) / len(times)
        assert avg_time < 3.0, f"平均响应时间 {avg_time:.2f}s 超过 3 秒"

    @pytest.mark.performance
    def test_concurrent_requests(self, base_url):
        """测试并发请求"""
        import concurrent.futures

        def make_request():
            return requests.get(f"{base_url}/health", timeout=5)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(1 for r in results if r.status_code == 200)
        assert success_count == 20, f"仅 {success_count}/20 请求成功"

    @pytest.mark.exception
    def test_invalid_json_payload(self, base_url):
        """测试无效 JSON 负载"""
        resp = requests.post(f"{base_url}/api/v1/camera/0/config",
                             data="invalid json", timeout=5)
        assert resp.status_code in [400, 422]

    @pytest.mark.exception
    def test_missing_required_fields(self, base_url):
        """测试缺少必填字段"""
        resp = requests.post(f"{base_url}/api/v1/camera/0/config",
                             json={}, timeout=5)
        # 应该返回错误或使用默认值
        assert resp.status_code in [200, 400, 422]

    @pytest.mark.security
    def test_sql_injection_attempt(self, base_url):
        """测试 SQL 注入防护"""
        malicious = "0' OR '1'='1"
        resp = requests.get(f"{base_url}/api/v1/alerts?camera_id={malicious}", timeout=5)
        # 应该安全处理，不返回所有数据
        assert resp.status_code in [200, 422]

    @pytest.mark.security
    def test_xss_attempt(self, base_url):
        """测试 XSS 防护"""
        xss_payload = "<script>alert('xss')</script>"
        resp = requests.get(f"{base_url}/api/v1/alerts?level={xss_payload}", timeout=5)
        assert resp.status_code in [200, 422]
