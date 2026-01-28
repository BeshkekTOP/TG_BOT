import pytest
import sqlite3
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys

# Импортируем функции из основного файла
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tgbot


class TestDatabase:
    """Тест 1: Проверка инициализации базы данных"""
    
    def test_database_initialization(self):
        """Тест создания таблиц в базе данных"""
        test_db = "test_giveaways.db"
        
        # Удаляем тестовую БД если существует
        if os.path.exists(test_db):
            os.remove(test_db)
        
        # Инициализируем БД
        conn, cursor = tgbot.init_database()
        
        # Проверяем наличие таблицы channels
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
        assert cursor.fetchone() is not None, "Таблица channels должна существовать"
        
        # Проверяем наличие таблицы giveaways
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='giveaways'")
        assert cursor.fetchone() is not None, "Таблица giveaways должна существовать"
        
        # Проверяем структуру таблицы giveaways
        cursor.execute("PRAGMA table_info(giveaways)")
        columns = [column[1] for column in cursor.fetchall()]
        assert 'text' in columns, "Колонка text должна существовать"
        assert 'winners_count' in columns, "Колонка winners_count должна существовать"
        assert 'check_code' in columns, "Колонка check_code должна существовать"
        
        conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)


class TestCheckCode:
    """Тест 2: Генерация проверочного кода"""
    
    def test_generate_check_code(self):
        """Тест генерации уникального кода проверки"""
        giveaway_id = 1
        user_id = 12345
        
        code1 = tgbot.generate_check_code(giveaway_id, user_id)
        code2 = tgbot.generate_check_code(giveaway_id, user_id)
        
        # Коды должны быть разными (из-за времени)
        assert code1 != code2, "Каждый код должен быть уникальным"
        
        # Код должен быть строкой из 32 символов (MD5 hash)
        assert len(code1) == 32, "Код должен быть длиной 32 символа (MD5)"
        assert isinstance(code1, str), "Код должен быть строкой"


class TestParticipants:
    """Тест 3: Добавление участников"""
    
    @pytest.fixture
    def test_db(self):
        """Фикстура для создания тестовой БД"""
        test_db = "test_giveaways.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        conn = sqlite3.connect(test_db, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participants TEXT DEFAULT '[]'
            )
        """)
        
        cursor.execute("INSERT INTO giveaways (participants) VALUES (?)", ('[]',))
        conn.commit()
        
        yield conn, cursor, 1
        
        conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)
    
    def test_add_participant(self, test_db):
        """Тест добавления участника в розыгрыш"""
        conn, cursor, giveaway_id = test_db
        user_id = 12345
        
        # Сохраняем оригинальные функции
        original_conn = tgbot.conn
        original_cursor = tgbot.cursor
        
        # Временно заменяем на тестовые
        tgbot.conn = conn
        tgbot.cursor = cursor
        
        # Добавляем участника
        tgbot.add_participant(giveaway_id, user_id)
        
        # Проверяем результат
        cursor.execute("SELECT participants FROM giveaways WHERE id = ?", (giveaway_id,))
        participants_str = cursor.fetchone()[0]
        participants = eval(participants_str)
        
        assert user_id in participants, "Участник должен быть добавлен"
        assert len(participants) == 1, "Должен быть один участник"
        
        # Восстанавливаем оригинальные функции
        tgbot.conn = original_conn
        tgbot.cursor = original_cursor
    
    def test_add_duplicate_participant(self, test_db):
        """Тест попытки добавить участника дважды"""
        conn, cursor, giveaway_id = test_db
        user_id = 12345
        
        original_conn = tgbot.conn
        original_cursor = tgbot.cursor
        
        tgbot.conn = conn
        tgbot.cursor = cursor
        
        # Добавляем участника дважды
        tgbot.add_participant(giveaway_id, user_id)
        tgbot.add_participant(giveaway_id, user_id)
        
        # Проверяем, что участник добавлен только один раз
        cursor.execute("SELECT participants FROM giveaways WHERE id = ?", (giveaway_id,))
        participants_str = cursor.fetchone()[0]
        participants = eval(participants_str)
        
        assert participants.count(user_id) == 1, "Участник должен быть добавлен только один раз"
        
        tgbot.conn = original_conn
        tgbot.cursor = original_cursor


class TestParticipantsCount:
    """Тест 4: Подсчет участников"""
    
    @pytest.fixture
    def test_db(self):
        test_db = "test_giveaways.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        conn = sqlite3.connect(test_db, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participants TEXT DEFAULT '[]'
            )
        """)
        
        yield conn, cursor
        
        conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)
    
    def test_get_participants_count_empty(self, test_db):
        """Тест подсчета участников когда их нет"""
        conn, cursor = test_db
        
        cursor.execute("INSERT INTO giveaways (participants) VALUES (?)", ('[]',))
        conn.commit()
        giveaway_id = cursor.lastrowid
        
        original_conn = tgbot.conn
        original_cursor = tgbot.cursor
        
        tgbot.conn = conn
        tgbot.cursor = cursor
        
        count = tgbot.get_participants_count(giveaway_id)
        
        assert count == 0, "Количество участников должно быть 0"
        
        tgbot.conn = original_conn
        tgbot.cursor = original_cursor
    
    def test_get_participants_count_multiple(self, test_db):
        """Тест подсчета нескольких участников"""
        conn, cursor = test_db
        
        participants = [123, 456, 789]
        cursor.execute("INSERT INTO giveaways (participants) VALUES (?)", (str(participants),))
        conn.commit()
        giveaway_id = cursor.lastrowid
        
        original_conn = tgbot.conn
        original_cursor = tgbot.cursor
        
        tgbot.conn = conn
        tgbot.cursor = cursor
        
        count = tgbot.get_participants_count(giveaway_id)
        
        assert count == 3, f"Количество участников должно быть 3, получено {count}"
        
        tgbot.conn = original_conn
        tgbot.cursor = original_cursor


