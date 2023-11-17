import asyncpg
from logging import getLogger

from .database_checks import *
from .. import sql

log = getLogger("discord")


async def create_pool(dsn, dbname: str):
    exists = await check_database(dsn, dbname)
    if not exists:
        try:
            # creating database
            _conn = await asyncpg.connect(dsn)
            await _conn.execute(
                sql.CREATE_DB.format(dbname=dbname)
            )
            await _conn.close()
        except Exception as e:
            log.error(f"Error while creating a database: {e}")
            raise asyncpg.PostgresError("Error creating database")

    try:
        pool = await asyncpg.create_pool(dsn, database=dbname)
        async with pool.acquire() as connection:
            await connection.execute(
                sql.CREATE_PLAYLISTS
            )
        return pool
    except Exception as e:
        log.error(f"Error creating a pool: {e}")
        raise asyncpg.PostgresError("Error creating connection pool")
