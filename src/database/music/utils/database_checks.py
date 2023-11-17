import os
import asyncpg


async def check_database(dsn: str, dbname: str):
    async with asyncpg.connect(dsn) as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1;",
            dbname
        )
        return exists == 1


async def check_table(dsn: str, dbname: str, tbname: str):
    async with asyncpg.connect(dsn, database=dbname) as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_tables WHERE tablename = $1",
            tbname
        )
        return exists == 1
