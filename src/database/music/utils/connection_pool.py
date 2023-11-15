import asyncpg
from .. import sql


async def create_pool(dsn, dbname: str):
    try:
        conn = await asyncpg.connect(dsn, database=dbname)
    except asyncpg.InvalidCatalogNameError:
        # db does not exists
        _conn = await asyncpg.connect(dsn, database='tune')
        await _conn.execute(
            sql.CREATE_DB.format(dbname=dbname)
        )
        await _conn.close()
    else:
        await conn.close()
    pool = await asyncpg.create_pool(dsn, database=dbname)
    async with pool.acquire() as connection:
        print("INIT DB")
        await connection.execute(
            sql.CREATE_PLAYLISTS
        )
    return pool
