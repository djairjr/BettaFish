# -*- coding: utf-8 -*-
# @Author  : persist-1<persist1@126.com>
# @Time    : 2025/9/8 00:02
# @Desc: Used to compare the orm mapping model (database/models.py) with the actual structures of the two databases, and perform update operations (connect to database -> structure comparison -> difference report -> interactive synchronization)
# @Tips: This script needs to install the dependency 'pymysql==1.1.0'

import os
import sys
from sqlalchemy import create_engine, inspect as sqlalchemy_inspect
from sqlalchemy.schema import MetaData

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.db_config import mysql_db_config, sqlite_db_config
from database.models import Base

def get_mysql_engine():
    """Create and return a MySQL database engine"""
    conn_str = f"mysql+pymysql://{mysql_db_config['user']}:{mysql_db_config['password']}@{mysql_db_config['host']}:{mysql_db_config['port']}/{mysql_db_config['db_name']}"
    return create_engine(conn_str)

def get_sqlite_engine():
    """Create and return a SQLite database engine"""
    conn_str = f"sqlite:///{sqlite_db_config['db_path']}"
    return create_engine(conn_str)

def get_db_schema(engine):
    """Get the current table structure of the database"""
    inspector = sqlalchemy_inspect(engine)
    schema = {}
    for table_name in inspector.get_table_names():
        columns = {}
        for column in inspector.get_columns(table_name):
            columns[column['name']] = str(column['type'])
        schema[table_name] = columns
    return schema

def get_orm_schema():
    """Get the table structure of the ORM model"""
    schema = {}
    for table_name, table in Base.metadata.tables.items():
        columns = {}
        for column in table.columns:
            columns[column.name] = str(column.type)
        schema[table_name] = columns
    return schema

def compare_schemas(db_schema, orm_schema):
    """Compare the database structure and ORM model structure and return the differences"""
    db_tables = set(db_schema.keys())
    orm_tables = set(orm_schema.keys())

    added_tables = orm_tables - db_tables
    deleted_tables = db_tables - orm_tables
    common_tables = db_tables.intersection(orm_tables)

    changed_tables = {}

    for table in common_tables:
        db_cols = set(db_schema[table].keys())
        orm_cols = set(orm_schema[table].keys())
        added_cols = orm_cols - db_cols
        deleted_cols = db_cols - orm_cols
        
        modified_cols = {}
        for col in db_cols.intersection(orm_cols):
            if db_schema[table][col] != orm_schema[table][col]:
                modified_cols[col] = (db_schema[table][col], orm_schema[table][col])

        if added_cols or deleted_cols or modified_cols:
            changed_tables[table] = {
                "added": list(added_cols),
                "deleted": list(deleted_cols),
                "modified": modified_cols
            }

    return {
        "added_tables": list(added_tables),
        "deleted_tables": list(deleted_tables),
        "changed_tables": changed_tables
    }

def print_diff(db_name, diff):
    """Print difference report"""
    print(f"--- {db_name} database structure difference report ---")
    if not any(diff.values()):
        print("The database structure is consistent with the ORM model and no synchronization is required.")
        return

    if diff.get("added_tables"):
        print("\n[+] New table:")
        for table in diff["added_tables"]:
            print(f"  - {table}")

    if diff.get("deleted_tables"):
        print("\n[-] Deleted table:")
        for table in diff["deleted_tables"]:
            print(f"  - {table}")

    if diff.get("changed_tables"):
        print("\n[*] Changed table:")
        for table, changes in diff["changed_tables"].items():
            print(f"  - {table}:")
            if changes.get("added"):
                print("[+] New fields:", ", ".join(changes["added"]))
            if changes.get("deleted"):
                print("[-] Delete fields:", ", ".join(changes["deleted"]))
            if changes.get("modified"):
                print("[*] Modify fields:")
                for col, types in changes["modified"].items():
                    print(f"      - {col}: {types[0]} -> {types[1]}")
    print("---End of report ---")