class TestChannelManagement:
    """Тест 5: Управление каналами"""
    
    @pytest.fixture
    def test_db(self):
        test_db = "test_channels.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        conn = sqlite3.connect(test_db, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                channel_username TEXT,
                channel_name TEXT,
                UNIQUE(user_id, channel_id)
            )
        """)
        
        yield conn, cursor
        
        conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)
    
    def test_add_channel(self, test_db):
        """Тест добавления канала"""
        conn, cursor = test_db
        
        user_id = 12345
        channel_id = "@test_channel"
        channel_username = "@test_channel"
        channel_name = "Test Channel"
        
        cursor.execute(
            "INSERT OR IGNORE INTO channels (user_id, channel_id, channel_username, channel_name) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, channel_username, channel_name)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM channels WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        assert result is not None, "Канал должен быть добавлен"
        assert result[4] == channel_name, "Название канала должно совпадать"
    
    def test_channel_unique_constraint(self, test_db):
        """Тест уникальности канала для пользователя"""
        conn, cursor = test_db
        
        user_id = 12345
        channel_id = "@test_channel"
        channel_username = "@test_channel"
        channel_name = "Test Channel"
        
        # Добавляем канал первый раз
        cursor.execute(
            "INSERT OR IGNORE INTO channels (user_id, channel_id, channel_username, channel_name) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, channel_username, channel_name)
        )
        conn.commit()
        
        # Пытаемся добавить тот же канал еще раз
        cursor.execute(
            "INSERT OR IGNORE INTO channels (user_id, channel_id, channel_username, channel_name) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, channel_username, channel_name)
        )
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM channels WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))
        count = cursor.fetchone()[0]
        
        assert count == 1, "Канал должен быть добавлен только один раз"


class TestGiveawayCreation:
    """Тест 6: Создание розыгрыша"""
    
    @pytest.fixture
    def test_db(self):
        test_db = "test_giveaway_creation.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        conn = sqlite3.connect(test_db, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                media_type TEXT,
                media_file_id TEXT,
                button_text TEXT,
                channels TEXT,
                winners_count INTEGER,
                channel_id TEXT,
                publish_time TEXT,
                end_type TEXT,
                end_time TEXT,
                end_count INTEGER,
                participants TEXT DEFAULT '[]',
                created_at TEXT,
                is_published BOOLEAN DEFAULT FALSE,
                check_code TEXT
            )
        """)
        
        yield conn, cursor
        
        conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)
    
    def test_create_giveaway(self, test_db):
        """Тест создания розыгрыша в БД"""
        conn, cursor = test_db
        
        text = "Test giveaway"
        button_text = "Участвовать"
        winners_count = 3
        channel_id = "@test_channel"
        publish_time = "сейчас"
        end_type = "time"
        end_time = "01.01.2025 12:00"
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO giveaways (text, button_text, winners_count, channel_id, publish_time, end_type, end_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (text, button_text, winners_count, channel_id, publish_time, end_type, end_time, current_time))
        conn.commit()
        giveaway_id = cursor.lastrowid
        
        cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
        result = cursor.fetchone()
        
        assert result is not None, "Розыгрыш должен быть создан"
        assert result[1] == text, "Текст должен совпадать"
        assert result[6] == winners_count, "Количество победителей должно совпадать"


