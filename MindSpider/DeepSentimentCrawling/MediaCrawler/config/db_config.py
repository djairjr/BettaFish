# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#   
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


import os

# mysql config - Database configuration using MindSpider
MYSQL_DB_PWD = "bettafish"
MYSQL_DB_USER = "bettafish"
MYSQL_DB_HOST = "127.0.0.1"
MYSQL_DB_PORT = 5444
MYSQL_DB_NAME = "bettafish"

mysql_db_config = {
    "user": MYSQL_DB_USER,
    "password": MYSQL_DB_PWD,
    "host": MYSQL_DB_HOST,
    "port": MYSQL_DB_PORT,
    "db_name": MYSQL_DB_NAME,
}


# redis config
REDIS_DB_HOST = "127.0.0.1"  # your redis host
REDIS_DB_PWD = os.getenv("REDIS_DB_PWD", "123456")  # your redis password
REDIS_DB_PORT = os.getenv("REDIS_DB_PORT", 6379)  # your redis port
REDIS_DB_NUM = os.getenv("REDIS_DB_NUM", 0)  # your redis db num

# cache type
CACHE_TYPE_REDIS = "redis"
CACHE_TYPE_MEMORY = "memory"

# sqlite config
SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "sqlite_tables.db")

sqlite_db_config = {
    "db_path": SQLITE_DB_PATH
}

# postgresql config - Database configuration using MindSpider (if DB_DIALECT is postgresql) or environment variables
POSTGRESQL_DB_PWD = os.getenv("POSTGRESQL_DB_PWD", "bettafish")
POSTGRESQL_DB_USER = os.getenv("POSTGRESQL_DB_USER", "bettafish")
POSTGRESQL_DB_HOST = os.getenv("POSTGRESQL_DB_HOST", "127.0.0.1")
POSTGRESQL_DB_PORT = os.getenv("POSTGRESQL_DB_PORT", "5444")
POSTGRESQL_DB_NAME = os.getenv("POSTGRESQL_DB_NAME", "bettafish")

postgresql_db_config = {
    "user": POSTGRESQL_DB_USER,
    "password": POSTGRESQL_DB_PWD,
    "host": POSTGRESQL_DB_HOST,
    "port": POSTGRESQL_DB_PORT,
    "db_name": POSTGRESQL_DB_NAME,
}

