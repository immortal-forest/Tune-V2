# this shit will probably cause some problems in future

CREATE_DB = """CREATE DATABASE {dbname};"""
CREATE_PLAYLISTS = """
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    member_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    modified_at TIMESTAMP NOT NULL
);
"""

INSERT_PLAYLIST = """
INSERT INTO playlists (playlist_id, name, member_id, created_at, modified_at)
VALUES ($1, $2, $3, current_timestamp, current_timestamp);
"""

UPDATE_PLAYLISTS = """
UPDATE playlists SET modified_at = current_timestamp WHERE playlist_id = '{playlist_id}';
"""

CREATE_PLAYLIST = """
CREATE SEQUENCE IF NOT EXISTS {playlist_id}_seq;

CREATE TABLE IF NOT EXISTS {playlist_id} (
    index INT NOT NULL DEFAULT nextval('{playlist_id}_seq'),
    title TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL UNIQUE,
    source INT NOT NULL,
);
"""

INSERT_ITEM = """INSERT INTO {playlist_id} (name, url, source) VALUES ($1, $2, $3);"""

DELETE_ITEM = """DELETE FROM {playlist_id} WHERE id = $1 or title = $1;"""

ON_DELETE = """
ALTER SEQUENCE {playlist_id}_seq RESTART 1;

UPDATE {playlist_id} SET id = DEFAULT;
"""

SEARCH_PLAYLIST = """SELECT * FROM playlists WHERE playlist_id = $1 or name ILKIE $1;"""
