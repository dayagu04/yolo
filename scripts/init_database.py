"""
数据库初始化脚本
创建 MySQL 数据库、表结构，并写入初始管理员账号
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from backend.database import DatabaseManager, Base
from sqlalchemy import create_engine, text


def load_config():
    config_path = ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 从环境变量注入数据库密码
    db_password = os.environ.get("YOLO_DATABASE_PASSWORD", "")
    if db_password:
        cfg["database"]["password"] = db_password

    return cfg


def create_database(config: dict):
    """创建数据库（如果不存在）"""
    db_config = config["database"]
    db_name = db_config["database"]

    # 连接到 MySQL 服务器（不指定数据库）
    server_url = (
        f"mysql+pymysql://{db_config['user']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}"
        f"?charset={db_config.get('charset', 'utf8mb4')}"
    )

    engine = create_engine(server_url, echo=False)

    try:
        with engine.connect() as conn:
            # 检查数据库是否存在
            result = conn.execute(
                text(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{db_name}'")
            )
            exists = result.fetchone() is not None

            if not exists:
                print(f"创建数据库: {db_name}")
                conn.execute(text(f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                conn.commit()
                print(f"✓ 数据库 {db_name} 创建成功")
            else:
                print(f"✓ 数据库 {db_name} 已存在")

    except Exception as e:
        print(f"✗ 创建数据库失败: {e}")
        raise
    finally:
        engine.dispose()


def init_tables(config: dict):
    """初始化表结构"""
    print("\n初始化表结构...")
    db_manager = DatabaseManager(config["database"])
    db_manager.create_tables()
    print("✓ 表结构初始化完成")
    return db_manager


def create_admin_user(db_manager: DatabaseManager, config: dict):
    """创建初始管理员账号"""
    print("\n创建管理员账号...")

    # 检查是否已有用户
    if db_manager.user_exists():
        print("✓ 用户表已有数据，跳过管理员创建")
        return

    # 从配置和环境变量获取管理员信息
    username = config.get("auth", {}).get("init_admin_username", "admin")
    password = os.environ.get("YOLO_AUTH_INIT_ADMIN_PASSWORD", "")

    if not password:
        print("⚠ 未设置环境变量 YOLO_AUTH_INIT_ADMIN_PASSWORD，跳过管理员创建")
        print("  请在 .env 文件中设置该变量后重新运行")
        return

    # 导入认证模块并创建用户
    from backend.auth import hash_password
    hashed_pwd = hash_password(password)
    db_manager.create_user(username, hashed_pwd, role="admin")
    print(f"✓ 管理员账号已创建: {username}")
    print(f"  角色: admin")
    print(f"  密码: {'*' * len(password)}")


def main():
    print("=" * 60)
    print("  智能安防监控系统 - 数据库初始化")
    print("=" * 60)

    try:
        # 加载配置
        print("\n[1/4] 加载配置文件...")
        config = load_config()
        db_config = config.get("database")

        if not db_config:
            print("✗ 配置文件中未找到 database 配置")
            return

        print(f"✓ 配置加载成功")
        print(f"  - 主机: {db_config['host']}:{db_config['port']}")
        print(f"  - 用户: {db_config['user']}")
        print(f"  - 数据库: {db_config['database']}")

        # 创建数据库
        print("\n[2/4] 创建数据库...")
        create_database(config)

        # 初始化表
        print("\n[3/4] 初始化表结构...")
        db_manager = init_tables(config)

        # 创建管理员账号
        print("\n[4/4] 创建管理员账号...")
        create_admin_user(db_manager, config)

        print("\n" + "=" * 60)
        print("  ✓ 数据库初始化完成")
        print("=" * 60)
        print("\n可以使用以下命令启动服务:")
        print("  uvicorn backend.main:app --host 0.0.0.0 --port 9000")

    except FileNotFoundError:
        print("\n✗ 配置文件不存在: config.yaml")
        print("  请先复制 config.yaml.example 并修改配置")
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
