import sqlite3


class database:
    def __init__(self, db_path):
        self.connection = sqlite3.connect(db_path)
        self.cursor = self.connection.cursor()
        self._create_table()

    def _create_table(self):
        # Users
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL UNIQUE,
                user_name TEXT NOT NULL,
                waifu_count INTEGER DEFAULT 0,
                last_claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Waifus
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS waifus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                waifu_api_id INTEGER UNIQUE,
                url TEXT NOT NULL,
                preview_url TEXT,
                source TEXT,
                artist_name TEXT,
                artist_url TEXT,
                is_nsfw BOOLEAN,
                tags TEXT
            )
            """
        )

        # Claims
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                waifu_id INTEGER NOT NULL,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (waifu_id) REFERENCES waifus (id)
            )
            """
        )

        self.connection.commit()

    def add_user(self, discord_id, user_name):
        self.cursor.execute(
            """
            INSERT OR IGNORE INTO users (discord_id, user_name)
            VALUES (?, ?)
            """,
            (discord_id, user_name),
        )
        self.connection.commit()

    def get_user(self, discord_id):
        self.cursor.execute(
            """
            SELECT * FROM users WHERE discord_id = ?
            """,
            (discord_id,),
        )
        return self.cursor.fetchone()

    def update_user_waifu_count(self, discord_id, count):
        self.cursor.execute(
            """
            UPDATE users SET waifu_count = ? WHERE discord_id = ?
            """,
            (count, discord_id),
        )
        self.connection.commit()

    def add_waifu(
        self,
        waifu_api_id,
        url,
        preview_url,
        source,
        artist_name,
        artist_url,
        is_nsfw,
        tags,
    ):
        self.cursor.execute(
            """
            INSERT OR IGNORE INTO waifus (waifu_api_id, url, preview_url, source, artist_name, artist_url, is_nsfw, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                waifu_api_id,
                url,
                preview_url,
                source,
                artist_name,
                artist_url,
                is_nsfw,
                tags,
            ),
        )
        self.connection.commit()

    def get_waifu_by_api_id(self, waifu_api_id):
        self.cursor.execute(
            """
            SELECT * FROM waifus WHERE waifu_api_id = ?
            """,
            (waifu_api_id,),
        )
        return self.cursor.fetchone()

    def add_claim(self, user_id, waifu_id):
        self.cursor.execute(
            """
            INSERT INTO claims (user_id, waifu_id)
            VALUES (?, ?)
            """,
            (user_id, waifu_id),
        )
        self.connection.commit()

    def get_claims_by_user(self, user_id):
        self.cursor.execute(
            """
            SELECT * FROM claims WHERE user_id = ?
            """,
            (user_id,),
        )
        return self.cursor.fetchall()

    def get_user_collection(self, user_id):
        self.cursor.execute(
            """
            SELECT w.*
            FROM waifus w
            JOIN claims c ON w.id = c.waifu_id
            WHERE c.user_id = ?
            """,
            (user_id,),
        )
        return self.cursor.fetchall()

    def is_waifu_claimed(self, waifu_id):
        self.cursor.execute(
            """
            SELECT 1 FROM claims WHERE waifu_id = ? LIMIT 1
            """,
            (waifu_id,),
        )
        return self.cursor.fetchone() is not None

    def get_waifu_owner(self, waifu_id):
        self.cursor.execute(
            """
            SELECT u.*
            FROM users u
            JOIN claims c ON u.id = c.user_id
            WHERE c.waifu_id = ?
            """,
            (waifu_id,),
        )
        return self.cursor.fetchone()

    def get_leaderboard(self, limit=10):
        self.cursor.execute(
            """
            SELECT user_name, waifu_count
            FROM users
            ORDER BY waifu_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return self.cursor.fetchall()

    def update_last_claim(self, discord_id):
        self.cursor.execute(
            """
            UPDATE users SET last_claimed_at = CURRENT_TIMESTAMP WHERE discord_id = ?
            """,
            (discord_id,),
        )
        self.connection.commit()

    def get_last_claim_time(self, discord_id):
        self.cursor.execute(
            """
            SELECT last_claimed_at FROM users WHERE discord_id = ?
            """,
            (discord_id,),
        )
        return self.cursor.fetchone()

    def close(self):
        self.connection.close()
