"""
Utilities for FastAPI dependencies.

This module provides functions and classes for working with FastAPI dependencies
in a more convenient way. It includes functions for creating dependencies with
authentication and authorization, as well as classes for creating custom
dependencies.
"""

import logging
from typing import Awaitable, Callable, List

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from config import get_settings
from core.database import DatabaseService
from core.models import User
from services.auth_service import AuthService
from services.payment_service import PaymentService
from services.product_service import ProductService
from services.warehouse_service import WarehouseService

logger = logging.getLogger("dependencies")

# Инициализация заголовка API-ключа
api_key_header = APIKeyHeader(name="X-API-Key")
# Существующие зависимости
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
settings = get_settings()


# Функции зависимостей для FastAPI
def get_db():
    """
    Получает соединение с базой данных из состояния приложения.
    Используется как зависимость.
    """
    from main import app

    # pylint: disable=no-member
    return app.db_pool


def get_db_service(db=Depends(get_db)):
    """
    Создает и возвращает сервис базы данных.
    Используется как зависимость.
    """
    return DatabaseService(db)


def get_product_service(db_service=Depends(get_db_service)):
    """
    Создает и возвращает сервис товаров.
    Используется как зависимость.
    """
    return ProductService(db_service)


def get_warehouse_service(db_service=Depends(get_db_service)):
    """
    Создает и возвращает сервис складов.
    Используется как зависимость.
    """
    return WarehouseService(db_service)


def get_sync_auth_service(db_service=Depends(get_db_service)):
    """
    Создает и возвращает сервис аутентификации (синхронная версия).
    Используется как зависимость.
    """
    return AuthService(db_service)


async def get_auth_service(db_service=Depends(get_db_service)):
    """
    Создает и возвращает сервис аутентификации (асинхронная версия).
    Используется как зависимость.
    """
    return AuthService(db_service)


async def get_current_user(
    token: str = Security(api_key_header),
    auth_service: AuthService = Depends(get_sync_auth_service),
) -> User:
    """
    Получает текущего пользователя по токену.
    Используется как зависимость.

    Raises:
        HTTPException: Если токен недействителен или истек
    """
    user = await auth_service.get_current_user(token)

    if not user:
        logger.warning("Недействительные учетные данные: %s...", token[:10])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return User(**user)


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Проверяет, что текущий пользователь активен.
    Используется как зависимость.

    Raises:
        HTTPException: Если пользователь неактивен
    """
    if not current_user.is_active:
        logger.warning("Попытка доступа неактивного пользователя: %s", current_user.username)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    return current_user


def has_role(required_roles: List[str]) -> Callable[[User], Awaitable[User]]:
    """
    Создает зависимость для проверки ролей пользователя.

    Args:
        required_roles: Список необходимых ролей

    Returns:
        Функция зависимости, которая проверяет роли пользователя

    Raises:
        HTTPException: Если у пользователя нет необходимых ролей
    """

    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        for role in required_roles:
            if role in current_user.roles:
                return current_user

        logger.warning(
            "Отказ в доступе пользователю %s. Требуемые роли: %s",
            current_user.username,
            ", ".join(required_roles),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    return role_checker


def get_payment_service():
    """Dependency для получения экземпляра PaymentService."""
    return PaymentService()


async def can_read_products(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Проверяет, что пользователь может читать данные о товарах.
    Любой активный и аутентифицированный пользователь имеет право на чтение.
    """
    return current_user


async def can_read_warehouses(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Проверяет, что пользователь может читать данные о складах.
    Любой активный и аутентифицированный пользователь имеет право на чтение.
    """
    return current_user


async def can_manage_product(
    product_id: int,
    current_user: User = Depends(get_current_active_user),
    product_service: ProductService = Depends(get_product_service),
) -> User:
    """
    Проверяет, может ли пользователь управлять данным продуктом.

    - Администратор имеет полный доступ.
    - Владелец товара может управлять только своими товарами.

    Raises:
        HTTPException: если доступ запрещен.
    """
    if "admin" in current_user.roles:
        return current_user

    product = await product_service.get_product_by_id(product_id)
    if not product or product.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для управления этим товаром",
        )

    return current_user


async def can_manage_warehouse(
    warehouse_id: int,
    current_user: User = Depends(get_current_active_user),
    warehouse_service: WarehouseService = Depends(get_warehouse_service),
) -> User:
    """
    Проверяет, может ли пользователь управлять данным складом.

    - Администратор имеет полный доступ.
    - Владелец склада может управлять только своими складами.

    Raises:
        HTTPException: если доступ запрещен.
    """
    if "admin" in current_user.roles:
        return current_user

    warehouse = await warehouse_service.get_warehouse_by_id(warehouse_id)
    if not warehouse or warehouse.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для управления этим складом",
        )

    return current_user
