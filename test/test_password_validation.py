"""
测试密码强度验证功能
"""
import pytest
from backend.auth import validate_password_strength, hash_password


class TestPasswordValidation:
    """测试密码强度验证"""

    def test_validate_password_empty(self):
        """测试空密码"""
        is_valid, error_msg = validate_password_strength("")
        assert not is_valid
        assert "不能为空" in error_msg

    def test_validate_password_too_short(self):
        """测试过短密码"""
        is_valid, error_msg = validate_password_strength("Abc123")
        assert not is_valid
        assert "至少需要 8 位" in error_msg

    def test_validate_password_no_lowercase(self):
        """测试缺少小写字母"""
        is_valid, error_msg = validate_password_strength("ABCD1234")
        assert not is_valid
        assert "小写字母" in error_msg

    def test_validate_password_no_uppercase(self):
        """测试缺少大写字母"""
        is_valid, error_msg = validate_password_strength("abcd1234")
        assert not is_valid
        assert "大写字母" in error_msg

    def test_validate_password_no_digit(self):
        """测试缺少数字"""
        is_valid, error_msg = validate_password_strength("Abcdefgh")
        assert not is_valid
        assert "数字" in error_msg

    def test_validate_password_valid_basic(self):
        """测试有效密码（基本要求）"""
        is_valid, error_msg = validate_password_strength("Abcd1234")
        assert is_valid
        assert error_msg == ""

    def test_validate_password_valid_with_special(self):
        """测试有效密码（包含特殊字符）"""
        is_valid, error_msg = validate_password_strength("Abcd123!")
        assert is_valid
        assert error_msg == ""

    def test_validate_password_complex(self):
        """测试复杂密码"""
        is_valid, error_msg = validate_password_strength("MyP@ssw0rd2024!")
        assert is_valid
        assert error_msg == ""

    def test_hash_password_produces_different_hashes(self):
        """测试相同密码产生不同哈希（盐值随机）"""
        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # bcrypt 每次哈希都不同

    def test_hash_password_format(self):
        """测试密码哈希格式"""
        password = "TestPassword123"
        hashed = hash_password(password)
        assert isinstance(hashed, str)
        assert hashed.startswith("$2b$")  # bcrypt 哈希前缀
        assert len(hashed) == 60  # bcrypt 哈希长度


@pytest.mark.parametrize(
    "password,expected_valid",
    [
        ("", False),  # 空密码
        ("123", False),  # 过短
        ("Abcd1234", True),  # 最小有效密码
        ("MyPassword123", True),  # 有效密码
        ("weak", False),  # 过短且无数字
        ("WeakPassword", False),  # 无数字
        ("weakpassword123", False),  # 无大写
        ("WEAKPASSWORD123", False),  # 无小写
        ("MyP@ssw0rd!", True),  # 强密码
        ("12345678", False),  # 纯数字
        ("abcdefgh", False),  # 纯小写
        ("ABCDEFGH", False),  # 纯大写
    ],
)
def test_password_validation_parametrized(password, expected_valid):
    """参数化测试密码验证"""
    is_valid, _ = validate_password_strength(password)
    assert is_valid == expected_valid
