from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.products import Product, ProductVersion
from app.models.user import AppUser, AuditLog
from app.repositories.products import ProductRepository


class ProductManagementError(ValueError):
    code = "PRODUCT_MANAGEMENT_ERROR"


class ProductNotFoundError(ProductManagementError):
    code = "PRODUCT_NOT_FOUND"


class ProductCodeConflictError(ProductManagementError):
    code = "PRODUCT_CODE_CONFLICT"


class ProductVersionConflictError(ProductManagementError):
    code = "PRODUCT_VERSION_CONFLICT"


class ProductAssignmentInvalidError(ProductManagementError):
    code = "PRODUCT_ASSIGNMENT_INVALID"


@dataclass(frozen=True)
class ProductPage:
    items: list[Product]
    total: int
    page: int
    page_size: int


class ProductManagementService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = ProductRepository()

    @staticmethod
    def _audit(session: Session, actor_id: int, action: str, object_type: str, object_id: int, detail: dict[str, object]) -> None:
        session.add(AuditLog(user_id=actor_id, action=action, object_type=object_type, object_id=str(object_id), detail_json=detail))

    def list_products(self, *, query: str | None, status: str | None, page: int, page_size: int) -> ProductPage:
        with self._session_factory() as session:
            products = self._repository.list_products(session, query=query, status=status)
            start = (page - 1) * page_size
            return ProductPage(products[start : start + page_size], len(products), page, page_size)

    def get_product(self, product_id: int) -> Product:
        with self._session_factory() as session:
            return self._product(session, product_id)

    def create_product(self, *, actor_id: int, product_code: str, product_name: str, description: str | None) -> Product:
        try:
            with self._session_factory.begin() as session:
                product = Product(product_code=product_code.strip(), product_name=product_name.strip(), description=description, status="active", row_version=1)
                session.add(product)
                session.flush()
                self._audit(session, actor_id, "insert", "product", product.id, {"product_code": product.product_code, "product_name": product.product_name, "status": "active", "row_version": 1})
                return product
        except IntegrityError as error:
            raise ProductCodeConflictError() from error

    def update_product(self, *, actor_id: int, product_id: int, product_code: str, product_name: str, description: str | None, row_version: int) -> Product:
        try:
            with self._session_factory.begin() as session:
                product = self._product(session, product_id)
                if not self._repository.update_product_if_version(session, product_id, row_version, product_code=product_code.strip(), product_name=product_name.strip(), description=description, updated_at=datetime.now()):
                    raise ProductVersionConflictError()
                self._audit(session, actor_id, "update", "product", product_id, {"row_version": {"from": row_version, "to": row_version + 1}})
                session.expire(product)
                return self._product(session, product_id)
        except IntegrityError as error:
            raise ProductCodeConflictError() from error

    def disable_product(self, *, actor_id: int, product_id: int, row_version: int) -> Product:
        with self._session_factory.begin() as session:
            product = self._product(session, product_id)
            if product.status == "disabled":
                return product
            if not self._repository.update_product_if_version(session, product_id, row_version, status="disabled", updated_at=datetime.now()):
                raise ProductVersionConflictError()
            self._audit(session, actor_id, "update", "product", product_id, {"status": {"from": "active", "to": "disabled"}, "row_version": {"from": row_version, "to": row_version + 1}})
            session.expire(product)
            return self._product(session, product_id)

    def list_versions(self, product_id: int) -> list[ProductVersion]:
        with self._session_factory() as session:
            self._product(session, product_id)
            return self._repository.list_versions(session, product_id)

    def get_version(self, product_id: int, version_id: int) -> ProductVersion:
        with self._session_factory() as session:
            self._product(session, product_id)
            return self._version(session, product_id, version_id)

    def create_version(self, *, actor_id: int, product_id: int, version_no: str, description: str | None, owner_id: int, reviewer_id: int) -> ProductVersion:
        try:
            with self._session_factory.begin() as session:
                self._product(session, product_id)
                self._validate_assignment(session, owner_id, reviewer_id)
                version = ProductVersion(product_id=product_id, version_no=version_no.strip(), description=description, primary_cvss_version="3.1", owner_id=owner_id, reviewer_id=reviewer_id, status="active", row_version=1)
                session.add(version)
                session.flush()
                self._audit(session, actor_id, "insert", "product_version", version.id, {"product_id": product_id, "version_no": version.version_no, "owner_id": owner_id, "reviewer_id": reviewer_id, "row_version": 1})
                return version
        except IntegrityError as error:
            raise ProductVersionConflictError() from error

    def update_version(self, *, actor_id: int, product_id: int, version_id: int, version_no: str, description: str | None, owner_id: int, reviewer_id: int, row_version: int) -> ProductVersion:
        try:
            with self._session_factory.begin() as session:
                version = self._version(session, product_id, version_id)
                self._validate_assignment(session, owner_id, reviewer_id)
                if not self._repository.update_version_if_version(session, version_id, row_version, version_no=version_no.strip(), description=description, owner_id=owner_id, reviewer_id=reviewer_id, updated_at=datetime.now()):
                    raise ProductVersionConflictError()
                self._audit(session, actor_id, "update", "product_version", version_id, {"row_version": {"from": row_version, "to": row_version + 1}})
                session.expire(version)
                return self._version(session, product_id, version_id)
        except IntegrityError as error:
            raise ProductVersionConflictError() from error

    def disable_version(self, *, actor_id: int, product_id: int, version_id: int, row_version: int) -> ProductVersion:
        with self._session_factory.begin() as session:
            version = self._version(session, product_id, version_id)
            if version.status == "disabled":
                return version
            if not self._repository.update_version_if_version(session, version_id, row_version, status="disabled", updated_at=datetime.now()):
                raise ProductVersionConflictError()
            self._audit(session, actor_id, "update", "product_version", version_id, {"status": {"from": "active", "to": "disabled"}, "row_version": {"from": row_version, "to": row_version + 1}})
            session.expire(version)
            return self._version(session, product_id, version_id)

    def _product(self, session: Session, product_id: int) -> Product:
        product = self._repository.get_product(session, product_id)
        if product is None:
            raise ProductNotFoundError()
        return product

    def _version(self, session: Session, product_id: int, version_id: int) -> ProductVersion:
        version = self._repository.get_version(session, version_id)
        if version is None or version.product_id != product_id:
            raise ProductNotFoundError()
        return version

    @staticmethod
    def _validate_assignment(session: Session, owner_id: int, reviewer_id: int) -> None:
        owner = session.get(AppUser, owner_id)
        reviewer = session.get(AppUser, reviewer_id)
        if owner is None or owner.status != "active" or "product_owner" not in owner.roles_json:
            raise ProductAssignmentInvalidError()
        if reviewer is None or reviewer.status != "active" or "reviewer" not in reviewer.roles_json:
            raise ProductAssignmentInvalidError()
