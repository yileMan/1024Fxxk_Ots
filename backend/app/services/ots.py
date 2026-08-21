from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.ots import OtsComponent, ProductOts
from app.models.products import ProductVersion
from app.models.user import AuditLog
from app.repositories.ots import OtsRepository


CSV_FIELDS = ("ots_name", "ots_version", "official_website", "is_eol")
MAX_CSV_BYTES = 1024 * 1024
MAX_CSV_ROWS = 5000


class OtsManagementError(ValueError):
    code = "OTS_MANAGEMENT_ERROR"


class OtsNotFoundError(OtsManagementError):
    code = "OTS_NOT_FOUND"


class OtsConflictError(OtsManagementError):
    code = "OTS_COMPONENT_CONFLICT"


class OtsVersionConflictError(OtsManagementError):
    code = "OTS_VERSION_CONFLICT"


class ProductOtsConflictError(OtsManagementError):
    code = "PRODUCT_OTS_CONFLICT"


class ProductOtsHistoryConflictError(OtsManagementError):
    code = "PRODUCT_OTS_HISTORY_CONFLICT"


class OtsCsvInvalidError(OtsManagementError):
    code = "OTS_CSV_INVALID"

    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__(self.code)
        self.errors = errors


@dataclass(frozen=True)
class OtsPage:
    items: list[OtsComponent]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class ProductOtsView:
    id: int
    product_version_id: int
    ots_component_id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    ots_name: str
    ots_version: str
    official_website: str
    is_eol: bool


@dataclass(frozen=True)
class AssociatedVersionView:
    product_ots_id: int
    product_id: int
    product_code: str
    product_name: str
    product_version_id: int
    version_no: str
    status: str


@dataclass(frozen=True)
class CsvImportResult:
    created_ots: int
    created_relations: int
    existing_relations: int


@dataclass(frozen=True)
class CsvRow:
    row: int
    ots_name: str
    ots_version: str
    official_website: str
    is_eol: bool