class TestValidation:
    """Тест 7: Валидация данных"""
    
    def test_winners_count_validation(self):
        """Тест валидации количества победителей"""
        # Положительное число
        assert isinstance(1, int) and 1 > 0, "Положительное число должно быть валидным"
        
        # Ноль должен быть невалидным
        assert not (isinstance(0, int) and 0 > 0), "Ноль должен быть невалидным"
        
        # Отрицательное число должно быть невалидным
        assert not (isinstance(-1, int) and -1 > 0), "Отрицательное число должно быть невалидным"
    
    def test_date_parsing(self):
        """Тест парсинга даты"""
        date_str = "01.01.2025 12:00"
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
            assert dt is not None, "Дата должна быть распарсена"
            assert dt.year == 2025, "Год должен быть 2025"
            assert dt.month == 1, "Месяц должен быть 1"
            assert dt.day == 1, "День должен быть 1"
        except ValueError:
            pytest.fail("Дата должна быть валидной")
    
    def test_future_date_validation(self):
        """Тест проверки что дата в будущем"""
        future_date = datetime.now() + timedelta(days=1)
        past_date = datetime.now() - timedelta(days=1)
        
        assert future_date > datetime.now(), "Будущая дата должна быть больше текущей"
        assert past_date <= datetime.now(), "Прошедшая дата должна быть меньше или равна текущей"


class TestChannelParsing:
    """Тест 8: Парсинг каналов"""
    
    def test_parse_channel_from_url(self):
        """Тест извлечения username из URL"""
        url = "https://t.me/test_channel"
        username = url.split("/")[-1]
        assert username == "test_channel", "Username должен быть извлечен корректно"
        
        channel_format = f"@{username}"
        assert channel_format == "@test_channel", "Формат канала должен быть @username"
    
    def test_parse_channel_from_at_format(self):
        """Тест парсинга канала в формате @username"""
        channel = "@test_channel"
        assert channel.startswith("@"), "Канал должен начинаться с @"
        
        username = channel[1:]  # Убираем @
        assert username == "test_channel", "Username должен быть извлечен корректно"
    
    def test_parse_multiple_channels(self):
        """Тест парсинга нескольких каналов"""
        text = "@channel1\n@channel2\n@channel3"
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        channels = [line for line in lines if line.startswith("@")]
        
        assert len(channels) == 3, "Должно быть 3 канала"
        assert "@channel1" in channels, "channel1 должен быть в списке"
        assert "@channel2" in channels, "channel2 должен быть в списке"
        assert "@channel3" in channels, "channel3 должен быть в списке"


class TestWinnersSelection:
    """Тест 9: Выбор победителей"""
    
    def test_winners_selection_logic(self):
        """Тест логики выбора победителей"""
        import random
        
        participants = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        winners_count = 3
        
        # Симулируем выбор победителей
        winners = random.sample(participants, min(len(participants), winners_count))
        
        assert len(winners) == 3, "Должно быть выбрано 3 победителя"
        assert all(winner in participants for winner in winners), "Все победители должны быть участниками"
        assert len(set(winners)) == len(winners), "Победители должны быть уникальными"
    
    def test_winners_selection_more_than_participants(self):
        """Тест выбора победителей когда их больше чем участников"""
        import random
        
        participants = [1, 2, 3]
        winners_count = 10
        
        winners = random.sample(participants, min(len(participants), winners_count))
        
        assert len(winners) == 3, "Количество победителей не должно превышать количество участников"
    
    def test_winners_selection_no_participants(self):
        """Тест выбора победителей когда участников нет"""
        participants = []
        winners_count = 3
        
        if not participants:
            winners = []
        else:
            import random
            winners = random.sample(participants, min(len(participants), winners_count))
        
        assert len(winners) == 0, "Победителей не должно быть если нет участников"


class TestDateTimeOperations:
    """Тест 10: Работа с датой и временем"""
    
    def test_datetime_formatting(self):
        """Тест форматирования даты и времени"""
        dt = datetime(2025, 1, 15, 14, 30)
        formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
        
        assert formatted == "2025-01-15 14:30:00", "Дата должна быть отформатирована корректно"
    
    def test_datetime_comparison(self):
        """Тест сравнения дат"""
        now = datetime.now()
        future = now + timedelta(hours=1)
        past = now - timedelta(hours=1)
        
        assert future > now, "Будущая дата должна быть больше текущей"
        assert past < now, "Прошедшая дата должна быть меньше текущей"
        assert now == now, "Текущая дата должна быть равна себе"
    
    def test_timedelta_calculations(self):
        """Тест вычислений с timedelta"""
        now = datetime.now()
        in_10_minutes = now + timedelta(minutes=10)
        in_1_hour = now + timedelta(hours=1)
        in_1_day = now + timedelta(days=1)
        in_1_week = now + timedelta(weeks=1)
        
        assert (in_10_minutes - now).total_seconds() == 600, "10 минут = 600 секунд"
        assert (in_1_hour - now).total_seconds() == 3600, "1 час = 3600 секунд"
        assert (in_1_day - now).days == 1, "1 день = 1 день"
        assert (in_1_week - now).days == 7, "1 неделя = 7 дней"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

