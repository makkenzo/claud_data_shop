"""
Core database module.

This module provides a service for working with the database.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg

from core.models import SaleItem

from .models import Warehouse, WarehouseCreate

logger = logging.getLogger("database_service")


class DatabaseService:
    """
    Сервисный слой для работы с базой данных.
    Реализует паттерн Repository для отделения логики доступа к данным.
    """

    def __init__(self, db_pool: Optional[asyncpg.Pool]):
        if db_pool is None:
            raise ValueError("db_pool не инициализирован!")
        self.pool = db_pool

    async def get_products(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        department: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает список товаров с учетом параметров фильтрации и сортировки.

        Args:
            skip: Количество записей для пропуска (пагинация)
            limit: Максимальное количество записей для возврата
            search: Строка поиска
            sort_by: Поле для сортировки
            sort_order: Порядок сортировки (asc или desc)
            department: Фильтр по отделу
            min_price: Минимальная цена
            max_price: Максимальная цена

        Returns:
            Список словарей с данными товаров
        """
        query_parts = ["SELECT * FROM products WHERE TRUE"]
        params = []
        param_index = 1  # PostgreSQL использует $1, $2...

        if search:
            query_parts.append(
                f"AND (sku_name ILIKE ${param_index} OR sku_code ILIKE ${param_index + 1} OR barcode ILIKE ${param_index + 2})"
            )
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
            param_index += 3

        if department:
            query_parts.append(f"AND department = ${param_index}")
            params.append(department)
            param_index += 1

        if min_price is not None:
            query_parts.append(f"AND price >= ${param_index}")
            params.append(min_price)
            param_index += 1

        if max_price is not None:
            query_parts.append(f"AND price <= ${param_index}")
            params.append(max_price)
            param_index += 1

        valid_columns = [
            "id",
            "sku_code",
            "sku_name",
            "price",
            "cost_price",
            "supplier",
            "department",
        ]

        if sort_by and sort_by in valid_columns:
            sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"
            query_parts.append(f"ORDER BY {sort_by} {sort_order}")
        else:
            query_parts.append("ORDER BY id ASC")

        query_parts.append(f"LIMIT ${param_index} OFFSET ${param_index + 1}")
        params.extend([limit, skip])

        query = " ".join(query_parts)

        logger.info("Query: %s", query)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка при получении списка товаров: %s", e)
            raise

    async def get_local_products(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        department: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        warehouse_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает список локальных товаров пользователя с фильтрами и сортировкой.

        Args:
            user_id: ID пользователя
            skip: Количество записей для пропуска (пагинация)
            limit: Максимальное количество записей для возврата
            search: Строка поиска
            sort_by: Поле для сортировки
            sort_order: Порядок сортировки (asc или desc)
            department: Фильтр по отделу
            min_price: Минимальная цена
            max_price: Максимальная цена

        Returns:
            Список словарей с данными товаров
        """
        query_parts = ["SELECT * FROM local_products WHERE user_id = $1"]
        params = [user_id]
        param_index = 2  # PostgreSQL использует $1, $2, $3...

        if search:
            query_parts.append(
                f"AND (sku_name ILIKE ${param_index} OR sku_code ILIKE ${param_index + 1} OR barcode ILIKE ${param_index + 2})"
            )
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
            param_index += 3

        if department:
            query_parts.append(f"AND department = ${param_index}")
            params.append(department)
            param_index += 1

        if min_price is not None:
            query_parts.append(f"AND price >= ${param_index}")
            params.append(min_price)
            param_index += 1

        if max_price is not None:
            query_parts.append(f"AND price <= ${param_index}")
            params.append(max_price)
            param_index += 1

        if warehouse_id is not None:
            query_parts.append(
                f"""AND id IN (SELECT product_id FROM warehouse_products WHERE warehouse_id = ${param_index})"""
            )
            params.append(warehouse_id)
            param_index += 1

        valid_columns = [
            "id",
            "sku_code",
            "sku_name",
            "price",
            "cost_price",
            "supplier",
            "department",
        ]

        if sort_by and sort_by in valid_columns:
            sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"
            query_parts.append(f"ORDER BY {sort_by} {sort_order}")
        else:
            query_parts.append("ORDER BY id ASC")

        query_parts.append(f"LIMIT ${param_index} OFFSET ${param_index + 1}")
        params.extend([limit, skip])

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка при получении списка товаров: %s", e)
            raise

    async def get_products_count(
        self,
        search: Optional[str] = None,
        department: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> int:
        """
        Получает общее количество товаров с учетом фильтрации.

        Args:
            search: Строка поиска
            department: Фильтр по отделу
            min_price: Минимальная цена
            max_price: Максимальная цена

        Returns:
            Общее количество товаров
        """
        query_parts = ["SELECT COUNT(*) FROM products WHERE 1=1"]
        params = []
        param_index = 1  # PostgreSQL использует $1, $2, $3...

        if search:
            query_parts.append(
                f"AND (sku_name ILIKE ${param_index} OR sku_code ILIKE ${param_index + 1} OR barcode ILIKE ${param_index + 2})"
            )
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
            param_index += 3

        if department:
            query_parts.append(f"AND department = ${param_index}")
            params.append(department)
            param_index += 1

        if min_price is not None:
            query_parts.append(f"AND price >= ${param_index}")
            params.append(min_price)
            param_index += 1

        if max_price is not None:
            query_parts.append(f"AND price <= ${param_index}")
            params.append(max_price)
            param_index += 1

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *params)
            return result if result else 0
        except Exception as e:
            logger.error("Ошибка при получении количества товаров: %s", e)
            raise

    async def get_local_products_count(
        self,
        user_id: int,
        search: Optional[str] = None,
        department: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        warehouse_id: Optional[int] = None,
    ) -> int:
        """
        Получает общее количество товаров пользователя с учетом фильтрации.

        Args:
            user_id: ID пользователя
            search: Строка поиска
            department: Фильтр по отделу
            min_price: Минимальная цена
            max_price: Максимальная цена

        Returns:
            Общее количество товаров
        """
        query_parts = ["SELECT COUNT(*) FROM local_products WHERE user_id = $1"]
        params = [user_id]
        param_index = 2  # PostgreSQL использует $1, $2, $3...

        if search:
            query_parts.append(
                f"AND (sku_name ILIKE ${param_index} OR sku_code ILIKE ${param_index + 1} OR barcode ILIKE ${param_index + 2})"
            )
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
            param_index += 3

        if department:
            query_parts.append(f"AND department = ${param_index}")
            params.append(department)
            param_index += 1

        if min_price is not None:
            query_parts.append(f"AND price >= ${param_index}")
            params.append(min_price)
            param_index += 1

        if max_price is not None:
            query_parts.append(f"AND price <= ${param_index}")
            params.append(max_price)
            param_index += 1

        if warehouse_id is not None:
            query_parts.append(
                f"""AND id IN (SELECT product_id FROM warehouse_products WHERE warehouse_id = ${param_index})"""
            )
            params.append(warehouse_id)
            param_index += 1

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *params)
            return result if result else 0
        except Exception as e:
            logger.error("Ошибка при получении количества товаров: %s", e)
            raise

    async def get_warehouses_count(self, user_id: int, search: Optional[str] = None) -> int:
        """
        Получает общее количество складов пользователя с учетом параметров фильтрации.

        Args:
            user_id: ID пользователя
            search: Строка поиска

        Returns:
            Общее количество складов
        """
        query_parts = ["SELECT COUNT(*) FROM warehouses WHERE user_id = $1"]
        params = [user_id]
        param_index = 1  # PostgreSQL использует $1, $2, $3...

        if search:
            query_parts.append(
                f"AND (name ILIKE ${param_index} OR location ILIKE ${param_index + 1})"
            )
            search_term = f"%{search}%"
            params.extend([search_term, search_term])
            param_index += 2

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *params)
            return result if result else 0
        except Exception as e:
            logger.error("Ошибка при получении количества складов: %s", e)
            raise

    async def get_product_by_barcode(self, barcode: str) -> Optional[Dict[str, Any]]:
        """
        Получение товара по штрих-коду.

        Args:
            barcode: Штрих-код товара

        Returns:
            Информация о товаре или None, если товар не найден
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM products WHERE barcode = $1", barcode)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении товара по штрих-коду из БД: %s", str(e))
            raise

    async def get_product_by_id(self, product_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает товар по ID.

        Args:
            product_id: ID товара

        Returns:
            Словарь с данными товара или None, если товар не найден
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM products WHERE id = $1", product_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении товара по ID %s: %s", product_id, str(e))
            raise

    async def get_local_product_by_id(self, product_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает товар по ID.

        Args:
            product_id: ID товара

        Returns:
            Словарь с данными товара или None, если товар не найден
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM local_products WHERE id = $1", product_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении товара по ID %s: %s", product_id, str(e))
            raise

    async def get_product_by_sku(self, sku_code: str) -> Optional[Dict[str, Any]]:
        """
        Получает товар по SKU коду.

        Args:
            sku_code: SKU код товара

        Returns:
            Словарь с данными товара или None, если товар не найден
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM products WHERE sku_code = $1", sku_code)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении товара по SKU %s: %s", sku_code, str(e))
            raise

    async def get_local_product_by_sku(
        self, sku_code: str, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Получает товар по SKU коду.

        Args:
            sku_code: SKU код товара

        Returns:
            Словарь с данными товара или None, если товар не найден
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM local_products WHERE user_id = $1 AND sku_code = $2",
                    user_id,
                    sku_code,
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении товара по SKU %s: %s", sku_code, str(e))
            raise

    async def get_warehouse_by_name(self, name: str, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает склад по имени.

        Args:
            name: Имя склада
            user_id: ID пользователя

        Returns:
            Словарь с данными склада или None, если склад не найден
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM warehouses WHERE name = $1 AND user_id = $2", name, user_id
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении склада по имени %s: %s", name, str(e))

    async def create_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает новый товар.

        Args:
            product_data: Словарь с данными товара

        Returns:
            Словарь с данными созданного товара, включая ID
        """
        fields = product_data.keys()
        placeholders = ", ".join([f"${i+1}" for i in range(len(fields))])  # Используем $1, $2, ...
        fields_str = ", ".join(fields)

        query = f"INSERT INTO products ({fields_str}) VALUES ({placeholders}) RETURNING *"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(query, *product_data.values())

            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при создании товара: %s", str(e))
            raise

    async def create_local_product(
        self, product_data: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """
        Создает новый локальный товар.

        Args:
            product_data: Словарь с данными товара
            user_id: ID пользователя

        Returns:
            Словарь с данными созданного товара, включая ID
        """
        product_data["user_id"] = user_id
        fields = list(product_data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(fields))])  # Используем $1, $2, ...
        fields_str = ", ".join(fields)

        query = f"""
            INSERT INTO local_products ({fields_str})
            VALUES ({placeholders})
            RETURNING *
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():  # Используем транзакцию
                    row = await conn.fetchrow(
                        query, *product_data.values()
                    )  # fetchrow() сразу возвращает данные

            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при создании локального товара: %s", str(e))
            raise

    async def update_product(
        self, product_id: int, product_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет данные товара.

        Args:
            product_id: ID товара
            product_data: Словарь с обновляемыми данными товара

        Returns:
            Словарь с обновленными данными товара или None, если товар не найден
        """
        if not product_data:
            return await self.get_product_by_id(product_id)

        set_parts = []
        params = []

        for i, (key, value) in enumerate(product_data.items(), start=1):
            set_parts.append(f"{key} = ${i}")
            params.append(value)

        params.append(product_id)
        query = f"UPDATE products SET {', '.join(set_parts)} WHERE id = ${len(params)} RETURNING *"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        query, *params
                    )  # fetchrow() сразу возвращает обновленные данные

            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при обновлении товара с ID %s: %s", product_id, str(e))
            raise

    async def update_local_product(
        self, product_id: int, product_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет данные локального товара.

        Args:
            product_id: ID товара
            product_data: Словарь с обновляемыми данными товара

        Returns:
            Словарь с обновленными данными товара или None, если товар не найден
        """
        if not product_data:
            return await self.get_local_product_by_id(product_id)

        set_parts = []
        params = []

        for i, (key, value) in enumerate(product_data.items(), start=1):
            set_parts.append(f"{key} = ${i}")
            params.append(value)

        params.append(product_id)
        query = f"UPDATE local_products SET {', '.join(set_parts)} WHERE id = ${len(params)} RETURNING *"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        query, *params
                    )  # fetchrow() сразу возвращает обновленные данные

            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при обновлении локального товара с ID %s: %s", product_id, e)
            raise

    async def delete_product(self, product_id: int) -> bool:
        """
        Удаляет товар.

        Args:
            product_id: ID товара

        Returns:
            True, если товар успешно удален, иначе False
        """
        query = "DELETE FROM products WHERE id = $1"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(query, product_id)

            return result.startswith("DELETE")  # asyncpg возвращает строку 'DELETE <количество>'
        except Exception as e:
            logger.error("Ошибка при удалении товара с ID %s: %s", product_id, e)
            raise

    async def delete_local_product(self, product_id: int) -> bool:
        """
        Удаляет локальный товар.

        Args:
            product_id: ID товара

        Returns:
            True, если товар успешно удален, иначе False
        """
        query = "DELETE FROM local_products WHERE id = $1"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(query, product_id)

            return result.startswith("DELETE")  # asyncpg возвращает строку 'DELETE <количество>'
        except Exception as e:
            logger.error("Ошибка при удалении локального товара с ID %s: %s", product_id, e)
            raise

    async def add_audit_log(
        self, action: str, entity: str, entity_id: str, user_id: int, details: str = ""
    ) -> int:
        """
        Добавляет запись в лог аудита.

        Args:
            action: Тип действия (create, update, delete, read)
            entity: Тип сущности (product, user)
            entity_id: ID сущности
            user_id: ID пользователя
            details: Дополнительные детали

        Returns:
            ID созданной записи
        """
        query = """
        INSERT INTO audit_log (action, entity, entity_id, user_id, timestamp, details)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.fetchval(
                        query, action, entity, entity_id, user_id, datetime.utcnow(), details
                    )

            return result
        except Exception as e:
            logger.error("Ошибка при добавлении записи в аудит: %s", e)
            raise

    async def get_audit_logs(
        self,
        skip: int = 0,
        limit: int = 100,
        entity: Optional[str] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает записи из лога аудита с учетом параметров фильтрации.

        Args:
            skip: Количество записей для пропуска (пагинация)
            limit: Максимальное количество записей для возврата
            entity: Фильтр по типу сущности
            action: Фильтр по типу действия
            user_id: Фильтр по ID пользователя
            from_date: Фильтр по начальной дате
            to_date: Фильтр по конечной дате

        Returns:
            Список словарей с данными записей аудита
        """
        query_parts = ["SELECT * FROM audit_log WHERE 1=1"]
        params = []

        if entity:
            query_parts.append("AND entity = $1")
            params.append(entity)

        if action:
            query_parts.append(f"AND action = ${len(params) + 1}")
            params.append(action)

        if user_id:
            query_parts.append(f"AND user_id = ${len(params) + 1}")
            params.append(user_id)

        if from_date:
            query_parts.append(f"AND timestamp >= ${len(params) + 1}")
            params.append(from_date)

        if to_date:
            query_parts.append(f"AND timestamp <= ${len(params) + 1}")
            params.append(to_date)

        query_parts.append(
            f"ORDER BY timestamp DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        )
        params.extend([limit, skip])

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                logs = [dict(row) for row in rows]

            return logs
        except Exception as e:
            logger.error("Ошибка при получении записей аудита: %s", e)
            raise

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по имени пользователя.

        Args:
            username: Имя пользователя

        Returns:
            Словарь с данными пользователя или None, если пользователь не найден
        """
        query = "SELECT * FROM users WHERE username = $1"

        try:
            async with self.pool.acquire() as conn:
                user = await conn.fetchrow(query, username)

            if user:
                user_dict = dict(user)
                user_dict["roles"] = user_dict["roles"].split(",") if user_dict["roles"] else []
                return user_dict

            return None
        except Exception as e:
            logger.error("Ошибка при получении пользователя %s: %s", username, e)
            raise

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает нового пользователя.

        Args:
            user_data: Словарь с данными пользователя

        Returns:
            Словарь с данными созданного пользователя, включая ID
        """
        if "roles" in user_data and isinstance(user_data["roles"], list):
            user_data["roles"] = ",".join(user_data["roles"])

        fields = user_data.keys()
        placeholders = ", ".join(f"${i+1}" for i in range(len(fields)))
        fields_str = ", ".join(fields)

        query = f"INSERT INTO users ({fields_str}) VALUES ({placeholders}) RETURNING username"

        try:
            async with self.pool.acquire() as conn:
                username = await conn.fetchval(query, *user_data.values())

            return await self.get_user_by_username(username)
        except Exception as e:
            logger.error("Ошибка при создании пользователя: %s", e)
            raise

    async def update_user(
        self, username: str, user_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет данные пользователя.

        Args:
            username: Имя пользователя
            user_data: Словарь с обновляемыми данными пользователя

        Returns:
            Словарь с обновленными данными пользователя или None, если пользователь не найден
        """
        if not user_data:
            return await self.get_user_by_username(username)

        # Преобразуем список ролей в строку
        if "roles" in user_data and isinstance(user_data["roles"], list):
            user_data["roles"] = ",".join(user_data["roles"])

        set_parts = [f"{key} = ${i+1}" for i, key in enumerate(user_data.keys())]
        query = f"UPDATE users SET {', '.join(set_parts)} WHERE username = ${len(user_data) + 1} RETURNING username"

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *user_data.values(), username)

            if not result:
                return None

            return await self.get_user_by_username(username)
        except Exception as e:
            logger.error("Ошибка при обновлении пользователя %s: %s", username, e)
            raise

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по email.

        Args:
            email: Email пользователя

        Returns:
            Словарь с данными пользователя или None, если пользователь не найден
        """
        try:
            async with self.pool.acquire() as conn:
                user = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)

            if user:
                user_dict = dict(user)
                user_dict["roles"] = user_dict["roles"].split(",") if user_dict["roles"] else []
                return user_dict

            return None
        except Exception as e:
            logger.error("Ошибка при получении пользователя по email %s: %s", email, e)
            raise

    async def get_oauth_account(
        self, provider: str, provider_user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Получает OAuth аккаунт пользователя.

        Args:
            provider: Провайдер OAuth (например, 'google')
            provider_user_id: ID пользователя в системе провайдера

        Returns:
            Словарь с данными OAuth аккаунта или None, если аккаунт не найден
        """
        try:
            async with self.pool.acquire() as conn:
                account = await conn.fetchrow(
                    "SELECT * FROM oauth_accounts WHERE provider = $1 AND provider_user_id = $2",
                    provider,
                    provider_user_id,
                )

            return dict(account) if account else None
        except Exception as e:
            logger.error(
                "Ошибка при получении OAuth аккаунта (provider=%s, id=%s): %s",
                provider,
                provider_user_id,
                e,
            )
            raise

    async def create_oauth_account(self, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает OAuth аккаунт для пользователя.

        Args:
            account_data: Словарь с данными OAuth аккаунта

        Returns:
            Словарь с данными созданного OAuth аккаунта
        """
        fields = list(account_data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(fields)))
        fields_str = ", ".join(fields)

        query = f"INSERT INTO oauth_accounts ({fields_str}) VALUES ({placeholders}) RETURNING *"

        try:
            async with self.pool.acquire() as conn:
                account = await conn.fetchrow(query, *account_data.values())

            return dict(account) if account else None
        except Exception as e:
            logger.error("Ошибка при создании OAuth аккаунта: %s", e)
            raise

    async def create_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает новую запись о платеже.

        Args:
            payment_data: Словарь с данными платежа

        Returns:
            Словарь с данными созданного платежа, включая ID
        """
        fields = list(payment_data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(fields)))
        fields_str = ", ".join(fields)

        query = f"""
        INSERT INTO payments ({fields_str})
        VALUES ({placeholders})
        RETURNING *
        """

        try:
            async with self.pool.acquire() as conn:
                payment = await conn.fetchrow(query, *payment_data.values())

            return dict(payment) if payment else None
        except Exception as e:
            logger.error("Ошибка при создании платежа: %s", e)
            raise

    async def update_payment(
        self, payment_id: str, payment_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет данные платежа.

        Args:
            payment_id: ID платежа в системе PayPal
            payment_data: Словарь с обновляемыми данными платежа

        Returns:
            Словарь с обновленными данными платежа или None, если платеж не найден
        """
        if not payment_data:
            return None

        set_parts = [f"{key} = ${i+1}" for i, key in enumerate(payment_data.keys())]
        set_parts.append(f"updated_at = ${len(set_parts) + 1}")

        query = f"""
        UPDATE payments
        SET {", ".join(set_parts)}
        WHERE payment_id = ${len(set_parts) + 1}
        RETURNING *
        """

        params = list(payment_data.values()) + [datetime.utcnow(), payment_id]

        try:
            async with self.pool.acquire() as conn:
                updated_payment = await conn.fetchrow(query, *params)

            return dict(updated_payment) if updated_payment else None
        except Exception as e:
            logger.error("Ошибка при обновлении платежа с ID %s: %s", payment_id, e)
            raise

    async def get_payment_by_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает платеж по ID в системе PayPal.

        Args:
            payment_id: ID платежа в системе PayPal

        Returns:
            Словарь с данными платежа или None, если платеж не найден
        """
        try:
            async with self.pool.acquire() as conn:
                payment = await conn.fetchrow(
                    "SELECT * FROM payments WHERE payment_id = $1", payment_id
                )

            return dict(payment) if payment else None
        except Exception as e:
            logger.error("Ошибка при получении платежа по ID %s: %s", payment_id, e)
            raise

    async def get_payments(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        payment_provider: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получает список платежей с учетом параметров фильтрации.

        Args:
            skip: Количество записей для пропуска (пагинация)
            limit: Максимальное количество записей для возврата
            status: Фильтр по статусу платежа
            payment_provider: Фильтр по платежной системе

        Returns:
            Список словарей с данными платежей
        """
        query_parts = ["SELECT * FROM payments"]
        conditions = []
        params = []

        if status:
            conditions.append(f"status = ${len(params) + 1}")
            params.append(status)

        if payment_provider:
            conditions.append(f"payment_provider = ${len(params) + 1}")
            params.append(payment_provider)

        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))

        query_parts.append(
            f"ORDER BY created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        )
        params.extend([limit, skip])

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка при получении списка платежей: %s", e)
            raise

    async def create_warehouse(self, user_id: int, warehouse_data: WarehouseCreate) -> Warehouse:
        """
        Создает новый склад.

        Args:
            user_id: ID пользователя
            warehouse_data: Данные склада

        Returns:
            Объект склада

        Raises:
            Exception: Ошибка при создании склада
        """
        try:
            query = """
            INSERT INTO warehouses (user_id, name, location)
            VALUES ($1, $2, $3)
            RETURNING id, user_id, name, location
            """

            async with self.pool.acquire() as conn:
                logger.debug("Попытка создать склад")
                row = await conn.fetchrow(
                    query, user_id, warehouse_data.name, warehouse_data.location
                )
                logger.debug("Создан склад: %s", row)

                return Warehouse(**dict(row))
        except Exception as e:
            logger.error("Ошибка при создании склада: %s", e)
            raise

    async def get_warehouses(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
    ) -> List[Warehouse]:
        """
        Получает список складов пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            Список объектов складов

        Raises:
            Exception: Ошибка при получении списка складов
        """

        try:
            query_parts = ["SELECT * FROM warehouses WHERE user_id = $1"]
            params = [user_id]
            param_index = 2  # PostgreSQL использует $1, $2, $3...

            if search:
                query_parts.append(
                    f"AND (name ILIKE ${param_index} OR location ILIKE ${param_index + 1})"
                )
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])
                param_index += 3

            valid_columns = [
                "id",
                "name",
                "location",
            ]

            if sort_by and sort_by in valid_columns:
                sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"
                query_parts.append(f"ORDER BY {sort_by} {sort_order}")
            else:
                query_parts.append("ORDER BY id ASC")

            query_parts.append(f"LIMIT ${param_index} OFFSET ${param_index + 1}")
            params.extend([limit, skip])

            query = " ".join(query_parts)

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Ошибка при получении списка складов: %s", e)
            raise

    async def get_warehouse_by_id(self, warehouse_id: int) -> Warehouse:
        """
        Получает склад по ID и ID пользователя.

        Args:
            user_id: ID пользователя
            warehouse_id: ID склада

        Returns:
            Объект склада

        Raises:
            Exception: Ошибка при получении склада
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM warehouses WHERE id = $1", warehouse_id)

            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при получении склада: %s", e)
            raise

    async def update_warehouse(
        self, warehouse_id: int, warehouse_data: WarehouseCreate
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет данные склада.

        Args:
            warehouse_id: ID склада
            warehouse_data: Словарь с обновляемыми данными склада

        Returns:
            Словарь с обновленными данными склада или None, если склад не найден
        """
        if not warehouse_data:
            return await self.get_warehouse_by_id(warehouse_id)

        set_parts = []
        params = []

        warehouse_dict = warehouse_data.model_dump()

        for i, (key, value) in enumerate(warehouse_dict.items(), start=1):
            set_parts.append(f"{key} = ${i}")
            params.append(value)

        # Добавляем обновление `updated_at`
        params.append(datetime.utcnow())
        set_parts.append(f"updated_at = ${len(params)}")

        # Добавляем `warehouse_id` в параметры
        params.append(warehouse_id)
        query = (
            f"UPDATE warehouses SET {', '.join(set_parts)} WHERE id = ${len(params)} RETURNING *"
        )

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        query, *params
                    )  # fetchrow() сразу возвращает обновленные данные

            return dict(row) if row else None
        except Exception as e:
            logger.error("Ошибка при обновлении склада с ID %s: %s", warehouse_id, e)
            raise

    async def delete_warehouse(self, warehouse_id: int) -> bool:
        """
        Удаляет склад.

        Args:
            warehouse_id: ID склада

        Returns:
            True, если склад успешно удален, иначе False
        """
        query = "DELETE FROM warehouses WHERE id = $1"

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(query, warehouse_id)

            return result.startswith("DELETE")  # asyncpg возвращает строку 'DELETE <количество>'
        except Exception as e:
            logger.error("Ошибка при удалении склада с ID %s: %s", warehouse_id, e)
            raise

    async def add_product_to_warehouse(
        self, warehouse_id: int, product_id: int, quantity: int
    ) -> bool:
        """
        Добавляет продукт в склад.

        Args:
            warehouse_id: ID склада
            product_id: ID продукта

        Returns:
            True, если продукт успешно добавлен, иначе False
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Проверяем, есть ли уже этот товар на складе
                    existing_quantity = await conn.fetchval(
                        """
                        SELECT quantity FROM warehouse_products 
                        WHERE warehouse_id = $1 AND product_id = $2
                        """,
                        warehouse_id,
                        product_id,
                    )

                    if existing_quantity is not None:
                        # Если товар уже есть, обновляем количество
                        await conn.execute(
                            """
                            UPDATE warehouse_products 
                            SET quantity = $1 
                            WHERE warehouse_id = $2 AND product_id = $3
                            """,
                            quantity,
                            warehouse_id,
                            product_id,
                        )
                    else:
                        # Если товара нет, создаем новую запись
                        await conn.execute(
                            """
                            INSERT INTO warehouse_products (warehouse_id, product_id, quantity) 
                            VALUES ($1, $2, $3)
                            """,
                            warehouse_id,
                            product_id,
                            quantity,
                        )

            logger.info(
                "Продукт %s успешно добавлен/обновлен на складе %s", product_id, warehouse_id
            )
            return True

        except Exception as e:
            logger.error("Ошибка при добавлении продукта в склад с ID %s: %s", warehouse_id, e)
            return False

    async def generate_order_id(self) -> str:
        """Генерирует уникальный order_id с инкрементом и префиксом ORD-."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                last_number = await conn.fetchval(
                    "UPDATE order_counter SET last_number = last_number + 1 RETURNING last_number"
                )
                return f"ORD-{last_number}"

    async def create_sale(
        self, user_id: int, items: List[SaleItem], currency: str, payment_method: str
    ) -> str:
        """Создание продажу и возвращает order_id"""
        try:
            order_id = await self.generate_order_id()
            total_amount = sum(item.price * item.quantity for item in items)

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """INSERT INTO sales (order_id, user_id, total_amount, currency, status) VALUES ($1, $2, $3, $4, $5)""",
                        order_id,
                        user_id,
                        total_amount,
                        currency,
                        "pending",
                    )

                    for item in items:
                        await conn.execute(
                            """INSERT INTO sales_items (sale_id, product_id, warehouse_id, quantity, price, cost_price, total) VALUES ((SELECT id FROM sales WHERE order_id = $1), $2, $3, $4, $5, $6, $7)""",
                            order_id,
                            item.product_id,
                            item.warehouse_id,
                            item.quantity,
                            item.price,
                            item.cost_price,
                            item.price * item.quantity,
                        )

                    await conn.execute(
                        """INSERT INTO receipts (order_id, user_id, total_amount, payment_method) VALUES ($1, $2, $3, $4)""",
                        order_id,
                        user_id,
                        total_amount,
                        payment_method,
                    )

            return order_id
        except Exception as e:
            logger.error("Ошибка при создании записи о продаже %s: %s", order_id, str(e))
            return False

    async def update_sale_status(self, order_id: str, status: str) -> bool:
        """Обновляет статус продажи"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "UPDATE sales SET status = $1 WHERE order_id = $2", status, order_id
                )
            return result == "UPDATE 1"
        except Exception as e:
            logger.error("Ошибка при обновлении статуса продажи %s: %s", order_id, str(e))
            return False

    async def get_sale_details(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Получает детали заказа и товаров в нём."""
        async with self.pool.acquire() as conn:
            sale = await conn.fetchrow("SELECT * FROM sales WHERE order_id = $1", order_id)

            if not sale:
                return None

            items = await conn.fetch("SELECT * FROM sales_items WHERE sale_id = $1", sale["id"])

            return {
                "order_id": sale["order_id"],
                "user_id": sale["user_id"],
                "total_amount": sale["total_amount"],
                "currency": sale["currency"],
                "status": sale["status"],
                "created_at": sale["created_at"],
                "items": [dict(item) for item in items],
            }

    async def get_sales_count(
        self,
        user_id: int,
        search: Optional[str] = None,
        warehouse_id: Optional[int] = None,
    ) -> int:
        query_parts = ["SELECT COUNT(*) FROM sales WHERE user_id = $1"]
        params = [user_id]
        param_index = 2  # PostgreSQL использует $1, $2, $3...

        if search:
            query_parts.append(f"AND (order_id ILIKE ${param_index})")
            search_term = f"%{search}%"
            params.append(search_term)
            param_index += 1

        if warehouse_id is not None:
            query_parts.append(
                f"""AND id IN (SELECT product_id FROM sales_items WHERE warehouse_id = ${param_index})"""
            )
            params.append(warehouse_id)
            param_index += 1

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *params)
            return result if result else 0
        except Exception as e:
            logger.error("Ошибка при получении количества товаров: %s", e)
            raise

    async def get_sales(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        warehouse_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        query_parts = ["SELECT * FROM sales WHERE user_id = $1"]
        params = [user_id]
        param_index = 2  # PostgreSQL использует $1, $2, $3...

        if search:
            query_parts.append(f"AND (order_id ILIKE ${param_index})")
            search_term = f"%{search}%"
            params.append(search_term)
            param_index += 1

        if warehouse_id is not None:
            query_parts.append(
                f"""AND id IN (SELECT product_id FROM sales_items WHERE warehouse_id = ${param_index})"""
            )
            params.append(warehouse_id)
            param_index += 1

        valid_columns = ["id", "order_id", "total_amount", "currency", "status", "created_at"]

        if sort_by and sort_by in valid_columns:
            sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"
            query_parts.append(f"ORDER BY {sort_by} {sort_order}")
        else:
            query_parts.append("ORDER BY id ASC")

        query_parts.append(f"LIMIT ${param_index} OFFSET ${param_index + 1}")
        params.extend([limit, skip])

        query = " ".join(query_parts)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                sales = [dict(row) for row in rows]

                order_ids = [sale["order_id"] for sale in sales]

                if not order_ids:
                    return sales

                items_query = """SELECT * FROM sales_items WHERE sale_id IN (SELECT id FROM sales WHERE order_id = ANY($1))"""
                item_rows = await conn.fetch(items_query, order_ids)
                items = [dict(row) for row in item_rows]

                items_map = {}
                for item in items:
                    sale_id = item["sale_id"]
                    if sale_id not in items_map:
                        items_map[sale_id] = []
                    items_map[sale_id].append(item)

                for sale in sales:
                    sale["items"] = items_map.get(sale["id"], [])

            return sales
        except Exception as e:
            logger.error("Ошибка при получении списка товаров: %s", e)
            raise