class OtsManagementService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = OtsRepository()

    @staticmethod
    def _audit(session: Session, actor_id: int, action: str, object_type: str, object_id: int | None, detail: dict[str, object]) -> None:
        session.add(AuditLog(user_id=actor_id, action=action, object_type=object_type, object_id=str(object_id) if object_id is not None else None, detail_json=detail))

    def list_ots(self, *, query: str | None, is_eol: bool | None, page: int, page_size: int) -> OtsPage:
        with self._session_factory() as session:
            items = self._repository.list_ots(session, query=query, is_eol=is_eol)
            start = (page - 1) * page_size
            return OtsPage(items[start:start + page_size], len(items), page, page_size)

    def get_ots(self, ots_id: int) -> OtsComponent:
        with self._session_factory() as session:
            return self._ots(session, ots_id)

    def create_ots(self, *, actor_id: int, ots_name: str, ots_version: str, official_website: str, is_eol: bool) -> OtsComponent:
        try:
            with self._session_factory.begin() as session:
                item = OtsComponent(ots_name=ots_name.strip(), ots_version=ots_version.strip(), official_website=official_website.strip(), is_eol=is_eol, row_version=1)
                session.add(item)
                session.flush()
                self._audit(session, actor_id, "insert", "ots_component", item.id, {"ots_name": item.ots_name, "ots_version": item.ots_version, "row_version": 1})
                return item
        except IntegrityError as error:
            raise OtsConflictError() from error

    def update_ots(self, *, actor_id: int, ots_id: int, ots_name: str, ots_version: str, official_website: str, is_eol: bool, row_version: int) -> OtsComponent:
        try:
            with self._session_factory.begin() as session:
                self._ots(session, ots_id)
                if not self._repository.update_ots_if_version(session, ots_id, row_version, ots_name=ots_name.strip(), ots_version=ots_version.strip(), official_website=official_website.strip(), is_eol=is_eol, updated_at=datetime.now()):
                    raise OtsVersionConflictError()
                self._audit(session, actor_id, "update", "ots_component", ots_id, {"row_version": {"from": row_version, "to": row_version + 1}})
                return self._ots(session, ots_id)
        except IntegrityError as error:
            raise OtsConflictError() from error

    def list_product_ots(self, version_id: int) -> list[ProductOtsView]:
        with self._session_factory() as session:
            self._version(session, version_id)
            return [self._view(relation, ots) for relation, ots in self._repository.list_product_ots(session, version_id)]

    def list_associated_versions(self, ots_id: int) -> list[AssociatedVersionView]:
        with self._session_factory() as session:
            self._ots(session, ots_id)
            return [AssociatedVersionView(relation.id, product.id, product.product_code, product.product_name, version.id, version.version_no, version.status) for relation, version, product in self._repository.list_associated_versions(session, ots_id)]

    def create_relation(self, *, actor_id: int, version_id: int, ots_component_id: int) -> ProductOtsView:
        try:
            with self._session_factory.begin() as session:
                self._version(session, version_id)
                ots = self._ots(session, ots_component_id)
                relation = ProductOts(product_version_id=version_id, ots_component_id=ots_component_id, created_by=actor_id)
                session.add(relation)
                session.flush()
                self._audit(session, actor_id, "insert", "product_ots", relation.id, {"product_version_id": version_id, "ots_component_id": ots_component_id})
                return self._view(relation, ots)
        except IntegrityError as error:
            raise ProductOtsConflictError() from error

    def remove_relation(self, *, actor_id: int, version_id: int, relation_id: int) -> None:
        with self._session_factory.begin() as session:
            self._version(session, version_id)
            relation = self._repository.get_relation(session, relation_id)
            if relation is None or relation.product_version_id != version_id:
                raise OtsNotFoundError()
            if self._repository.has_downstream_history(session, relation_id):
                raise ProductOtsHistoryConflictError()
            detail = {"product_version_id": version_id, "ots_component_id": relation.ots_component_id}
            session.delete(relation)
            self._audit(session, actor_id, "delete", "product_ots", relation_id, detail)

    @staticmethod
    def template_csv() -> str:
        return ",".join(CSV_FIELDS) + "\r\n"

    def export_csv(self, version_id: int) -> str:
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(CSV_FIELDS)
        for item in self.list_product_ots(version_id):
            writer.writerow((item.ots_name, item.ots_version, item.official_website, str(item.is_eol).lower()))
        return output.getvalue()

    def import_csv(self, *, actor_id: int, version_id: int, content: bytes, file_name: str) -> CsvImportResult:
        rows = self._parse_csv(content)
        try:
            with self._session_factory.begin() as session:
                self._version(session, version_id)
                existing = self._repository.find_ots_by_keys(session, [(row.ots_name, row.ots_version) for row in rows])
                by_key = {(item.ots_name.casefold(), item.ots_version.casefold()): item for item in existing}
                errors: list[dict[str, object]] = []
                for row in rows:
                    item = by_key.get((row.ots_name.casefold(), row.ots_version.casefold()))
                    if item is None:
                        continue
                    if item.official_website != row.official_website:
                        errors.append({"row": row.row, "field": "official_website", "reason": "与现有 OTS 主数据不一致"})
                    if item.is_eol != row.is_eol:
                        errors.append({"row": row.row, "field": "is_eol", "reason": "与现有 OTS 主数据不一致"})
                if errors:
                    raise OtsCsvInvalidError(errors)

                created_ots = created_relations = existing_relations = 0
                for row in rows:
                    key = (row.ots_name.casefold(), row.ots_version.casefold())
                    item = by_key.get(key)
                    if item is None:
                        item = OtsComponent(ots_name=row.ots_name, ots_version=row.ots_version, official_website=row.official_website, is_eol=row.is_eol, row_version=1)
                        session.add(item)
                        session.flush()
                        by_key[key] = item
                        created_ots += 1
                    if self._repository.find_relation(session, version_id, item.id) is not None:
                        existing_relations += 1
                        continue
                    session.add(ProductOts(product_version_id=version_id, ots_component_id=item.id, created_by=actor_id))
                    created_relations += 1
                session.flush()
                if created_ots or created_relations:
                    self._audit(session, actor_id, "batch_upsert", "product_ots", None, {"product_version_id": version_id, "file_name": file_name, "created_ots": created_ots, "created_relations": created_relations, "existing_relations": existing_relations})
                return CsvImportResult(created_ots, created_relations, existing_relations)
        except IntegrityError as error:
            raise ProductOtsConflictError() from error

    @staticmethod
    def _parse_csv(content: bytes) -> list[CsvRow]:
        if len(content) > MAX_CSV_BYTES:
            raise OtsCsvInvalidError([{"row": 0, "field": "file", "reason": "文件超过 1 MiB 限制"}])
        try:
            text_content = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise OtsCsvInvalidError([{"row": 0, "field": "file", "reason": "文件必须使用 UTF-8 编码"}]) from error
        try:
            reader = csv.DictReader(StringIO(text_content, newline=""), strict=True)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise OtsCsvInvalidError([{"row": 1, "field": "header", "reason": "表头必须为 " + ",".join(CSV_FIELDS)}])
            rows: list[CsvRow] = []
            errors: list[dict[str, object]] = []
            seen: set[tuple[str, str]] = set()
            for index, raw in enumerate(reader, start=2):
                if len(rows) >= MAX_CSV_ROWS:
                    errors.append({"row": index, "field": "file", "reason": "数据行不能超过 5000 行"})
                    break
                values = {field: (raw.get(field) or "").strip() for field in CSV_FIELDS}
                if raw.get(None):
                    errors.append({"row": index, "field": "row", "reason": "字段数量超过固定表头"})
                for field in ("ots_name", "ots_version", "official_website", "is_eol"):
                    if not values[field]:
                        errors.append({"row": index, "field": field, "reason": "不能为空"})
                for field, maximum in (("ots_name", 200), ("ots_version", 200), ("official_website", 1000)):
                    if len(values[field]) > maximum:
                        errors.append({"row": index, "field": field, "reason": f"长度不能超过 {maximum} 个字符"})
                parsed_url = urlparse(values["official_website"])
                if values["official_website"] and (parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc):
                    errors.append({"row": index, "field": "official_website", "reason": "必须是有效的 HTTP(S) 地址"})
                if values["is_eol"] not in {"true", "false"}:
                    errors.append({"row": index, "field": "is_eol", "reason": "仅允许 true 或 false"})
                key = (values["ots_name"].casefold(), values["ots_version"].casefold())
                if key in seen:
                    errors.append({"row": index, "field": "ots_name", "reason": "同一文件中名称和版本重复"})
                seen.add(key)
                if all(values.values()) and values["is_eol"] in {"true", "false"} and parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
                    rows.append(CsvRow(index, values["ots_name"], values["ots_version"], values["official_website"], values["is_eol"] == "true"))
            if errors:
                raise OtsCsvInvalidError(errors)
            return rows
        except csv.Error as error:
            raise OtsCsvInvalidError([{"row": 0, "field": "file", "reason": f"CSV 无法解析：{error}"}]) from error

    def _ots(self, session: Session, ots_id: int) -> OtsComponent:
        item = self._repository.get_ots(session, ots_id)
        if item is None:
            raise OtsNotFoundError()
        return item

    @staticmethod
    def _version(session: Session, version_id: int) -> ProductVersion:
        version = session.get(ProductVersion, version_id)
        if version is None:
            raise OtsNotFoundError()
        return version

    @staticmethod
    def _view(relation: ProductOts, ots: OtsComponent) -> ProductOtsView:
        return ProductOtsView(relation.id, relation.product_version_id, relation.ots_component_id, relation.created_by, relation.created_at, relation.updated_at, ots.ots_name, ots.ots_version, ots.official_website, ots.is_eol)