def sync_database(engine, diff):
    """Synchronize ORM model to database"""
    metadata = Base.metadata
    
    # Alembic context configuration
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    conn = engine.connect()
    ctx = MigrationContext.configure(conn)
    op = Operations(ctx)

    # Handle deleted tables
    for table_name in diff['deleted_tables']:
        op.drop_table(table_name)
        print(f"Deleted table: {table_name}")

    # Process new tables
    for table_name in diff['added_tables']:
        table = metadata.tables.get(table_name)
        if table is not None:
            table.create(engine)
            print(f"Created table: {table_name}")

    # Handle field changes
    for table_name, changes in diff['changed_tables'].items():
        # Delete field
        for col_name in changes['deleted']:
            op.drop_column(table_name, col_name)
            print(f"Field deleted in table {table_name}: {col_name}")
        # Add new field
        for col_name in changes['added']:
            table = metadata.tables.get(table_name)
            column = table.columns.get(col_name)
            if column is not None:
                op.add_column(table_name, column)
                print(f"A new field has been added to table {table_name}: {col_name}")

        # Modify fields
        for col_name, types in changes['modified'].items():
            table = metadata.tables.get(table_name)
            if table is not None:
                column = table.columns.get(col_name)
                if column is not None:
                    op.alter_column(table_name, col_name, type_=column.type)
                    print(f"Modified field in table {table_name}: {col_name} (type changed to {column.type})")


def main():
    """main function"""
    orm_schema = get_orm_schema()

    # Working with MySQL
    try:
        mysql_engine = get_mysql_engine()
        mysql_schema = get_db_schema(mysql_engine)
        mysql_diff = compare_schemas(mysql_schema, orm_schema)
        print_diff("MySQL", mysql_diff)
        if any(mysql_diff.values()):
            choice = input(">>> Manual confirmation is required: Do you want to synchronize the ORM model to the MySQL database? (y/N):")
            if choice.lower() == 'y':
                sync_database(mysql_engine, mysql_diff)
                print("MySQL database synchronization is completed.")
    except Exception as e:
        print(f"Error while processing MySQL: {e}")


    # Working with SQLite
    try:
        sqlite_engine = get_sqlite_engine()
        sqlite_schema = get_db_schema(sqlite_engine)
        sqlite_diff = compare_schemas(sqlite_schema, orm_schema)
        print_diff("SQLite", sqlite_diff)
        if any(sqlite_diff.values()):
            choice = input(">>> Manual confirmation is required: Do you want to synchronize the ORM model to the SQLite database? (y/N):")
            if choice.lower() == 'y':
                # Note: SQLite does not support ALTER COLUMN to modify field types. The process is simplified here.
                print("Warning: SQLite has limited support for field modifications, and this script will not perform operations that modify field types.")
                sync_database(sqlite_engine, sqlite_diff)
                print("SQLite database synchronization is completed.")
    except Exception as e:
        print(f"Error while processing SQLite: {e}")


if __name__ == "__main__":
    main()

######################### Feedback example #########################
# [*] Changed table:
#   - kuaishou_video:
# [*] Modify fields:
#       - user_id: TEXT -> VARCHAR(64)
#   - xhs_note_comment:
# [*] Modify fields:
#       - comment_id: BIGINT -> VARCHAR(255)
#   - zhihu_content:
# [*] Modify fields:
#       - created_time: BIGINT -> VARCHAR(32)
#       - content_id: BIGINT -> VARCHAR(64)
#   - zhihu_creator:
# [*] Modify fields:
#       - user_id: INTEGER -> VARCHAR(64)
#   - tieba_note:
# [*] Modify fields:
#       - publish_time: BIGINT -> VARCHAR(255)
#       - tieba_id: INTEGER -> VARCHAR(255)
#       - note_id: BIGINT -> VARCHAR(644)
# ---End of report ---
# >>> Manual confirmation is required: Do you want to synchronize the ORM model to the MySQL database? (y/N): y
# Modified field in table kuaishou_video: user_id (type changed to VARCHAR(64))
# Modified field in table xhs_note_comment: comment_id (type changed to VARCHAR(255))
# Modified field in table zhihu_content: created_time (type changed to VARCHAR(32))
# Modified field in table zhihu_content: content_id (type changed to VARCHAR(64))
# Modified field in table zhihu_creator: user_id (type changed to VARCHAR(64))
# Modified field in table tieba_note: publish_time (type changed to VARCHAR(255))
# Modified field in table tieba_note: tieba_id (type changed to VARCHAR(255))
# Modified field in table tieba_note: note_id (type changed to VARCHAR(644))
# MySQL database synchronization is completed.